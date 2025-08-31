#!/usr/bin/env python3
import ast
import re
import json
import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple, Iterable

VERSION = "extract_visual_notes v1.3 (selectable fields, optional visual gate)"

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


def walk_fields(
    obj: Any,
    path: List[str],
    sheet_name: str,
    target_fields: Tuple[str, ...],
    require_visual: bool,
) -> Iterable[Tuple[str, str, str]]:
    """
    Yield (sheet_name, path_str, text) for any string value under keys in target_fields.
    If require_visual is True, only yield when the text contains a <visual> tag.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k in target_fields:
                if (not require_visual) or VISUAL_TAG_RE.search(v):
                    yield (sheet_name, " > ".join(path + [k]), v)
            else:
                yield from walk_fields(
                    v, path + [str(k)], sheet_name, target_fields, require_visual
                )
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from walk_fields(
                item, path + [f"[{i}]"], sheet_name, target_fields, require_visual
            )


def extract_text_items(
    data: List[Dict], target_fields: Tuple[str, ...], require_visual: bool
) -> List[Dict]:
    """Collect candidate text items from the chosen fields (optionally gated by <visual>)."""
    results: List[Dict] = []
    for i, entry in enumerate(data):
        sheet = entry.get("sheet", {})
        sheet_name = sheet.get("sheet_name", f"[unknown_sheet_{i}]")
        if "slides" in sheet:
            for sname, pstr, text in walk_fields(
                sheet["slides"],
                [f"[{i}]", "sheet", "slides"],
                sheet_name,
                target_fields,
                require_visual,
            ):
                results.append({"sheet_name": sname, "path": pstr, "text": text})
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
        note_norm = normalize_sep_insensitive(it["text"])
        for orig, norm in norm_phrases:
            if norm in note_norm:
                out[orig].append(it)

    return out


def unique_union(items_lists: Iterable[List[Dict]]) -> List[Dict]:
    """
    Union of items by a stable key to avoid dupes when phrases overlap.
    Key: (sheet_name, path, text)
    """
    seen = set()
    union: List[Dict] = []
    for lst in items_lists:
        for it in lst:
            key = (it["sheet_name"], it["path"], it["text"])
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
        w.writerow(["sheet_name", "path", "text"])
        for it in items:
            w.writerow([it["sheet_name"], it["path"], it["text"]])


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            f"{VERSION}\n"
            "Extract text from chosen fields (default: notes) and match phrase(s).\n"
            "Optionally require <visual> gate. Matching ignores case and spaces/hyphens."
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
        "--fields",
        nargs="+",
        default=["notes"],
        help="Fields to scan (e.g., notes title section transcription). Default: notes",
    )
    parser.add_argument(
        "--no-visual-gate",
        action="store_true",
        help="Do NOT require <visual> in the text (default requires it).",
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
    target_fields = tuple(args.fields)
    require_visual = not args.no_visual_gate

    all_items = extract_text_items(data, target_fields, require_visual)
    per_phrase = filter_by_phrases_sep_insensitive(all_items, args.contains)
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
