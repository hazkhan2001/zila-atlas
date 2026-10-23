"""
build_districts.py: build the district, province and tehsil layers.

Run from the project folder:
    python pipeline/build_districts.py

HOW IT WORKS
    1. Load 554 tehsil shapes (2017 census tehsils).
    2. Work out each tehsil's province and its old (2019) district from
       hint layers, using a spatial join.
    3. Assign each tehsil to a 2023 census district, using a cascade of
       rules from most to least certain (see `assign_tehsil`).
    4. Merge ("dissolve") tehsils into districts, and districts into provinces.
    5. Check that every census district got a shape, then write everything.

OUTPUTS (data/processed/)
    districts.csv / .geojson   one row per district, with district_id
    provinces.geojson          provinces built from the districts
    tehsils.csv                every tehsil, its district, and HOW it was assigned
    special_areas.geojson      areas outside all districts (shown, no statistics)
    build_report.txt           counts, warnings and everything needing review
"""

import sys
from difflib import get_close_matches
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyreadr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import config
from pipeline.names import build_lookup, match_key, normalize_name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_slug(name: str) -> str:
    """'Dera Ismail Khan' -> 'DERA-ISMAIL-KHAN'"""
    return normalize_name(name).upper().replace(" ", "-")


def area_km2(gdf: gpd.GeoDataFrame) -> pd.Series:
    """Area in square kilometres, measured in an equal-area projection."""
    return (gdf.to_crs(config.AREA_CRS).area / 1_000_000).round(1)


def locate(shapes: gpd.GeoDataFrame, hint: gpd.GeoDataFrame, col: str) -> pd.Series:
    """
    For each shape, return `col` from the hint polygon that contains it.

    LESSON: a spatial join matches rows by location instead of a shared ID.
    We test one point per shape: `representative_point()` is guaranteed to
    fall inside the shape (a plain centroid can land outside a crescent).
    Points that hit no hint polygon (coastal slivers, border mismatches)
    fall back to the nearest one.
    """
    pts = shapes[["geometry"]].copy()
    pts["geometry"] = shapes.representative_point()
    hit = gpd.sjoin(pts, hint[[col, "geometry"]], how="left", predicate="within")
    hit = hit[~hit.index.duplicated()]          # a point on a shared edge can hit twice
    result = hit[col]
    missing = result.isna()
    if missing.any():
        near = gpd.sjoin_nearest(pts[missing].to_crs(config.AREA_CRS),
                                 hint[[col, "geometry"]].to_crs(config.AREA_CRS),
                                 how="left")
        near = near[~near.index.duplicated()]
        result.loc[missing] = near[col]
    return result


def title_name(census_name: str, fixes: dict) -> str:
    """'TOBA TEK SINGH' -> 'Toba Tek Singh', unless a fix says otherwise."""
    return fixes.get(census_name, census_name.title())


# ---------------------------------------------------------------------------
# The assignment cascade
# ---------------------------------------------------------------------------

def assign_tehsil(row, census_by_prov, overrides):
    """
    Decide which 2023 district a tehsil belongs to.

    Returns (district_2023, method, confidence). Rules, most certain first:
        1. override        a human decision in tehsil_assignment_overrides.csv
        2. exact           its name matches exactly one census tehsil in the province
        3. exact+hint      several match; pick the one in its old district
        4. fuzzy+hint      a close spelling whose district equals its old district
        5. old_district    its old district still exists under the same name
    Anything left is returned as unassigned and stops the build.
    """
    prov, key, old = row["province_code"], row["key"], row["old_district"]
    old_key = match_key(row["old_district_census"])  # old district, census spelling

    # 1. Human overrides always win.
    o = overrides.get((prov, old, row["tehsil_name"]))
    if o is not None:
        return o["district_2023"], "override", o["confidence"]

    # Gilgit-Baltistan isn't in Census 2023: its districts come from the hint layer.
    if prov == "GB":
        return old.upper(), "hint_layer", "high"

    census = census_by_prov.get(prov)
    if census is None:
        return None, "unassigned", ""

    # 2-3. Exact name match.
    cands = census[census["key"] == key]["DISTRICT"].unique()
    if len(cands) == 1:
        return cands[0], "exact", "high"
    if len(cands) > 1:
        same = [d for d in cands if match_key(d) == old_key]
        if same:
            return same[0], "exact+hint", "high"

    # 4. Fuzzy match, accepted only if it agrees with the old district.
    #    LESSON: get_close_matches returns the closest strings, best first.
    for k in get_close_matches(key, census["key"].unique().tolist(), n=5, cutoff=0.6):
        districts = census[census["key"] == k]["DISTRICT"].unique()
        same = [d for d in districts if match_key(d) == old_key]
        if same:
            return same[0], "fuzzy+hint", "high"

    # 5. Old district still exists under the same name.
    same_name = [d for d in census["DISTRICT"].unique() if match_key(d) == old_key]
    if same_name:
        return same_name[0], "old_district", "medium"

    return None, "unassigned", ""


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main():
    report = []

    # ---- 1. Load shapes ---------------------------------------------------
    tehsils = gpd.read_file(config.TEHSIL_SHAPES).to_crs("EPSG:4326")
    tehsils["tehsil_name"] = tehsils["shapeName"].str.title()
    hint_prov = gpd.read_file(config.HINT_PROVINCES).to_crs("EPSG:4326")
    hint_prov["province_code"] = hint_prov["shapeISO"].map(config.PROVINCE_CODES)
    hint_dist = gpd.read_file(config.HINT_DISTRICTS).to_crs("EPSG:4326")

    # ---- 2. Province and old district for each tehsil --------------------
    tehsils["province_code"] = locate(tehsils, hint_prov, "province_code")
    tehsils["old_district"] = locate(tehsils, hint_dist, "shapeName")
    tehsils["key"] = tehsils["tehsil_name"].map(match_key)

    # Translate old district names into census spelling ("Sheikhpura" ->
    # "SHEIKHUPURA") so the rules below can compare them.
    sp = pd.read_csv(config.REFERENCE / "hint_district_spellings.csv")
    tehsils["old_district_census"] = tehsils["old_district"].replace(
        dict(zip(sp["hint_name"], sp["census_name"])))

    # Areas lying mostly outside every hint district are kept as separate
    # "special areas" with no statistics, rather than forced into a district.
    union = hint_dist.to_crs(config.AREA_CRS).union_all()
    proj = tehsils.to_crs(config.AREA_CRS)
    outside_share = proj.geometry.difference(union).area / proj.area
    is_special = outside_share > 0.9
    special = tehsils[is_special].copy()
    tehsils = tehsils[~is_special].copy()

    # ---- 3. Census tehsil names, grouped by province ---------------------
    t01 = pyreadr.read_r(config.CENSUS_DIR / "TABLE_01.RData")["TABLE_01"]
    t01 = t01[t01["REGION"] == "OVERALL"].copy()
    t01["province_code"] = t01["PROVINCE"].map(config.CENSUS_PROVINCES)
    t01["key"] = t01["TEHSIL"].map(match_key)
    # LESSON: a dict comprehension builds a dict in one line:
    #     {key_expression: value_expression for item in items}
    census_by_prov = {p: g for p, g in t01.groupby("province_code")}

    ov = pd.read_csv(config.REFERENCE / "tehsil_assignment_overrides.csv", dtype=str).fillna("")
    overrides = {(r.province_code, r.old_district, r.tehsil_name): r
                 for r in ov.itertuples(index=False)}
    overrides = {k: {"district_2023": v.district_2023, "confidence": v.confidence}
                 for k, v in overrides.items()}

    # ---- 4. Run the cascade on every tehsil ------------------------------
    results = tehsils.apply(lambda r: assign_tehsil(r, census_by_prov, overrides), axis=1)
    # `results` is a column of 3-item tuples; unpack it into three columns.
    tehsils[["district_2023", "method", "confidence"]] = pd.DataFrame(
        results.tolist(), index=tehsils.index)

    unassigned = tehsils[tehsils["method"] == "unassigned"]
    if not unassigned.empty:
        print(unassigned[["province_code", "old_district", "tehsil_name"]].to_string())
        raise SystemExit(f"{len(unassigned)} tehsils unassigned: add them to "
                         "tehsil_assignment_overrides.csv")

    used = {(r.province_code, r.old_district, r.tehsil_name) for r in tehsils.itertuples()}
    stale = [k for k in overrides if k not in used]
    if stale:
        report.append(f"WARNING: {len(stale)} overrides matched no tehsil: {stale}")

    # ---- 5. Names and IDs -------------------------------------------------
    disp = pd.read_csv(config.REFERENCE / "district_display_names.csv")
    fixes = dict(zip(disp["source_name"], disp["display_name"]))
    tehsils["district_name"] = tehsils["district_2023"].map(lambda n: title_name(n, fixes))
    tehsils["district_id"] = tehsils["province_code"] + "-" + tehsils["district_name"].map(make_slug)

    # ---- 6. Dissolve tehsils into districts ------------------------------
    # LESSON: dissolve() is groupby() for shapes: rows sharing the same
    # district_id are merged into one polygon, and other columns are
    # combined using `aggfunc` ("first" keeps the first value).
    districts = tehsils.dissolve(
        by="district_id",
        aggfunc={"district_name": "first", "province_code": "first",
                 "district_2023": "first"},
    ).reset_index()
    districts = districts.rename(columns={"district_2023": "census_name"})
    districts["province_name"] = districts["province_code"].map(config.PROVINCE_NAMES)
    districts["in_census_2023"] = districts["province_code"].isin(config.CENSUS_PROVINCES.values())
    districts.loc[~districts["in_census_2023"], "census_name"] = ""
    districts["area_km2"] = area_km2(districts)
    pts = districts.representative_point()
    districts["label_lon"], districts["label_lat"] = pts.x.round(4), pts.y.round(4)

    # How confident is the district's outline? Its weakest tehsil decides.
    rank = {"high": 3, "medium": 2, "low": 1}
    worst = tehsils.groupby("district_id")["confidence"].apply(
        lambda s: min(s, key=lambda c: rank.get(c, 0)))
    districts["boundary_confidence"] = districts["district_id"].map(worst)

    if districts["district_id"].duplicated().any():
        raise SystemExit("Duplicate district_id")

    # ---- 7. Every census district must have a shape ----------------------
    census_d = t01.groupby(["province_code", "DISTRICT"]).size().reset_index()[["province_code", "DISTRICT"]]
    have = set(zip(districts["province_code"], districts["census_name"]))
    missing = [(p, d) for p, d in census_d.itertuples(index=False) if (p, d) not in have]

    # ---- 8. Provinces, from districts ------------------------------------
    provinces = districts.dissolve(by="province_code", aggfunc={"province_name": "first"}).reset_index()

    # ---- 9. Special areas -------------------------------------------------
    special["area_id"] = "XX-" + special["tehsil_name"].map(make_slug)
    special["area_name"] = special["tehsil_name"]
    special["note"] = ("Shown as named in the source tehsil layer. Lies outside all "
                       "district boundaries; no statistics are attached.")
    special = special[["area_id", "area_name", "note", "geometry"]]

    # ---- 10. Name lookup must stay unambiguous ---------------------------
    aliases = pd.read_csv(config.REFERENCE / "district_aliases.csv", dtype=str).fillna("")
    linked = aliases[aliases["district_id"] != ""]
    bad = linked[~linked["district_id"].isin(districts["district_id"])]
    if not bad.empty:
        raise SystemExit(f"Aliases point to unknown district_ids:\n{bad}")
    build_lookup(districts.rename(columns={"census_name": "source_name"}), linked)

    # ---- 11. Write --------------------------------------------------------
    out = config.PROCESSED
    out.mkdir(parents=True, exist_ok=True)
    dcols = ["district_id", "district_name", "census_name", "province_code",
             "province_name", "in_census_2023", "area_km2", "label_lon",
             "label_lat", "boundary_confidence"]
    districts = districts[dcols + ["geometry"]].sort_values("district_id")
    districts.drop(columns="geometry").to_csv(out / "districts.csv", index=False)

    tcols = ["tehsil_name", "province_code", "old_district", "district_id",
             "district_name", "method", "confidence"]
    tehsils[tcols].sort_values(["district_id", "tehsil_name"]).to_csv(out / "tehsils.csv", index=False)

    # Simplify for the web: 0.003 degrees is roughly 300 m, invisible at
    # district zoom but cuts file size a lot. preserve_topology keeps
    # shapes valid (no self-crossing lines).
    for gdf, name in [(districts, "districts"), (provinces, "provinces"), (special, "special_areas")]:
        web = gdf.copy()
        web["geometry"] = web.simplify(0.003, preserve_topology=True)
        web.to_file(out / f"{name}.geojson", driver="GeoJSON")

    # ---- 12. Report ------------------------------------------------------
    report.insert(0, f"Boundaries: {config.BOUNDARY_CITATION}")
    report.append(f"Tehsils: {len(tehsils)} assigned, {len(special)} special area(s)")
    report.append("Assignment method counts:\n" + tehsils["method"].value_counts().to_string())
    report.append("\nDistricts per province:\n" + districts.groupby("province_code").size().to_string())
    report.append(f"\nTotal districts: {len(districts)}")
    report.append(f"Census districts without a shape: {len(missing)} {missing}")
    report.append("Districts with low-confidence outlines: "
                  + ", ".join(districts.loc[districts["boundary_confidence"] == "low", "district_name"]))
    report.append(f"Special areas: {special['area_name'].tolist()}")
    text = "\n".join(report)
    (out / "build_report.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
