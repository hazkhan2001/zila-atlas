# CLAUDE.md: Zila Atlas

Free, public, district-level data platform for Pakistan (Spatial India equivalent).
Owner: Hamza, a Python beginner. Every coding session doubles as a lesson: explain syntax
and the logic of the structure, and keep `LESSON` comments in scripts.

## Commands
- Rebuild everything: `python pipeline/run_all.py`
- View site: `cd site && python -m http.server 8000`
- Screenshot test (light/dark, desktop/phone): `python tests/check_site.py`
- Validate firms only: `python pipeline/firms.py`
- Compare OCHA boundaries (after download to `data/raw/ocha_codab/`): `python pipeline/compare_ocha.py`

## Layout
- `data/raw/`: never edit. `data/reference/`: hand-curated, every row has a reason or source.
- `data/processed/`, `site/data/`, `site/index.html`: generated; edit `site/src/index.html`, not `site/index.html`.

## Rules that must hold
1. Every published number has a period and a source link; validators enforce this.
2. No estimates presented as reported figures.
3. Rates = sum of counts, then divide. Never average percentages.
4. Never fuzzy-join district names automatically; confirmed spellings go in `data/reference/district_aliases.csv`.
5. District IDs (`PB-LAHORE`) are stable; never rename once published.
6. Census tables: fill blank provinces from district names (groupby drops blank keys).
7. Neutral wording; disputed areas labelled as in source, shown separately, no statistics.
8. Real basemap imagery only (Esri/Mapbox), never synthetic map art.
9. Chart colours come from tokens validated for colour-blind readers; map ramp is one-hue sequential.

## Context
Full scope, decisions, sources, backlog, launch and outreach plans live in the Claude Project
knowledge files (01 to 06). Top open task: replace tehsil-built districts with OCHA COD-AB boundaries (download needed, then run `compare_ocha.py`).
Firm rows keep their own `last_verified` date in `firms_staging/`; never stamp it with the build date.
