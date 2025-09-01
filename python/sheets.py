#!/usr/bin/env python3
import argparse, json, re, shutil, time
from pathlib import Path

LABEL_RE = re.compile(r"(?i)level\s*(\d+)\s*unit\s*(\d+)\s*lesson\s*(\d+)")


def parse_label(label: str):
    m = LABEL_RE.search(str(label))
    if not m:
        return None
    L, U, S = map(int, m.groups())
    return L, U, S


def load_workbook(workbook_path: Path):
    """Return dict mapping (level, unit, lesson_num) -> full sheet object from a workbook JSON."""
    data = json.loads(workbook_path.read_text(encoding="utf-8"))
    sheets = data.get("sheets", [])
    out = {}
    for s in sheets:
        key = (
            int(s.get("level", -1)),
            int(s.get("unit", -1)),
            int(s.get("lesson_num", -1)),
        )
        if all(k != -1 for k in key):
            out[key] = s  # store entire sheet object
    return out


def backup_file(p: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    bak = p.with_suffix(p.suffix + f".bak.{ts}")
    shutil.copy2(p, bak)
    return bak


def main():
    ap = argparse.ArgumentParser(
        description="Embed full 'sheet' objects into lvl_3_4_metadata.json "
        "by matching human labels to workbook sheets for Level 3 Units (any number)."
    )
    ap.add_argument(
        "--meta", required=True, type=Path, help="Path to lvl_3_4_metadata.json"
    )
    ap.add_argument(
        "--from_dir",
        required=True,
        type=Path,
        help="Directory containing unit workbook JSONs (e.g., outputs/)",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="Do not write changes; just report"
    )
    args = ap.parse_args()

    # Collect all unit files from the directory
    unit_files = sorted(args.from_dir.glob("*_L3U*.json"))
    if not unit_files:
        raise SystemExit(f"No unit JSONs found in {args.from_dir}")

    # Build index
    idx = {}
    for ujson in unit_files:
        idx.update(load_workbook(ujson))

    # Load metadata array
    meta_path = args.meta
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(meta, list):
        raise SystemExit(
            "Expected lvl_3_4_metadata.json to be a JSON array of objects."
        )

    updated = 0
    missing = []
    skipped_out_of_scope = 0

    for obj in meta:
        label = obj.get("key") or obj.get("label")
        parsed = parse_label(label) if label else None
        if not parsed:
            continue
        L, U, S = parsed

        # Scope: Level 3, any Unit found in from_dir
        if L != 3:
            skipped_out_of_scope += 1
            continue

        sheet = idx.get((L, U, S))
        if sheet:
            if obj.get("sheet") != sheet:
                obj["sheet"] = sheet
                updated += 1
        else:
            missing.append(f"Level {L} Unit {U} Lesson {S}")

    # Write or dry-run
    if args.dry_run:
        print(f"[DRY-RUN] Would embed {updated} full sheet objects.")
    else:
        bak = backup_file(meta_path)
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[OK] Embedded {updated} sheet objects. Backup saved to {bak}")

    if missing:
        print("[WARN] No matching sheet found for:")
        for m in missing:
            print("  -", m)
    print(f"[INFO] Skipped out-of-scope (not Level 3): {skipped_out_of_scope}")


if __name__ == "__main__":
    main()
