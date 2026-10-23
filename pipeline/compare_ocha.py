"""
compare_ocha.py: check OCHA COD-AB districts against Zila Atlas districts.

Run AFTER you put the OCHA files in data/raw/ocha_codab/ :

    python pipeline/compare_ocha.py
    python pipeline/compare_ocha.py --layer path/to/some_adm2_layer.geojson   # any ADM2 layer

It does not change any district, ID or alias. It only writes two reports for
a human to read and confirm (our rule: no automatic fuzzy matching of names):

    data/processed/ocha_crosswalk_candidates.csv   one row per Zila Atlas district
    data/processed/ocha_unmatched.csv              OCHA districts nobody claimed

LESSON: two independent kinds of evidence beat one.
    1. NAME evidence: do the spellings agree (after the usual cleaning)?
    2. SHAPE evidence: do the two polygons cover the same ground?
    A "confirmed" row needs both. A name match with no shape overlap (or the
    reverse) is exactly the kind of row a person should look at.

LESSON: overlap is measured two ways.
    share_of_ours   = overlap area / OUR district's area
    share_of_theirs = overlap area / THEIR district's area
    If both are near 1.0 the shapes are the same place. If only one is high,
    one district has been split or merged. Areas are measured in an equal-area
    projection (config.AREA_CRS), never in raw lon/lat degrees.
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config
from pipeline.names import build_lookup, match_key

OCHA_DIR = config.RAW / "ocha_codab"

# OCHA, WFP and geoBoundaries each name their columns differently.
# We try these in order and use the first one that exists.
NAME_COLUMNS = ["ADM2_EN", "admin2Name_en", "ADM2_NAME", "shapeName"]
CODE_COLUMNS = ["ADM2_PCODE", "admin2Pcode", "shapeID"]
PARENT_COLUMNS = ["ADM1_EN", "admin1Name_en", "ADM1_NAME"]

# Zila Atlas edges are approximate (2017 tehsils merged), so even a correct
# match rarely overlaps 100%. 0.80 is a starting point; change it with --threshold.
DEFAULT_SAME_PLACE = 0.80


def first_present(columns, candidates, what):
    """Return the first candidate that is a real column, or stop with a clear message."""
    for c in candidates:
        if c in columns:
            return c
    raise SystemExit(f"Could not find a {what} column. Columns are: {list(columns)}")


def find_layer(explicit):
    """Use --layer if given, otherwise look for an ADM2 file in data/raw/ocha_codab/."""
    if explicit:
        return Path(explicit)
    hits = []
    for pattern in ("*adm2*.shp", "*adm2*.geojson", "*adm2*.gpkg"):
        hits += sorted(OCHA_DIR.rglob(pattern))
    if not hits:
        raise SystemExit(
            f"No ADM2 layer found under {OCHA_DIR}.\n"
            "Download 'Pakistan - Subnational Administrative Boundaries' (shapefile zip)\n"
            "from https://data.humdata.org/dataset/cod-ab-pak, unzip it into that folder, and rerun."
        )
    return hits[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--layer", help="path to an ADM2 layer (default: search data/raw/ocha_codab)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_SAME_PLACE,
                        help="overlap share (0 to 1) at which two shapes count as the same place")
    args = parser.parse_args()
    same_place = args.threshold

    layer_path = find_layer(args.layer)
    print(f"Reading OCHA-style layer: {layer_path}")
    theirs = gpd.read_file(layer_path).to_crs("EPSG:4326")
    name_col = first_present(theirs.columns, NAME_COLUMNS, "district name")
    code_col = first_present(theirs.columns, CODE_COLUMNS, "district code")
    parent_col = next((c for c in PARENT_COLUMNS if c in theirs.columns), None)
    theirs = theirs.rename(columns={name_col: "their_name", code_col: "their_code"})
    theirs["their_parent"] = theirs[parent_col] if parent_col else ""
    theirs["geometry"] = theirs.geometry.make_valid()   # repairs tiny self-crossings
    print(f"  {len(theirs)} districts in that layer (Zila Atlas has 156)")

    ours = gpd.read_file(config.PROCESSED / "districts.geojson").to_crs("EPSG:4326")
    ours["geometry"] = ours.geometry.make_valid()
    master = pd.read_csv(config.PROCESSED / "districts.csv")
    aliases = pd.read_csv(config.REFERENCE / "district_aliases.csv")
    lookup = build_lookup(master, aliases)       # cleaned name -> our district_id

    # ---- shape evidence: intersect every pair that overlaps ----
    a = ours[["district_id", "geometry"]].to_crs(config.AREA_CRS)
    b = theirs[["their_code", "geometry"]].to_crs(config.AREA_CRS)
    a["our_area"] = a.area
    b["their_area"] = b.area
    pieces = gpd.overlay(a, b, how="intersection", keep_geom_type=True)
    pieces["overlap"] = pieces.area
    pieces["share_of_ours"] = pieces["overlap"] / pieces["our_area"]
    pieces["share_of_theirs"] = pieces["overlap"] / pieces["their_area"]

    # For each of our districts, keep the OCHA district it overlaps most.
    # LESSON: sort_values + drop_duplicates is a common "best row per group" idiom.
    best = (pieces.sort_values("overlap", ascending=False)
                  .drop_duplicates("district_id")
                  [["district_id", "their_code", "share_of_ours", "share_of_theirs"]])

    out = master[["district_id", "district_name", "province_code"]].merge(best, on="district_id", how="left")
    out = out.merge(theirs[["their_code", "their_name", "their_parent"]], on="their_code", how="left")

    # ---- name evidence ----
    # Does the OCHA name, once cleaned, point at THIS district in our lookup?
    out["name_agrees"] = [
        isinstance(n, str) and lookup.get(match_key(n)) == did
        for n, did in zip(out["their_name"], out["district_id"])
    ]
    out["shape_agrees"] = (out["share_of_ours"] >= same_place) & (out["share_of_theirs"] >= same_place)

    def verdict(row):
        if row["name_agrees"] and row["shape_agrees"]:
            return "confirmed"
        if row["shape_agrees"]:
            return "shape_only: same place, different name. Add alias if you agree"
        if row["name_agrees"]:
            return "name_only: same name, different shape. Check for a split or merge"
        return "review: neither name nor shape agrees"

    out["status"] = out.apply(verdict, axis=1)
    for col in ("share_of_ours", "share_of_theirs"):
        out[col] = out[col].round(3)

    # OCHA districts that are nobody's best match = candidates for new/split districts.
    claimed = set(out["their_code"].dropna())
    unmatched = theirs.loc[~theirs["their_code"].isin(claimed),
                           ["their_code", "their_name", "their_parent"]]

    config.PROCESSED.mkdir(exist_ok=True)
    out.to_csv(config.PROCESSED / "ocha_crosswalk_candidates.csv", index=False)
    unmatched.to_csv(config.PROCESSED / "ocha_unmatched.csv", index=False)

    print("\nResult for the 156 Zila Atlas districts:")
    print(out["status"].str.split(":").str[0].value_counts().to_string())
    print(f"\nOCHA districts not claimed by any Zila Atlas district: {len(unmatched)}")
    print("Reports: data/processed/ocha_crosswalk_candidates.csv, ocha_unmatched.csv")


if __name__ == "__main__":
    main()
