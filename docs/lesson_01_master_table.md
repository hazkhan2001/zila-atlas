# Lesson 1: The master table, and why everything depends on it

## The problem

You'll be joining a dozen datasets: census tables, PSLM, MICS, flood maps,
firm lists. Each one names districts its own way. If you join on raw names,
rows silently disappear, and nobody notices until a professor emails you
asking why Sheikhupura has no data.

The fix is one **master table** with a stable ID per district, and a single
function that every dataset must pass through to get that ID.

## Concepts in this lesson

### 1. A GeoDataFrame is a pandas table with a shape column

```python
import geopandas as gpd
districts = gpd.read_file("data/processed/districts.geojson")
districts.head()          # looks like a normal pandas table...
districts.geometry        # ...plus a column of polygons
districts.plot()          # and it can draw itself
```

Everything you know about pandas (`.groupby`, `.merge`, filtering) still works.

### 2. Coordinate systems (CRS)

Latitude/longitude are **angles**. One degree of longitude is about 111 km at
the equator and about 92 km at Lahore, so you can't measure area in degrees.
`area_km2()` reprojects to an equal-area system first:

```python
gdf.to_crs("EPSG:6933").area / 1_000_000   # m² -> km²
```

Rule of thumb: store and display in EPSG:4326 (lat/lon), measure in a
projected CRS.

### 3. Spatial join

A normal join matches rows by a shared column. A spatial join matches by
location: "which district polygon contains this tehsil?"

```python
gpd.sjoin(points, districts, predicate="within")
```

We join a **representative point** of each tehsil, not the whole polygon,
because borders from two sources never line up exactly. And we check how
much of each tehsil falls outside all districts, so a unit that doesn't
belong anywhere is flagged instead of forced into its nearest neighbor.

### 4. Normalizing names

`normalize_name()` applies the same cleanup to every name before comparing:

| Input | Normalized |
|---|---|
| `D.I. Khan District` | `dera ismail khan` |
| `D I Khan` | `dera ismail khan` |
| `Umer Kot` vs `Umerkot` | both `umerkot` once spaces are removed |

Anything still unmatched gets **suggestions printed for a human**, never an
automatic fuzzy match. A wrong automatic match is worse than a missing one,
because it's invisible.

### 5. IDs that are unique, stable and readable

`PB-SHEIKHUPURA` tells you the province and district at a glance. The build
script refuses to finish if two districts would get the same ID.

### 6. Validation as code

`firms.py` turns your editorial rules ("no revenue without a source", "never
estimate private firms") into checks that run every time. If any fail, the
script exits with code 1 and writes nothing. Later, this lets an automated
check block bad data from ever reaching the site.

## Exercises

1. Run `python pipeline/firms.py tests/firms_bad_example.csv`, read each
   error, then fix the file until it passes.
2. In a Python shell, try:
   ```python
   from pipeline.names import normalize_name
   normalize_name("Mirpur Khas")
   normalize_name("Kambar Shahdad Kot")
   ```
   Why does the second one need an alias even after normalization?
3. Open `data/processed/build_report.txt`. Which two tehsils were assigned
   by "nearest"? Look up where they are and decide whether that's right.
