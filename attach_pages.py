#!/usr/bin/env python3
import json
import re
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# --------- Helpers ---------
KEY_SUFFIX_TMPL = r"_TG_L{level}_U{unit}_L{lesson:02d}$"


def load_json(path: Path, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[fatal] Missing {label}: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"[fatal] {label} is not valid JSON: {path}\n{e}")


def maybe_load_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_page_key(
    d: Dict[str, Any], level: int, unit: int, lesson: int
) -> Optional[str]:
    # Keys look like: Y49395_TG_L3_U1_L01 (prefix can vary)
    pat = re.compile(KEY_SUFFIX_TMPL.format(level=level, unit=unit, lesson=lesson))
    for k in d.keys():
        if pat.search(k):
            return k
    return None


def index_metadata(meta: List[Dict[str, Any]]) -> Dict[Tuple[int, int, int], int]:
    idx = {}
    for i, row in enumerate(meta):
        lvl = row.get("level")
        uni = row.get("unit")
        les = row.get("lesson")
        if isinstance(lvl, int) and isinstance(uni, int) and isinstance(les, int):
            idx[(lvl, uni, les)] = i
    return idx


# --------- Main ---------
def main():
    ap = ArgumentParser(
        description="Attach page1/2/3 blocks into lvl_3_4_metadata.json from lessonBlocks."
    )
    ap.add_argument(
        "--meta",
        default="python/lvl_3_4_metadata.json",
        help="Path to metadata JSON (array).",
    )
    ap.add_argument(
        "--blocks_dir",
        default="lessonBlocks",
        help="Directory containing L{level}_U{unit}_pg{n}.json files.",
    )
    ap.add_argument(
        "--levels",
        default="3,4",
        help="Comma-separated levels to process (default: 3,4).",
    )
    ap.add_argument(
        "--units", default="1-30", help="Units range, e.g. '1-30' or '1,2,5'."
    )
    ap.add_argument(
        "--pages", default="1,2,3", help="Which pages to attach (subset of 1,2,3)."
    )
    ap.add_argument(
        "--dry_run",
        action="store_true",
        help="Load and report without writing changes.",
    )
    ap.add_argument(
        "--strict", action="store_true", help="Fail if any page file or key is missing."
    )
    ap.add_argument(
        "--backup",
        action="store_true",
        help="Write a .bak file next to the metadata before saving.",
    )
    args = ap.parse_args()

    meta_path = Path(args.meta)
    blocks_dir = Path(args.blocks_dir)

    metadata = load_json(meta_path, "metadata")
    if not isinstance(metadata, list):
        sys.exit("[fatal] metadata JSON is not an array")

    # Parse CLI selections
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    if "-" in args.units:
        a, b = args.units.split("-", 1)
        units = list(range(int(a), int(b) + 1))
    else:
        units = [int(x) for x in args.units.split(",") if x.strip()]
    pages = [int(x) for x in args.pages.split(",") if x.strip()]
    for p in pages:
        if p not in (1, 2, 3):
            sys.exit("[fatal] pages must be 1,2,3")

    # Index metadata for fast lookup
    idx = index_metadata(metadata)

    missing_files = []
    missing_keys = []
    attached = 0

    for level in levels:
        for unit in units:
            # Load page files once per (level, unit)
            page_docs: Dict[int, Optional[Dict[str, Any]]] = {}
            for p in pages:
                pg_path = blocks_dir / f"L{level}_U{unit}_pg{p}.json"
                doc = maybe_load_json(pg_path)
                if doc is None:
                    if args.strict:
                        sys.exit(f"[fatal] Missing page file: {pg_path}")
                    missing_files.append(str(pg_path))
                page_docs[p] = doc

            # Walk lessons 1..10 (metadata uses 10 lessons per unit)
            for lesson in range(1, 11):
                key = (level, unit, lesson)
                if key not in idx:
                    # Not all (lvl,unit,lesson) combos exist — skip quietly
                    continue

                row = metadata[idx[key]]

                # For each requested page, find the correct key and attach
                for p in pages:
                    doc = page_docs[p]
                    if not isinstance(doc, dict):
                        continue

                    # Find lesson-specific array in the page doc
                    found_key = find_page_key(doc, level, unit, lesson)
                    if not found_key:
                        msg = f"L{level}_U{unit}_pg{p}.json :: no key for lesson {lesson:02d}"
                        if args.strict:
                            sys.exit(f"[fatal] {msg}")
                        missing_keys.append(msg)
                        continue

                    block = doc.get(found_key)
                    # Expect an array of 'cell' objects
                    if not isinstance(block, list):
                        msg = f"L{level}_U{unit}_pg{p}.json :: key {found_key} is not a list"
                        if args.strict:
                            sys.exit(f"[fatal] {msg}")
                        missing_keys.append(msg)
                        continue

                    # Attach to metadata row
                    row[f"page{p}"] = block
                    attached += 1

    # Write back
    if args.dry_run:
        print(f"[dry-run] Would attach {attached} page blocks.")
        if missing_files:
            print(f"[warn] Missing files ({len(set(missing_files))}):")
            for m in sorted(set(missing_files)):
                print(f"  - {m}")
        if missing_keys:
            print(
                f"[warn] Missing/malformed keys ({len(missing_keys)} examples shown up to 20):"
            )
            for m in missing_keys[:20]:
                print(f"  - {m}")
        return

    if args.backup:
        bak_path = meta_path.with_suffix(meta_path.suffix + ".bak")
        bak_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # Save updated metadata
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ok] Attached {attached} page blocks into {meta_path}")

    if missing_files:
        print(
            f"[warn] {len(set(missing_files))} page files missing. Use --strict to fail instead."
        )
    if missing_keys:
        print(
            f"[warn] {len(missing_keys)} lesson keys not found or malformed. Use --strict to fail."
        )


if __name__ == "__main__":
    main()
