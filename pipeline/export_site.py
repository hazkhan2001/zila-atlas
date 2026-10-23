"""
export_site.py: package processed data into compact files for the website.

Run from the project folder (after the other build scripts):
    python pipeline/export_site.py

OUTPUTS (site/data/)
    districts.geojson, provinces.geojson, special_areas.geojson   map shapes
    indicators.json    catalog + every district's values + province/national totals
    firms.json         ranked firms per province (if the firms table has rows)
    *.csv              copies of the main tables for people who want the raw data

WHY A SEPARATE EXPORT STEP?
    The pipeline's processed files are built for analysis (full precision,
    many columns). A website wants small files: fewer decimals, only the
    fields the page uses. Keeping this step separate means you can change
    the site's needs without touching the analysis outputs.
"""

import json
import math
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import set_precision

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config


def clean(value):
    """Make a value JSON-safe: NaN becomes None (JSON null), numpy types become Python."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):          # numpy int64/float64 -> int/float
        value = value.item()
        if isinstance(value, float) and math.isnan(value):
            return None
    return value


def write_shapes(name: str, keep: list):
    """Copy a GeoJSON with coordinates rounded to ~10 m and only `keep` fields."""
    gdf = gpd.read_file(config.PROCESSED / f"{name}.geojson")[keep + ["geometry"]]
    # set_precision snaps coordinates to a grid. 0.0001 degrees ~ 11 metres.
    gdf["geometry"] = set_precision(gdf.geometry.values, 0.0001)
    gdf.to_file(config.SITE_DATA / f"{name}.geojson", driver="GeoJSON",
                COORDINATE_PRECISION=4)


def main():
    out = config.SITE_DATA
    out.mkdir(parents=True, exist_ok=True)

    write_shapes("districts", ["district_id", "district_name", "province_code"])
    write_shapes("provinces", ["province_code", "province_name"])
    write_shapes("special_areas", ["area_id", "area_name", "note"])

    # ---- Indicators ------------------------------------------------------
    cat = pd.read_csv(config.PROCESSED / "indicator_catalog.csv")
    wide = pd.read_csv(config.PROCESSED / "indicators_wide.csv", index_col="district_id")
    agg = pd.read_csv(config.PROCESSED / "aggregates.csv", index_col="area_code")
    dist = pd.read_csv(config.PROCESSED / "districts.csv", index_col="district_id")

    ids = cat["indicator_id"].tolist()
    payload = {
        "catalog": [{k: clean(v) for k, v in row.items()} for row in cat.to_dict("records")],
        "provinces": config.PROVINCE_NAMES,
        "districts": {},
        "aggregates": {},
        "sources": {"census": config.CENSUS_CITATION, "boundaries": config.BOUNDARY_CITATION},
    }
    for did, row in dist.iterrows():
        values = wide.loc[did] if did in wide.index else pd.Series(dtype=object)
        payload["districts"][did] = {
            "name": row["district_name"],
            "province": row["province_code"],
            "in_census": bool(row["in_census_2023"]),
            "boundary_confidence": row["boundary_confidence"],
            "note": clean(values.get("data_note")) or None,
            "top_language": clean(values.get("top_language")),
            # A list in catalog order is much smaller than a dict of names.
            "v": [clean(values.get(i)) for i in ids],
        }
    for code, row in agg.iterrows():
        payload["aggregates"][code] = [clean(row.get(i)) for i in ids]

    with open(out / "indicators.json", "w") as f:
        # separators=(",", ":") drops spaces: smaller file, same data.
        json.dump(payload, f, separators=(",", ":"))

    # ---- Firms -----------------------------------------------------------
    firms_path = config.PROCESSED / "firms_ranked.json"
    if firms_path.exists():
        shutil.copy(firms_path, out / "firms.json")
    else:
        (out / "firms.json").write_text(json.dumps({"firms": [], "as_of": None}))

    # ---- National economy and provincial health ------------------------
    nat = config.PROCESSED / "national.json"
    if nat.exists():
        shutil.copy(nat, out / "national.json")

    # ---- Raw tables for download ----------------------------------------
    for name in ["districts.csv", "indicators_wide.csv", "indicator_catalog.csv",
                 "aggregates.csv", "tehsils.csv"]:
        shutil.copy(config.PROCESSED / name, out / name)
    if (config.REFERENCE / "firms.csv").exists():
        shutil.copy(config.REFERENCE / "firms.csv", out / "firms.csv")
    for name in ["stats.csv", "series.csv", "creditors.csv", "province_health.csv"]:
        src_csv = config.REFERENCE / "national" / name
        if src_csv.exists():
            shutil.copy(src_csv, out / f"national_{name}")

    # ---- The page itself ------------------------------------------------
    # The site's source lives in site/src/. Embedded viewers only allow
    # stylesheets from Google Fonts, so MapLibre's CSS is pasted inline.
    src = (config.SITE / "src" / "index.html").read_text()
    maplibre_css = (config.SITE / "src" / "vendor" / "maplibre-gl.css").read_text()
    (config.SITE / "index.html").write_text(src.replace("/*__MAPLIBRE_CSS__*/", maplibre_css))

    for p in sorted(out.iterdir()):
        print(f"{p.name:28} {p.stat().st_size / 1024:8.1f} KB")


if __name__ == "__main__":
    main()
