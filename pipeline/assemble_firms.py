"""
assemble_firms.py: merge researched batches into the one firms table.

Run from the project folder:
    python pipeline/assemble_firms.py
    python pipeline/firms.py          # then validate and rank

Each batch in data/reference/firms_staging/ is one round of research
(e.g. banks, utilities). Keeping batches separate means you can always see
which research a figure came from; this script stitches them together into
data/reference/firms.csv, the table the rest of the pipeline uses.
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config
from pipeline.names import normalize_name

COLUMNS = ["firm_id", "firm_name", "group_name", "entity_type", "psx_ticker", "secp_cuin",
           "sector", "hq_province_code", "hq_district_id", "operating_province_codes",
           "fiscal_year_end", "revenue_status", "revenue_pkr_mn", "total_assets_pkr_mn",
           "market_cap_pkr_mn", "market_cap_date", "basis", "source", "confidence",
           "last_verified", "notes", "batch"]

# Head-office city -> district_id, so a firm can be placed on the map later.
CITY_DISTRICT = {
    "Karachi": "", "Lahore": "PB-LAHORE", "Islamabad": "IS-ISLAMABAD",
    "Rawalpindi": "PB-RAWALPINDI", "Multan": "PB-MULTAN", "Faisalabad": "PB-FAISALABAD",
    "Peshawar": "KP-PESHAWAR", "Quetta": "BA-QUETTA", "Muzaffarabad": "JK-MUZAFFARABAD",
    "Kohat": "KP-KOHAT", "Nowshera": "KP-NOWSHERA",
}


def main():
    frames = []
    for path in sorted((config.REFERENCE / "firms_staging").glob("*.csv")):
        df = pd.read_csv(path, dtype=str).fillna("")
        df["batch"] = path.stem
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True).fillna("")
    # LESSON: last_verified is stored with each row (the day a person checked the
    # figure). A blank means a brand-new row, so only then do we use today.
    raw["last_verified"] = raw["last_verified"].where(raw["last_verified"] != "", date.today().isoformat())

    out = pd.DataFrame({
        "firm_id": raw["psx_ticker"].where(raw["psx_ticker"] != "",
                                           raw["firm_name"].map(lambda n: normalize_name(n).upper().replace(" ", "-"))),
        "firm_name": raw["firm_name"],
        "group_name": raw["group_name"],
        "entity_type": raw["entity_type"],
        "psx_ticker": raw["psx_ticker"],
        "secp_cuin": "",
        "sector": raw["sector"],
        "hq_province_code": raw["hq_province_code"],
        # Karachi is seven districts and a head-office address is not geocoded yet,
        # so Karachi firms get no district for now rather than a guessed one.
        "hq_district_id": raw["hq_city"].map(CITY_DISTRICT).fillna(""),
        "operating_province_codes": raw["operating_province_codes"],
        "fiscal_year_end": raw["fiscal_year_end"],
        "revenue_status": "reported",
        "revenue_pkr_mn": raw["revenue_pkr_mn"],
        "total_assets_pkr_mn": raw["total_assets_pkr_mn"],
        "market_cap_pkr_mn": "",
        "market_cap_date": "",
        "basis": raw["basis"],
        "source": raw["source_url"],
        "confidence": raw["confidence"],
        "last_verified": raw["last_verified"],
        "notes": raw["notes"],
        "batch": raw["batch"],
    })[COLUMNS]

    dupes = out[out["firm_id"].duplicated(keep=False)]
    if not dupes.empty:
        raise SystemExit(f"Same firm in two batches:\n{dupes[['firm_id', 'batch']]}")

    out.to_csv(config.REFERENCE / "firms.csv", index=False)
    print(f"{len(out)} firms from {len(frames)} batches -> data/reference/firms.csv")
    print(out.groupby(["batch"]).size().to_string())


if __name__ == "__main__":
    main()
