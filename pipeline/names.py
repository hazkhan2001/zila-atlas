"""
names.py: turn messy district names into stable district_ids.

THE PROBLEM THIS SOLVES
    The same district shows up spelled differently in every dataset:
        "Sheikhupura", "Sheikhpura", "SHEIKHUPURA DISTRICT"
        "Bahawalnagar", "B. Nagar"
        "Dera Ismail Khan", "D.I. Khan", "D I Khan"
    Joining on raw names silently drops rows. So every incoming name goes
    through three steps, in order:
        1. normalize it (lowercase, strip punctuation and filler words)
        2. look it up among master names and the alias table
        3. if still unmatched, suggest close spellings for a human to confirm

    Nothing is ever matched by guesswork automatically. Fuzzy suggestions are
    only printed for review; a confirmed one gets added to
    data/reference/district_aliases.csv so it matches exactly next time.
"""

import re
import unicodedata
from difflib import get_close_matches

import pandas as pd

# Words that add no identifying information. Order doesn't matter here.
FILLER_WORDS = {"district", "dist", "agency", "tribal", "the"}

# Common abbreviations expanded to full words before comparing.
# LESSON: a dict used as a lookup table: key = what we see, value = what we want.
# Only multi-letter codes: single letters are too ambiguous to expand
# automatically. Odd cases like "B. Nagar" go in the alias table instead.
ABBREVIATIONS = {
    "di": "dera ismail",   # D.I. Khan
    "dg": "dera ghazi",    # D.G. Khan
    "ry": "rahim yar",     # R.Y. Khan
    "tt": "toba tek",      # T.T. Singh
    "ict": "islamabad",
}


def normalize_name(name: str) -> str:
    """
    Reduce a name to a simple comparable form.

    LESSON: The `name: str` and `-> str` parts are "type hints". Python does
    not enforce them; they document what goes in and what comes out.

    >>> normalize_name("D.I. Khan District")
    'dera ismail khan'
    """
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""

    # 1. Strip accents (e.g. "Kundūz" -> "Kunduz") and lowercase.
    text = unicodedata.normalize("NFKD", str(name))
    text = text.encode("ascii", "ignore").decode("ascii").lower()

    # 2. Turn punctuation into spaces.
    #    LESSON: re.sub(pattern, replacement, text) is a regex find-and-replace.
    #    [^a-z0-9 ] means "any character that is NOT a letter, digit or space".
    text = re.sub(r"[^a-z0-9 ]+", " ", text)

    # 3. Glue runs of single letters into one token: "d i khan" -> "di khan".
    #    This makes "D.I. Khan", "D I Khan" and "DI Khan" all identical.
    tokens = []
    letters = ""                      # buffer collecting consecutive single letters
    for tok in text.split():
        if len(tok) == 1:
            letters += tok            # keep collecting
        else:
            if letters:               # a word ended the run: flush the buffer
                tokens.append(letters)
                letters = ""
            tokens.append(tok)
    if letters:                       # name ended while still collecting
        tokens.append(letters)

    # 4. Expand known abbreviations and drop filler words.
    #    LESSON: list comprehension = a compact loop that builds a list:
    #        [what_to_keep for item in items if condition]
    words = []
    for tok in tokens:
        words.extend(ABBREVIATIONS.get(tok, tok).split())  # .get(key, default)
    words = [w for w in words if w not in FILLER_WORDS]

    return " ".join(words)


def match_key(name: str) -> str:
    """
    The key actually used for lookups: the normalized name with spaces removed,
    so "Umer Kot" == "Umerkot" and "Mirpur Khas" == "Mirpurkhas".
    """
    return normalize_name(name).replace(" ", "")


def build_lookup(master: pd.DataFrame, aliases: pd.DataFrame) -> dict:
    """
    Build a dictionary: normalized name -> district_id.

    Includes every master district name plus every confirmed alias.
    Raises an error if two different districts would share a normalized name,
    because a lookup that is ambiguous would silently pick the wrong one.
    """
    lookup = {}

    # LESSON: zip() walks two lists side by side, pairing their items.
    pairs = list(zip(master["district_name"], master["district_id"]))
    # The boundary file's own original spelling always counts as an alias.
    if "source_name" in master.columns:
        pairs += list(zip(master["source_name"], master["district_id"]))
    pairs += list(zip(aliases["alias"], aliases["district_id"]))

    for raw_name, district_id in pairs:
        key = match_key(raw_name)
        if key == "":
            continue  # blank names (e.g. districts outside the census) carry no info
        if key in lookup and lookup[key] != district_id:
            raise ValueError(
                f"Ambiguous name '{raw_name}' -> both {lookup[key]} and "
                f"{district_id}. Make the alias province-specific."
            )
        lookup[key] = district_id
    return lookup


def match_names(names: pd.Series, lookup: dict, n_suggestions: int = 3) -> pd.DataFrame:
    """
    Match a column of incoming names against the lookup.

    Returns one row per *unique* input name with:
        input_name, normalized, district_id (blank if unmatched),
        method ('exact' or 'unmatched'), suggestions (for unmatched only)
    """
    rows = []
    known_keys = list(lookup.keys())

    for raw in names.dropna().unique():
        key = match_key(raw)
        if key in lookup:
            rows.append({"input_name": raw, "normalized": key,
                         "district_id": lookup[key], "method": "exact",
                         "suggestions": ""})
        else:
            # get_close_matches ranks strings by similarity (0 to 1).
            # cutoff=0.75 means "at least 75% similar" to be suggested.
            close = get_close_matches(key, known_keys, n=n_suggestions, cutoff=0.75)
            suggestion_text = "; ".join(f"{c} -> {lookup[c]}" for c in close)
            rows.append({"input_name": raw, "normalized": key,
                         "district_id": "", "method": "unmatched",
                         "suggestions": suggestion_text})

    return pd.DataFrame(rows)
