#!/usr/bin/env python3
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from json.decoder import JSONDecodeError


# -----------------------
# Number extraction (PURE)
# -----------------------
def extract_rungs_number(text: str) -> str:
    """
    Return rung count as a string, e.g. "6".
    Handles digits ("6 rungs") and words ("six rungs", "twenty-one rungs").
    Raises ValueError if not found.
    """
    t = text.lower()
    # unify any dash punctuation (en/em/etc.) to ASCII hyphen
    t = "".join("-" if unicodedata.category(ch) == "Pd" else ch for ch in t)

    # 1) Try digit form
    m = re.search(r"\b(\d+)\s*rungs?\b", t)
    if m:
        return m.group(1)

    # 2) Try word form (supports zero–99 like "six", "twenty-one")
    m = re.search(r"\b([a-z]+(?:-[a-z]+)?)\s*rungs?\b", t)
    if m:
        word = m.group(1)
        n = _wordnum_to_int(word)
        if n is not None:
            return str(n)

    raise ValueError("No rung count found in text")


def _wordnum_to_int(word: str):
    units = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
    }
    tens = {
        "twenty": 20,
        "thirty": 30,
        "forty": 40,
        "fifty": 50,
        "sixty": 60,
        "seventy": 70,
        "eighty": 80,
        "ninety": 90,
    }
    if word in units:
        return units[word]
    if word in tens:
        return tens[word]
    if "-" in word:
        a, b = word.split("-", 1)
        if a in tens and b in units:
            return tens[a] + units[b]
    return None


# -----------------------
# JSON helpers
# -----------------------
def load_json_tolerant(path: Path):
    """
    Load JSON, tolerating trailing commas like:
      {"a": 1,}
      [1,2,]
    """
    txt = path.read_text(encoding="utf-8")
    try:
        return json.loads(txt)
    except JSONDecodeError:
        # remove trailing commas before } or ]
        fixed = re.sub(r",(\s*[}\]])", r"\1", txt)
        return json.loads(fixed)


def save_json(path: Path, data):
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# -----------------------
# Updater
# -----------------------
def append_rungs_to_items(items: list) -> tuple[int, int]:
    """
    Mutates items: for each dict with 'notes', appends/updates 'rungs'.
    Returns (updated_count, skipped_count).
    """
    updated = 0
    skipped = 0
    for obj in items:
        notes = obj.get("notes", "")
        if not isinstance(notes, str):
            skipped += 1
            continue
        try:
            obj["rungs"] = extract_rungs_number(notes)
            updated += 1
        except ValueError:
            skipped += 1
    return updated, skipped


# -----------------------
# CLI
# -----------------------
def main():
    ap = argparse.ArgumentParser(
        description="Append 'rungs' (as string) to items parsed from notes."
    )
    ap.add_argument("input", type=Path, help="Input JSON file (list of objects)")
    ap.add_argument(
        "-o", "--output", type=Path, help="Output JSON file (default: overwrite input)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Show changes but do not write"
    )
    args = ap.parse_args()

    data = load_json_tolerant(args.input)

    if not isinstance(data, list):
        print("ERROR: Expected a top-level JSON list.", file=sys.stderr)
        sys.exit(1)

    updated, skipped = append_rungs_to_items(data)

    print(f"Processed {len(data)} items: updated={updated}, skipped={skipped}")

    if args.dry_run:
        # Just print a quick preview of the last item (like your example)
        if data:
            print(json.dumps(data[-1], indent=2, ensure_ascii=False))
        return

    out_path = args.output or args.input
    save_json(out_path, data)
    print(f"Wrote updated JSON to: {out_path}")


if __name__ == "__main__":
    main()
