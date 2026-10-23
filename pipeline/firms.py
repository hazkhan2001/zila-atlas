"""
firms.py: validate the curated firms table and rank the top firms per province.

Run from the project folder:
    python pipeline/firms.py                          # uses data/reference/firms.csv
    python pipeline/firms.py tests/firms_example.csv  # try it on the example file

THE RULES (each one protects credibility with economists and journalists)
    1. Every row says what kind of entity it is (listed, state-owned, private...).
    2. A revenue number must have a source and a fiscal year. No source, no number.
    3. Private firms that don't disclose are marked 'undisclosed', never estimated.
    4. Market cap must carry the date it was measured on.
    5. Province and district codes must exist in the master tables.

OUTPUT
    data/processed/firms_top3.csv: top 3 per province, in two views:
        hq          ranked among firms headquartered in the province
        operations  ranked among firms that operate in the province
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config

# LESSON: a set {...} is like a list but with no duplicates and very fast
# "is x in it?" checks. Perfect for lists of allowed values.
ENTITY_TYPES = {"listed", "soe_listed", "soe_unlisted", "private", "foreign_subsidiary"}
REVENUE_STATUSES = {"reported", "undisclosed"}
CONFIDENCE = {"high", "medium", "low"}
REQUIRED = ["firm_id", "firm_name", "entity_type", "hq_province_code",
            "revenue_status", "source", "basis", "confidence", "last_verified"]
FINANCIAL_SECTORS = {"Banking"}   # ranked by total assets, not revenue
NUMERIC = ["revenue_pkr_mn", "total_assets_pkr_mn", "market_cap_pkr_mn"]


def load_firms(path: Path) -> pd.DataFrame:
    # dtype=str reads everything as text first, so a CUIN like "0041857" keeps
    # its leading zeros. We convert the numeric columns ourselves below.
    df = pd.read_csv(path, dtype=str).fillna("")
    for col in NUMERIC:
        # errors="coerce" turns anything that isn't a number into NaN (blank),
        # which the validator then catches instead of crashing.
        df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="coerce")
    return df


def validate(df: pd.DataFrame) -> list:
    """Return a list of problems. An empty list means the table is valid."""
    problems = []
    valid_provinces = set(config.PROVINCE_CODES.values())
    districts = pd.read_csv(config.PROCESSED / "districts.csv")
    valid_districts = set(districts["district_id"])

    if df["firm_id"].duplicated().any():
        dupes = df.loc[df["firm_id"].duplicated(), "firm_id"].tolist()
        problems.append(f"duplicate firm_id: {dupes}")

    # LESSON: .iterrows() walks the table one row at a time. It's slow on big
    # tables, but this one has a few dozen rows and readability wins.
    for _, row in df.iterrows():
        tag = row["firm_id"] or row["firm_name"] or "(blank row)"

        for col in REQUIRED:
            if row[col] == "":
                problems.append(f"{tag}: missing {col}")

        if row["entity_type"] not in ENTITY_TYPES:
            problems.append(f"{tag}: entity_type '{row['entity_type']}' not in {sorted(ENTITY_TYPES)}")
        if row["revenue_status"] not in REVENUE_STATUSES:
            problems.append(f"{tag}: revenue_status must be one of {sorted(REVENUE_STATUSES)}")
        if row["confidence"] not in CONFIDENCE:
            problems.append(f"{tag}: confidence must be one of {sorted(CONFIDENCE)}")

        # Rule 2 and 3: reported means a number + a fiscal year; undisclosed means no number.
        has_rev = pd.notna(row["revenue_pkr_mn"])
        is_bank = row["sector"] in FINANCIAL_SECTORS
        if is_bank and pd.isna(row["total_assets_pkr_mn"]):
            problems.append(f"{tag}: banks need total_assets_pkr_mn")
        if row["revenue_status"] == "reported" and not is_bank:
            if not has_rev:
                problems.append(f"{tag}: revenue_status is 'reported' but revenue_pkr_mn is blank")
            if row["fiscal_year_end"] == "":
                problems.append(f"{tag}: reported revenue needs fiscal_year_end")
        if row["source"] and not row["source"].startswith("http"):
            problems.append(f"{tag}: source must be a link")
        if row["revenue_status"] == "undisclosed" and has_rev:
            problems.append(f"{tag}: 'undisclosed' firms must not carry an estimated revenue")

        # Rule 4: market cap needs its date, and only listed entities have one.
        if pd.notna(row["market_cap_pkr_mn"]):
            if row["market_cap_date"] == "":
                problems.append(f"{tag}: market_cap_pkr_mn needs market_cap_date")
            if row["entity_type"] not in {"listed", "soe_listed"}:
                problems.append(f"{tag}: only listed entities can have a market cap")
        if row["entity_type"] in {"listed", "soe_listed"} and row["psx_ticker"] == "":
            problems.append(f"{tag}: listed entity needs psx_ticker")

        # Rule 5: codes must exist.
        if row["hq_province_code"] and row["hq_province_code"] not in valid_provinces:
            problems.append(f"{tag}: unknown hq_province_code '{row['hq_province_code']}'")
        if row["hq_district_id"] and row["hq_district_id"] not in valid_districts:
            problems.append(f"{tag}: unknown hq_district_id '{row['hq_district_id']}'")
        for code in filter(None, row["operating_province_codes"].split(";")):
            if code.strip() not in valid_provinces:
                problems.append(f"{tag}: unknown operating province '{code}'")

    return problems


def top_n(df: pd.DataFrame, n: int = 3, metric: str = "revenue_pkr_mn") -> pd.DataFrame:
    """
    Rank firms within each province, in both the 'hq' and 'operations' views.

    LESSON: .explode() turns a list inside one cell into several rows.
        firm A, operating in ["PB", "SD"]  ->  (A, PB) and (A, SD)
    That lets one firm count toward every province it operates in.
    """
    ranked = df[df[metric].notna()].copy()

    hq = ranked.assign(province_code=ranked["hq_province_code"], view="hq")

    ops = ranked.assign(
        province_code=ranked["operating_province_codes"].str.split(";")
    ).explode("province_code")
    ops["province_code"] = ops["province_code"].str.strip()
    ops = ops[ops["province_code"] != ""].assign(view="operations")

    both = pd.concat([hq, ops], ignore_index=True)
    # Sort biggest first, then keep the first n rows of each (view, province).
    both = both.sort_values(metric, ascending=False)
    both["rank"] = both.groupby(["view", "province_code"]).cumcount() + 1
    top = both[both["rank"] <= n]

    cols = ["view", "province_code", "rank", "firm_id", "firm_name", "group_name",
            "entity_type", "sector", metric, "fiscal_year_end",
            "market_cap_pkr_mn", "market_cap_date", "source", "confidence"]
    return top[cols].sort_values(["view", "province_code", "rank"])


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else config.REFERENCE / "firms.csv"
    df = load_firms(path)
    print(f"Loaded {len(df)} firms from {path}")

    problems = validate(df)
    if problems:
        print(f"\n{len(problems)} problem(s) found, nothing written:")
        for p in problems:
            print("  -", p)
        sys.exit(1)  # a non-zero exit code tells other tools "this failed"

    if df.empty:
        print("Table is empty: valid, nothing to rank yet.")
        return

    # Website export: every firm with the metric it is ranked by.
    import json
    site_rows = []
    for _, r in df.iterrows():
        bank = r["sector"] in FINANCIAL_SECTORS
        site_rows.append({
            "firm_name": r["firm_name"], "group": r["group_name"], "entity_type": r["entity_type"],
            "psx_ticker": r["psx_ticker"], "sector": r["sector"],
            "hq_province_code": r["hq_province_code"],
            "operating_province_codes": r["operating_province_codes"],
            "metric": "total_assets" if bank else "revenue",
            "revenue_pkr_mn": None if bank or pd.isna(r["revenue_pkr_mn"]) else float(r["revenue_pkr_mn"]),
            "total_assets_pkr_mn": float(r["total_assets_pkr_mn"]) if bank else None,
            "period_end": r["fiscal_year_end"], "basis": r["basis"],
            "source_url": r["source"], "confidence": r["confidence"],
        })
    as_of = max(df["last_verified"])
    (config.PROCESSED / "firms_ranked.json").write_text(
        json.dumps({"as_of": as_of, "firms": site_rows}, separators=(",", ":")))

    nonfin = df[~df["sector"].isin(FINANCIAL_SECTORS)]
    top = top_n(nonfin)
    out = config.PROCESSED / "firms_top3.csv"
    top.to_csv(out, index=False)
    print(f"Valid. Wrote {len(top)} ranked rows to {out}")
    print(top[["view", "province_code", "rank", "firm_name", "revenue_pkr_mn"]].to_string(index=False))

    undisclosed = df[df["revenue_status"] == "undisclosed"]
    if not undisclosed.empty:
        print(f"\nShown separately as 'revenue undisclosed': {', '.join(undisclosed['firm_name'])}")


if __name__ == "__main__":
    main()
