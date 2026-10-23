"""
build_indicators.py: compute district indicators from Census 2023.

Run from the project folder (after build_districts.py):
    python pipeline/build_indicators.py

OUTPUTS (data/processed/)
    indicator_catalog.csv   one row per indicator: label, unit, meaning, source
    indicators_wide.csv     one row per district, one column per indicator
    indicators_long.csv     one row per (district, indicator): the tidy form
    aggregates.csv          the same indicators for each province and Pakistan

THE GOLDEN RULE: SUM COUNTS, THEN DIVIDE
    Census tables are at tehsil level. To get a district literacy rate you
    must add up literate people across tehsils and divide by the summed
    population. Averaging the tehsils' percentages would be wrong: it gives
    a tehsil of 5,000 people the same weight as one of 2 million.
    So every rate here is built from two counts (numerator, denominator),
    which also lets us compute province and national rates the same way.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyreadr

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline import config


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

SPELLINGS = {"ICT": "ISLAMABAD", "MALAKAND PROTECTED AREA": "MALAKAND",
             "TANDO ALLAHYAR": "TANDO AHYAR"}
_DISTRICT_PROVINCE = {}


def district_province() -> dict:
    """
    Census district name -> province code, from TABLE_01 (which has no blanks).

    LESSON: Some tables in the package leave PROVINCE blank on a few rows.
    groupby() silently DROPS rows whose group key is blank, so those people
    would vanish from the totals with no error. Since every census district
    belongs to exactly one province, we can fill the blanks safely.
    """
    if not _DISTRICT_PROVINCE:
        t = pyreadr.read_r(config.CENSUS_DIR / "TABLE_01.RData")["TABLE_01"]
        pairs = t[["DISTRICT", "PROVINCE"]].drop_duplicates()
        for d, p in zip(pairs["DISTRICT"].str.upper().str.strip(), pairs["PROVINCE"]):
            _DISTRICT_PROVINCE[d] = config.CENSUS_PROVINCES[p]
    return _DISTRICT_PROVINCE


def load(table: str) -> pd.DataFrame:
    """Read one census table, fix spellings and attach province codes."""
    df = pyreadr.read_r(config.CENSUS_DIR / f"{table}.RData")[table]
    # Different tables in the package spell a few districts differently.
    # Fix them here, once, so every table uses TABLE_01's spelling.
    dcol = "DISTRICT" if "DISTRICT" in df.columns else "District"
    df[dcol] = df[dcol].str.upper().str.strip().replace(SPELLINGS)
    df["province_code"] = df[dcol].map(district_province())
    if df["province_code"].isna().any():
        bad = df.loc[df["province_code"].isna(), dcol].unique()
        raise SystemExit(f"{table}: districts not found in TABLE_01: {bad}")
    if dcol != "DISTRICT":
        df = df.rename(columns={dcol: "DISTRICT"})
    return df


def by_district(df: pd.DataFrame, cols: list, district_col: str = "DISTRICT") -> pd.DataFrame:
    """Sum `cols` over all rows of each (province, district)."""
    return df.groupby(["province_code", district_col])[cols].sum(min_count=1)


# ---------------------------------------------------------------------------
# The indicator definitions
# ---------------------------------------------------------------------------
# LESSON: Instead of writing 27 near-identical blocks of code, we describe
# each indicator as data (a dict) and let one loop compute them all.
# Adding an indicator later means adding one entry here, nothing else.
#
#   num / den : names of count columns in the `counts` table built below
#   scale     : 100 for a percentage, 1 for a plain ratio
#   direction : is a higher value generally better, worse, or neither?
#               (the map uses this to pick a colour scale)

RATES = [
    # id, label, category, num, den, scale, unit, direction, description
    ("density", "Population density", "People", "pop", "area_census", 1,
     "people per km²", "neutral", "Population divided by census area"),
    ("urban_share", "Urban population", "People", "pop_urban", "pop_ur_den", 100,
     "%", "neutral", "Share of population living in areas classed urban"),
    ("sex_ratio", "Sex ratio", "People", "male", "female", 100,
     "males per 100 females", "neutral", "Males per 100 females"),
    ("under15_share", "Children under 15", "People", "age_u15", "age_all", 100,
     "%", "neutral", "Share of population aged under 15"),
    ("age65_share", "People aged 65+", "People", "age_65p", "age_all", 100,
     "%", "neutral", "Share of population aged 65 and above"),
    ("dependency_ratio", "Dependency ratio", "People", "age_dep", "age_1564", 100,
     "per 100 working-age", "worse",
     "People under 15 or over 64 per 100 people aged 15 to 64"),
    ("literacy", "Literacy rate (10+)", "Education", "lit10", "pop10", 100,
     "%", "better", "Share of people aged 10+ who can read and write"),
    ("literacy_female", "Female literacy (10+)", "Education", "lit10_f", "pop10_f", 100,
     "%", "better", "Share of females aged 10+ who can read and write"),
    ("literacy_male", "Male literacy (10+)", "Education", "lit10_m", "pop10_m", 100,
     "%", "better", "Share of males aged 10+ who can read and write"),
    ("out_of_school", "Out-of-school children (5 to 16)", "Education", "oosc", "age_5_16", 100,
     "%", "worse", "Children aged 5 to 16 not attending school (never enrolled or dropped out)"),
    ("never_school", "Never attended school (5+)", "Education", "never_all", "pop5", 100,
     "%", "worse", "Share of people aged 5+ who never attended school"),
    ("electricity", "Electric lighting", "Housing", "light_elec", "hh_t22", 100,
     "% of households", "better", "Households whose main source of lighting is electricity"),
    ("solar", "Solar lighting", "Housing", "light_solar", "hh_t22", 100,
     "% of households", "neutral", "Households whose main source of lighting is solar"),
    ("piped_gas", "Cooking with piped gas", "Housing", "fuel_gas", "hh_t22", 100,
     "% of households", "neutral", "Households cooking mainly with piped natural gas"),
    ("firewood", "Cooking with firewood", "Housing", "fuel_wood", "hh_t22", 100,
     "% of households", "worse", "Households cooking mainly with firewood"),
    ("water_inside", "Drinking water inside home", "Housing", "water_inside", "hh_t23", 100,
     "% of households", "better", "Households with their drinking-water source inside the dwelling"),
    ("tap_water", "Tap water", "Housing", "water_tap", "hh_t23", 100,
     "% of households", "better", "Households whose main drinking water is from a tap"),
    ("flush_toilet", "Flush toilet", "Housing", "toilet_flush", "hh_t24", 100,
     "% of households", "better", "Households with a flush toilet"),
    ("no_toilet", "No toilet", "Housing", "toilet_none", "hh_t24", 100,
     "% of households", "worse", "Households with no toilet facility"),
    ("owned_home", "Owner-occupied homes", "Housing", "owned", "hh_t25", 100,
     "% of households", "neutral", "Households living in a home they own"),
    ("one_room", "One-room homes", "Housing", "rooms1", "hh_t25", 100,
     "% of households", "worse", "Households living in a single room"),
    ("disability", "Disability prevalence", "Health", "disab", "pop_t16", 100,
     "%", "neutral", "Share of population reported as having a disability"),
]

# Indicators that are counts or come straight from the official district table.
DIRECT = [
    ("population", "Population (2023)", "People", "persons", "neutral",
     "Total population, Census 2023 (official district totals)"),
    ("population_2017", "Population (2017)", "People", "persons", "neutral",
     "Total population, Census 2017, as reported alongside the 2023 results"),
    ("growth_rate", "Annual growth 2017 to 2023", "People", "% per year", "neutral",
     "Average annual population growth rate between the 2017 and 2023 censuses"),
    ("households", "Households", "People", "households", "neutral", "Number of households"),
    ("household_size", "Average household size", "People", "persons", "neutral",
     "Average number of people per household"),
    ("area_census", "Area", "People", "km²", "neutral", "Census-reported land area"),
]


# ---------------------------------------------------------------------------
# Build the table of counts
# ---------------------------------------------------------------------------

def build_counts() -> pd.DataFrame:
    """One row per (province_code, census district), one column per count."""
    parts = []

    # Official district totals (complete for every district).
    d = load("PakPC2023PakDist")
    parts.append(d.set_index(["province_code", "DISTRICT"])[
        ["Pop2023", "Pop2017", "GR", "Households", "AHS"]].rename(columns={
            "Pop2023": "pop", "Pop2017": "population_2017", "GR": "growth_rate",
            "Households": "households", "AHS": "household_size"}))

    # Table 1: area, urban population, sex. These match PBS's published
    # district figures, but Table 1 is missing one tehsil of Tando Muhammad
    # Khan, so for that district we use Table 4 instead (see below).
    t = load("TABLE_01")
    ov = t[t["REGION"] == "OVERALL"]
    parts.append(by_district(ov, ["AREA_SQKM", "ALL_SEXES", "MALE", "FEMALE"]).rename(columns={
        "AREA_SQKM": "area_census", "ALL_SEXES": "pop_t01", "MALE": "male_t01", "FEMALE": "female_t01"}))
    parts.append(by_district(t[t["REGION"] == "URBAN"], ["ALL_SEXES"]).rename(
        columns={"ALL_SEXES": "pop_urban_t01"}))

    # Table 4: single-year ages (complete for all 136 districts, unlike the
    # age-group table, which omits Islamabad).
    t = load("TABLE_04")
    label = t["SEX_AGE_GROUP_IN_YEARS"].replace({"BELOW 1": "0", "75 & ABOVE": "75"})
    t["age"] = pd.to_numeric(label, errors="coerce")   # "ALL AGES" becomes NaN
    a = t.dropna(subset=["age"])
    def ages(mask):
        return a[mask].groupby(["province_code", "DISTRICT"])["ALL_SEXES_OVERALL"].sum()
    age_tbl = pd.DataFrame({
        "age_all": ages(a["age"] >= 0),
        "age_u15": ages(a["age"] < 15),
        "age_65p": ages(a["age"] >= 65),
        "age_1564": ages(a["age"].between(15, 64)),
        "age_5_16": ages(a["age"].between(5, 16)),
    })
    age_tbl["age_dep"] = age_tbl["age_all"] - age_tbl["age_1564"]
    parts.append(age_tbl)
    # The "ALL AGES" rows give urban population and sex for every district.
    tot = t[t["SEX_AGE_GROUP_IN_YEARS"] == "ALL AGES"].groupby(["province_code", "DISTRICT"])
    parts.append(pd.DataFrame({
        "pop_t04": tot["ALL_SEXES_OVERALL"].sum(),
        "pop_urban": tot["ALL_SEXES_URBAN"].sum(min_count=1),
        "male": tot["MALE_OVERALL"].sum(),
        "female": tot["FEMALE_OVERALL"].sum(),
    }))

    # Table 12: literacy and schooling (long format: one row per variable).
    t = load("TABLE_12")
    want = {"Literate >=10": "lit10", "Population >=10": "pop10", "Population >=5": "pop5",
            "Out of School Children (5-16)": "oosc", "Never to School (all)": "never_all"}
    sub = t[t["VARS"].isin(want)].copy()
    sub["VARS"] = sub["VARS"].map(want)
    for col, suffix in [("ALL_SEXES_OVERALL", ""), ("FEMALE_OVERALL", "_f"), ("MALE_OVERALL", "_m")]:
        p = sub.pivot_table(index=["province_code", "DISTRICT"], columns="VARS",
                            values=col, aggfunc="sum")
        p.columns = [c + suffix for c in p.columns]
        parts.append(p if suffix == "" else p[[f"lit10{suffix}", f"pop10{suffix}"]])

    # Tables 22-25: households (OVERALL rows only).
    hh = [("TABLE_22", "hh_t22", {"LIGHT_ELECT": "light_elec", "LIGHT_SOLAR": "light_solar",
                                  "FUEL_GAS": "fuel_gas", "FUEL_FIREWOOD": "fuel_wood"}),
          ("TABLE_23", "hh_t23", {"DRINK_WTR_INSIDE": "water_inside", "DRINK_WTR_TAP": "water_tap"}),
          ("TABLE_24", "hh_t24", {"TOILET_FLUSH": "toilet_flush", "TOILET_NONE": "toilet_none"}),
          ("TABLE_25", "hh_t25", {"RES_ST_OWNED": "owned", "NO_ROOMS_ONE": "rooms1"})]
    for table, hh_name, cols in hh:
        t = load(table)
        t = t[t["REGION"] == "OVERALL"]
        parts.append(by_district(t, ["HOUSEHOLDS", *cols]).rename(
            columns={"HOUSEHOLDS": hh_name, **cols}))

    # Table 16: disability.
    t = load("TABLE_16")
    p = t.pivot_table(index=["province_code", "DISTRICT"], columns="DISAB_FUNC_LIM",
                      values="ALL_SEXES_OVERALL", aggfunc="sum")
    parts.append(pd.DataFrame({"disab": p["Disability"], "pop_t16": p["Population"]}))

    # LESSON: pd.concat(axis=1) lines up all these tables side by side on
    # their shared index (province_code, DISTRICT).
    counts = pd.concat(parts, axis=1)
    # A district whose urban rows are all blank has no urban localities:
    # its urban population is 0, not unknown.
    counts["pop_urban_t01"] = counts["pop_urban_t01"].fillna(0)
    counts["pop_urban"] = counts["pop_urban"].fillna(0)

    # Prefer Table 1 (official) wherever it covers the whole district,
    # i.e. wherever its population equals the official district total.
    complete = (counts["pop_t01"] - counts["pop"]).abs() < 1
    counts["pop_ur_den"] = counts["pop_t04"]
    for t1, t4 in [("pop_urban_t01", "pop_urban"), ("male_t01", "male"),
                   ("female_t01", "female"), ("pop_t01", "pop_ur_den")]:
        counts.loc[complete, t4] = counts.loc[complete, t1]
    return counts


def languages() -> pd.DataFrame:
    """Largest mother tongue in each district, and its share."""
    t = load("TABLE_11")
    t = t[t["LANGUAGE"] != "TOTAL"]
    g = t.groupby(["province_code", "DISTRICT", "LANGUAGE"])["ALL_SEXES_OVERALL"].sum().reset_index()
    total = g.groupby(["province_code", "DISTRICT"])["ALL_SEXES_OVERALL"].transform("sum")
    g["share"] = 100 * g["ALL_SEXES_OVERALL"] / total
    # idxmax() gives the row label of the largest value in each group.
    top = g.loc[g.groupby(["province_code", "DISTRICT"])["share"].idxmax()]
    top["LANGUAGE"] = top["LANGUAGE"].str.title().replace(
        {"Pushto": "Pashto", "Brahvi": "Brahui", "Kohiostani": "Kohistani", "Others": "Other"})
    return top.set_index(["province_code", "DISTRICT"])[["LANGUAGE", "share"]].rename(
        columns={"LANGUAGE": "top_language", "share": "top_language_share"})


def compute_rates(counts: pd.DataFrame) -> pd.DataFrame:
    """Apply every RATES definition to a table of counts."""
    out = pd.DataFrame(index=counts.index)
    for ind_id, _, _, num, den, scale, *_ in RATES:
        # Division by zero gives inf; replace with NaN (blank) so it's obvious.
        out[ind_id] = (scale * counts[num] / counts[den]).replace([np.inf, -np.inf], np.nan)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    counts = build_counts()
    rates = compute_rates(counts)

    # District table: direct values + rates + language.
    direct_ids = [d[0] for d in DIRECT]
    wide = pd.concat([counts.rename(columns={"pop": "population"})[direct_ids],
                      rates, languages()], axis=1)
    # Census population totals from the official table are used for density.
    wide["density"] = wide["population"] / wide["area_census"]

    # Join to our district_ids using the census names stored in districts.csv.
    dist = pd.read_csv(config.PROCESSED / "districts.csv")
    keymap = dist[dist["in_census_2023"]].set_index(["province_code", "census_name"])["district_id"]
    wide.index = wide.index.map(lambda k: keymap.get(k))
    if wide.index.isna().any():
        raise SystemExit("Some census districts did not map to a district_id")
    wide.index.name = "district_id"

    # Tando Muhammad Khan: the tehsil-level tables omit one of its tehsils.
    tmk = "SD-TANDO-MUHAMMAD-KHAN"
    wide["data_note"] = ""
    wide.loc[tmk, "data_note"] = ("Area and density are not shown: one tehsil is missing "
                                  "from the census area table. All other figures are complete.")
    wide.loc[tmk, ["density", "area_census"]] = np.nan  # area is incomplete

    # Districts outside Census 2023 get empty rows, so every district appears.
    for did in dist.loc[~dist["in_census_2023"], "district_id"]:
        wide.loc[did, "data_note"] = ("Not covered by Pakistan's Census 2023: Azad Jammu and "
                                      "Kashmir and Gilgit-Baltistan run separate enumerations.")
    wide = wide.sort_index().round(2)

    # Province and national aggregates: sum counts, then apply the same rates.
    # LESSON: groupby(level=0) groups by the first level of the index
    # (province_code here) without needing a separate column.
    agg_rows = []
    for name, grp in list(counts.groupby(level=0)) + [("PK", counts)]:
        s = grp.sum(min_count=1)
        r = compute_rates(s.to_frame().T).iloc[0]
        row = {"area_code": name, "population": s["pop"], "households": s["households"],
               "population_2017": s["population_2017"], "area_census": s["area_census"],
               "household_size": s["pop"] / s["households"],
               # Growth: average annual compound rate between the two totals (6 years).
               "growth_rate": 100 * ((s["pop"] / s["population_2017"]) ** (1 / 6) - 1),
               **r.to_dict()}
        row["density"] = s["pop"] / s["area_census"]
        agg_rows.append(row)
    agg = pd.DataFrame(agg_rows).round(2)

    # Catalog.
    cat = [{"indicator_id": i, "label": lab, "category": catg, "unit": unit,
            "direction": dirn, "description": desc, "type": "count"}
           for i, lab, catg, unit, dirn, desc in DIRECT]
    cat += [{"indicator_id": i, "label": lab, "category": catg, "unit": unit,
             "direction": dirn, "description": desc, "type": "rate"}
            for i, lab, catg, _, _, _, unit, dirn, desc in RATES]
    cat.append({"indicator_id": "top_language_share", "label": "Largest mother tongue (share)",
                "category": "People", "unit": "%", "direction": "neutral",
                "description": "Share of people whose mother tongue is the district's most common one",
                "type": "rate"})
    cat = pd.DataFrame(cat)
    cat["source"] = config.CENSUS_CITATION
    cat["year"] = 2023
    cat.loc[cat["indicator_id"] == "population_2017", "year"] = 2017

    long = (wide.drop(columns=["top_language", "data_note"])
                .reset_index()
                .melt(id_vars="district_id", var_name="indicator_id", value_name="value")
                .dropna(subset=["value"]))

    out = config.PROCESSED
    cat.to_csv(out / "indicator_catalog.csv", index=False)
    wide.to_csv(out / "indicators_wide.csv")
    long.to_csv(out / "indicators_long.csv", index=False)
    agg.to_csv(out / "aggregates.csv", index=False)

    print(f"{len(cat)} indicators, {wide['population'].notna().sum()} districts with data, "
          f"{len(long)} values")
    print(agg[["area_code", "population", "literacy", "out_of_school", "electricity",
               "urban_share", "growth_rate"]].to_string(index=False))


if __name__ == "__main__":
    main()
