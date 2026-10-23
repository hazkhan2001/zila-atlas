"""
run_all.py: rebuild everything, in order, from the raw files.

    python pipeline/run_all.py

LESSON: subprocess.run starts another Python script as if you had typed it.
check=True stops this script the moment any step fails, so a broken step
can never quietly feed bad data to the steps after it.
"""

import subprocess
import sys
from pathlib import Path

STEPS = [
    "build_districts.py",   # tehsils -> 2023 districts -> provinces
    "build_indicators.py",  # census tables -> district indicators
    "assemble_firms.py",    # research batches -> firms.csv
    "firms.py",             # validate firms, rank, export
    "build_national.py",    # national economy + provincial health tables
    "export_site.py",       # compact files + page for the website
]

here = Path(__file__).resolve().parent
for step in STEPS:
    print(f"\n=== {step} ===")
    subprocess.run([sys.executable, str(here / step)], check=True)
print("\nAll steps finished. Open site/index.html through a local server to view it.")
