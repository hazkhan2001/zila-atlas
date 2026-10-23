"""
config.py: one place for every path and setting the pipeline uses.

LESSON: Why a config file?
    If paths are typed directly inside each script ("hard-coded"), changing
    one folder means hunting through every file. Putting them here means
    every script imports the same values, so a change happens once.

    `Path` (from pathlib) is Python's modern way to handle file paths.
    The `/` operator joins path pieces and works on Windows, Mac and Linux:
        ROOT / "data" / "raw"   ->   .../pakdata/data/raw
"""

from pathlib import Path

# __file__ is this file's own location. .resolve() makes it absolute,
# .parent goes up one folder (pipeline/), .parent again goes to pakdata/.
ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data"
RAW = DATA / "raw"              # untouched downloads, never edited by hand
REFERENCE = DATA / "reference"  # small hand-curated tables
PROCESSED = DATA / "processed"  # everything the scripts generate
SITE = ROOT / "site"            # the website
SITE_DATA = SITE / "data"       # data files the website loads

# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------
# HOW OUR DISTRICT MAP IS MADE
#   Building blocks: 554 tehsil shapes drawn from the 2017 census
#   (Pathways Data, via geoBoundaries ADM3). Each tehsil is assigned to its
#   2023 census district, then all tehsils of a district are merged
#   ("dissolved") into one district shape. Provinces are made the same way
#   from districts. Every layer therefore shares one set of borders.
#
#   The older geoBoundaries ADM1/ADM2 layers are used only as HINTS: to tell
#   which province a tehsil is in, and which district it belonged to before.

TEHSIL_SHAPES = RAW / "geoboundaries" / "PAK_ADM3.geojson"
HINT_PROVINCES = RAW / "geoboundaries" / "PAK_ADM1.geojson"
HINT_DISTRICTS = RAW / "geoboundaries" / "PAK_ADM2.geojson"

BOUNDARY_CITATION = (
    "District shapes built by merging 2017 census tehsils (Pathways Data Pvt. Ltd., "
    "via geoBoundaries gbOpen PAK ADM3, Open Database License 1.0) into 2023 "
    "census districts. Province hints from geoBoundaries ADM1/ADM2 (public domain)."
)

CENSUS_DIR = RAW / "census2023"
CENSUS_CITATION = (
    "Pakistan Bureau of Statistics, 7th Population and Housing Census 2023, "
    "digitized in the PakPC2023 R package v0.2.0 (Yaseen, Dilber, Asghar), GPL-2."
)

# Short, stable province codes. These become the first part of every
# district_id, so they must never change once data is published.
PROVINCE_CODES = {
    "PK-PB": "PB",  # Punjab
    "PK-SD": "SD",  # Sindh
    "PK-KP": "KP",  # Khyber Pakhtunkhwa
    "PK-BA": "BA",  # Balochistan
    "PK-IS": "IS",  # Islamabad Capital Territory
    "PK-JK": "JK",  # Azad Jammu and Kashmir
    "PK-GB": "GB",  # Gilgit-Baltistan
}

PROVINCE_NAMES = {
    "PB": "Punjab",
    "SD": "Sindh",
    "KP": "Khyber Pakhtunkhwa",
    "BA": "Balochistan",
    "IS": "Islamabad Capital Territory",
    "JK": "Azad Jammu and Kashmir",
    "GB": "Gilgit-Baltistan",
}

# How the census package spells each province.
CENSUS_PROVINCES = {
    "PUNJAB": "PB", "SINDH": "SD", "KPK": "KP",
    "BALOCHISTAN": "BA", "ISLAMABAD": "IS",
}

# Equal-area projection for computing areas in km².
# LESSON: Latitude/longitude are angles, not distances, so you cannot
# measure area with them directly. We temporarily "project" the shapes onto
# a flat surface designed to preserve area. EPSG:6933 is a global
# equal-area projection that works fine for Pakistan.
AREA_CRS = "EPSG:6933"
