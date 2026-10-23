"""
build_national.py: validate the national economy and provincial health tables.

Run from the project folder:
    python pipeline/build_national.py

INPUTS (data/reference/national/, all hand-curated from cited sources)
    stats_*.csv          one headline figure per row, one file per research batch
    series_*.csv         short annual histories (GDP growth, inflation, policy rate...)
    creditors.csv        external public debt by creditor
    province_health.csv  fertility and child mortality by province, by survey

OUTPUT
    data/processed/national.json   everything above, checked, for the website

WHY THESE ARE HAND-CURATED TABLES
    Most of these numbers are published as PDFs or press releases, a few
    times a year. Typing them into a table, each with its source link and
    date, is faster and more honest than a scraper that breaks whenever a
    PDF layout changes. The validator below is what keeps them honest:
    no number gets onto the site without a period and a link.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config

NAT = config.REFERENCE / "national"
TEXT_UNITS = {"rating", "text"}          # values allowed to be words, e.g. "Caa1"
CONFIDENCE = {"high", "medium", "low"}


def check(df: pd.DataFrame, name: str, required: list, numeric: list) -> list:
    """Return a list of problems with one table."""
    problems = []
    for i, row in df.iterrows():
        tag = f"{name} row {i + 2}"   # +2: header row, and humans count from 1
        for col in required:
            if str(row.get(col, "")).strip() == "":
                problems.append(f"{tag}: missing {col}")
        url = str(row.get("source_url", ""))
        if url and not url.startswith("http"):
            problems.append(f"{tag}: source_url must be a link")
        for col in numeric:
            if row.get("unit") in TEXT_UNITS:
                continue
            try:
                float(row[col])
            except (TypeError, ValueError):
                problems.append(f"{tag}: {col} '{row[col]}' is not a number")
        if "confidence" in df.columns and row.get("confidence") not in CONFIDENCE:
            problems.append(f"{tag}: confidence must be one of {sorted(CONFIDENCE)}")
    return problems


def num(v):
    """Convert to float when possible, else keep the text (for ratings)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def main():
    read = lambda f: pd.read_csv(NAT / f, dtype=str).fillna("")
    # Each research batch is its own file (stats_debt.csv, stats_prices.csv ...).
    # LESSON: glob("stats_*.csv") finds every file matching the pattern.
    def batch(pattern, columns):
        files = sorted(NAT.glob(pattern))
        if not files:                     # nothing researched yet: an empty table
            return pd.DataFrame(columns=columns)
        return pd.concat([read(f.name) for f in files], ignore_index=True)
    stats = batch("stats_*.csv", ["indicator_id"])
    series = batch("series_*.csv", ["series_id", "fiscal_year", "value", "unit", "source_url"])
    creditors = read("creditors.csv")
    health = read("province_health.csv")

    problems = []
    problems += check(stats, "stats_*.csv",
                      ["indicator_id", "label", "category", "value", "unit", "period", "source_url"],
                      ["value"])
    problems += check(series, "series_*.csv",
                      ["series_id", "fiscal_year", "value", "unit", "source_url"], ["value"])
    problems += check(creditors, "creditors.csv",
                      ["creditor", "creditor_type", "value_usd_bn", "period", "source_url"],
                      ["value_usd_bn"])
    problems += check(health, "province_health.csv",
                      ["region_code", "indicator", "value", "survey", "survey_year", "source_url"],
                      ["value"])
    if stats["indicator_id"].duplicated().any():
        problems.append(f"stats.csv: duplicate ids {stats.loc[stats['indicator_id'].duplicated(), 'indicator_id'].tolist()}")
    dup = series.duplicated(["series_id", "fiscal_year"])
    if dup.any():
        problems.append(f"series.csv: duplicate years {series.loc[dup, ['series_id', 'fiscal_year']].values.tolist()}")

    if problems:
        print(f"{len(problems)} problem(s), nothing written:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    # LESSON: .to_dict("records") turns a table into a list of dicts, one
    # per row: exactly the shape a JSON file (and JavaScript) likes.
    stat_rows = stats.to_dict("records")
    for r in stat_rows:
        r["value"] = num(r["value"])

    series_out = {}
    for sid, grp in series.groupby("series_id"):
        grp = grp.sort_values("fiscal_year")
        series_out[sid] = {
            "unit": grp["unit"].iloc[0],
            "source_url": grp["source_url"].iloc[0],
            "points": [{"fy": fy, "value": float(v)} for fy, v in zip(grp["fiscal_year"], grp["value"])],
        }

    cred = creditors.copy()
    cred["value_usd_bn"] = cred["value_usd_bn"].astype(float)
    cred = cred.sort_values("value_usd_bn", ascending=False)

    h = health.copy()
    h["value"] = h["value"].astype(float)

    payload = {
        "stats": stat_rows,
        "series": series_out,
        "creditors": cred.to_dict("records"),
        "health": h.to_dict("records"),
    }
    stats.to_csv(NAT / "stats.csv", index=False)      # combined copies, for download
    series.to_csv(NAT / "series.csv", index=False)
    (config.PROCESSED / "national.json").write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Valid: {len(stats)} figures, {len(series_out)} series, "
          f"{len(cred)} creditors, {len(h)} health values -> data/processed/national.json")


if __name__ == "__main__":
    main()
