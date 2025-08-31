import ast
import re
import json
import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple, Iterable

VERSION = "extract_visual_notes v1.2 (sep-insensitive, union, breakdown)"

# Matches the <visual ...> tag regardless of spacing/case
VISUAL_TAG_RE = re.compile(r"<\s*visual", re.IGNORECASE)
# Remove spaces and hyphens for canonical comparisons
SEPARATOR_RE = re.compile(r"[\s\-]+")


def normalize_sep_insensitive(s: str) -> str:
    """Lowercase and remove spaces/hyphens."""
    return SEPARATOR_RE.sub("", s.lower())


def extract_data_list(py_path: Path, var_name: str = "data") -> List[Dict]:
    raw = py_path.read_text(encoding="utf-8")
    tree = ast.parse(raw)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", None) == var_name:
                    return ast.literal_eval(node.value)
    raise ValueError(f"{var_name} not found in {py_path}")


def walk_notes(
    obj: Any, path: List[str], sheet_name: str
) -> Iterable[Tuple[str, str, str]]:
    """
    Yield tuples of (sheet_name, path_str, notes_text) for every notes node
    gated by <visual>.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "notes" and isinstance(v, str):
                if VISUAL_TAG_RE.search(v):
                    yield (sheet_name, " > ".join(path + [k]), v)
            else:
                yield from walk_notes(v, path + [str(k)], sheet_name)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from walk_notes(item, path + [f"[{i}]"], sheet_name)


def extract_visual_notes(data: List[Dict]) -> List[Dict]:
    """Collect all <visual> notes (no filtering yet)."""
    results: List[Dict] = []
    for i, entry in enumerate(data):
        sheet = entry.get("sheet", {})
        sheet_name = sheet.get("sheet_name", f"[unknown_sheet_{i}]")
        if "slides" in sheet:
            for sname, pstr, note in walk_notes(
                sheet["slides"], [f"[{i}]", "sheet", "slides"], sheet_name
            ):
                results.append({"sheet_name": sname, "path": pstr, "notes": note})
    return results


def filter_by_phrases_sep_insensitive(
    items: List[Dict], phrases: List[str]
) -> Dict[str, List[Dict]]:
    """
    Return a dict mapping each input phrase to the list of matching items
    using separator-insensitive, case-insensitive matching.
    """
    norm_phrases = [(p, normalize_sep_insensitive(p)) for p in phrases]
    out: Dict[str, List[Dict]] = {p: [] for p in phrases}

    for it in items:
        note_norm = normalize_sep_insensitive(it["notes"])
        for orig, norm in norm_phrases:
            if norm in note_norm:
                out[orig].append(it)

    return out


def unique_union(items_lists: Iterable[List[Dict]]) -> List[Dict]:
    """
    Union of items by a stable key to avoid dupes when phrases overlap.
    Key: (sheet_name, path, notes)
    """
    seen = set()
    union: List[Dict] = []
    for lst in items_lists:
        for it in lst:
            key = (it["sheet_name"], it["path"], it["notes"])
            if key not in seen:
                seen.add(key)
                union.append(it)
    return union


def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_csv(path: Path, items: List[Dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sheet_name", "path", "notes"])
        for it in items:
            w.writerow([it["sheet_name"], it["path"], it["notes"]])


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            f"{VERSION}\n"
            "Extract notes under <visual> that contain given phrase(s).\n"
            "Matching is case-insensitive and ignores spaces/hyphens between letters\n"
            "(e.g., 'epocket' == 'e pocket' == 'e-pocket').\n"
            "Prints per-phrase counts and the union count; writes the union to --out-json."
        )
    )
    parser.add_argument(
        "source", type=Path, help="Python file containing `data = [...]`"
    )
    parser.add_argument(
        "--var", type=str, default="data", help="Variable name (default: data)"
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        required=True,
        help="Output JSON for the UNION of matches",
    )
    parser.add_argument(
        "--contains", nargs="+", required=True, help="One or more phrases to search for"
    )
    parser.add_argument(
        "--report-csv", type=Path, help="Optional CSV of the UNION matches"
    )
    parser.add_argument(
        "--list-matrix",
        action="store_true",
        help="Also print which PATHS match which PHRASES (diagnostic)",
    )

    args = parser.parse_args()
    print(VERSION)

    data = extract_data_list(args.source, args.var)
    all_visual = extract_visual_notes(data)

    per_phrase = filter_by_phrases_sep_insensitive(all_visual, args.contains)
    union_items = unique_union(per_phrase.values())

    # Summary
    for p in args.contains:
        print(f"• {p!r}: {len(per_phrase[p])} matches")
    print(f"⇒ UNION (deduped): {len(union_items)} matches")

    # Optional diagnostic matrix: which paths matched which phrase
    if args.list_matrix:
        print("\nPath⇄Phrase matrix (diagnostic):")
        # Build reverse index
        path_to_phrases: Dict[str, List[str]] = {}
        for p, items in per_phrase.items():
            for it in items:
                path_to_phrases.setdefault(it["path"], []).append(p)
        for it in union_items:
            phrases_here = ", ".join(path_to_phrases.get(it["path"], []))
            print(f"- {it['path']}  [{phrases_here}]")

    # Write outputs
    write_json(args.out_json, union_items)
    if args.report_csv:
        write_csv(args.report_csv, union_items)

    print(f"✅ Wrote UNION to {args.out_json}")
    if args.report_csv:
        print(f"🧾 Wrote CSV report to {args.report_csv}")


if __name__ == "__main__":
    main()


# Epockets


# Words
# python extract_visual_notes.py LVL_3_units_1_2_3.py \
#   --out-json  words.json \
#   --contains "show the word" \


# Vocab Cards
# python helpers/extract_visual_notes.py data/level_3.py \
#   --out-json  vocab.json \
#   --contains "vocabulary card" "vocabulary-card"


# Phonemic Awarenes
# python extract_visual_notes.py LVL_3_units_1_2_3.py \
#   --out-json  PhonemicAwareness.json \
#   --contains "Phonemic Awareness" \

# Sound Spelling Cards
# python helpers/extract_visual_notes.py data/level_3.py \
#   --out-json  sound_spelling_cards.json \
#   --contains "sound-spelling card" "sound spelling card"

# Word Ladder
# python helpers/extract_visual_notes.py data/level_3.py \
#   --out-json word_ladder.json \
#   --contains "empty word ladder"
