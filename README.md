# Zila Atlas: a district data explorer for Pakistan

A free, public, district-level data site for Pakistan in the spirit of Spatial
India. This folder holds the whole thing: the data pipeline and the website.

## Quick start

```bash
pip install -r requirements.txt
python pipeline/run_all.py                    # rebuild everything
cd site && python -m http.server 8000         # then open http://localhost:8000
```

Self-hosted (for example on GitHub Pages) the map shows Esri satellite imagery
under the districts. Inside Claude's artifact viewer the imagery is blocked,
so the map falls back to a plain background on its own.

## Publishing on GitHub Pages

The site is static, so GitHub can host it for free. `.github/workflows/pages.yml`
uploads the `site/` folder whenever you push to the `main` branch.

1. Create an empty repository on GitHub (no README, no licence, so the first push is clean).
2. Push this folder to it (the steps are explained in `docs/lesson_02_publishing.md`).
3. On GitHub: Settings, then Pages, then set Source to "GitHub Actions".
4. The first run takes about a minute. The address appears in the Actions tab and under Pages.

After that, a data update is: `python pipeline/run_all.py`, then commit and push.
Licences: code is MIT (`LICENSE`); compiled data is CC BY 4.0 except the ODbL shapes (`LICENSE-DATA.md`).

## What's in v1

| Part | Contents |
|---|---|
| Districts | 156 districts: Punjab 36, Sindh 30 (Karachi as 7), KP 35, Balochistan 34, Islamabad, AJK 10, GB 10 |
| Indicators | 29 Census 2023 indicators for the 136 census districts, plus province and national totals |
| Companies | 68 firms with sourced revenue (or total assets for banks), top 3 per province by head office or operations |
| Economy | 52 national figures (debt, creditors, reserves, IMF, rates, inflation, GDP, PPP, fiscal, trade, ratings) and 4 ten-year histories |
| Health | Fertility and child mortality for every province, AJK, GB and former FATA (PDHS 2017-18, plus PDS 2020 and Sindh MICS) |
| Website | Map with district profiles, scatter comparison, companies, economy tab, data and methods page |

## Pipeline order

```
pipeline/
  config.py            paths, sources, province codes
  names.py             name normalization and matching (the join key for every dataset)
  build_districts.py   2017 tehsil shapes -> 2023 census districts -> provinces
  build_indicators.py  census tables -> indicators (sum counts, then divide)
  assemble_firms.py    research batches in data/reference/firms_staging/ -> firms.csv
  firms.py             validates firms against the rules, ranks, exports
  build_national.py    validates national figures (data/reference/national/*.csv) -> national.json
  export_site.py       compact data files + builds site/index.html from site/src/
  run_all.py           runs all of the above in order
tests/
  check_site.py        renders every view in a headless browser, light/dark, desktop/phone
  firms_example.csv    fictional rows for practising with the validator
```

## Key reference tables (hand-curated, in data/reference/)

- `tehsil_assignment_overrides.csv`: 79 tehsils placed by hand, each with a confidence and reason
- `hint_district_spellings.csv`: old district spellings to census spellings
- `district_aliases.csv`: other spellings seen in other datasets (MICS, UNOSAT...)
- `district_display_names.csv`: how census names are shown on the site
- `firms_staging/*.csv`: company research, one file per batch

## Data rules

1. Raw files are never edited. Corrections live in `data/reference/`.
2. Every published number carries a source and a period.
3. Unmatched names are never guessed. They are printed with suggestions, then added by hand.
4. Rates are built by summing counts across tehsils, then dividing. Never by averaging percentages.
5. Private firms that don't disclose are left unranked. No figure is an estimate.

## Updating the Economy tab

Each figure is one row in `data/reference/national/stats_*.csv` with its period and
source link. When a new number is published (monthly inflation, a rating action, the
weekly reserves), edit that row and run `python pipeline/run_all.py`. The validator
refuses any row without a period or a link.

## Open items

- **District lines are approximate at the edges** (built from 2017 tehsils). Replace with
  OCHA COD-AB when it can be downloaded; IDs should mostly survive because they come from
  census names.
- **Karachi East and South** are low-confidence outlines (old towns mapped to new districts).
- **AJK and GB** have districts but no census figures (they're outside Census 2023).
- **Companies to reconcile**: Engro Fertilizers (two sources disagree), HBL (only consolidated
  assets found), ZTBL (2024 figure), SSGC and SNGPL (FY2026 not yet published), K-Electric
  (latest accounts FY2024). GEPCO, HESCO, SEPCO, QESCO, TESCO and GHPL publish no revenue found yet.
- **Economy figures to firm up**: FY2025-26 current account (two reported figures), core
  inflation and the exchange rate (press-reported), federal government deposits at SBP
  (read from an unclear table), creditor detail for individual multilateral lenders and China
  (SBP publishes only categories). Interest as a share of revenue is calculated, not published.
- **Health surveys**: the latest survey covering every region is PDHS 2017-18; newer
  provincial MICS (Punjab 2024, KP 2019, Balochistan 2019-20) could not be reached.
- **Esri imagery terms**: fine for development; for a public launch check Esri's terms or switch
  the tile URL in `site/src/index.html` to a keyed provider (Mapbox, MapTiler).
- **Licenses**: the tehsil layer is ODbL, so the derived district shapes must be shared under
  ODbL with attribution. The census package is GPL-2.

## Sources

- PBS 7th Population and Housing Census 2023, digitized in the PakPC2023 R package
  (Yaseen, Dilber, Asghar), via https://github.com/cran/PakPC2023
- Tehsil boundaries: Pathways Data Pvt. Ltd. via geoBoundaries gbOpen PAK ADM3 (ODbL 1.0)
- Province and old-district hints: geoBoundaries gbOpen PAK ADM1/ADM2
- Companies: PSX filings and data portal, company annual reports, Auditor-General
  reports as quoted in the press; each row in `firms.csv` links its source
