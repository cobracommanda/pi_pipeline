#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path
from argparse import ArgumentParser

KEY_RE = re.compile(r"^Level (\d+) Unit (\d+) Lesson (\d+)$")


def load_json(p: Path, name: str):
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[fatal] Missing {name} at {p}")
    except json.JSONDecodeError as e:
        sys.exit(f"[fatal] {name} is not valid JSON: {e}")


def parse_key(k: str):
    m = KEY_RE.match(k.strip())
    if not m:
        raise ValueError(f"Bad lesson key format: {k!r}")
    level, unit, lesson = map(int, m.groups())
    return level, unit, lesson


def get_read_aloud_cards(read_json, level: int, unit: int):
    level_key = f"level{level}"
    unit_str = str(unit)
    try:
        lessons = read_json[level_key]["units"][unit_str]
    except Exception:
        return None
    # Expect lessons "1".."5"
    return [lessons.get(str(i)) for i in range(1, 6)]


def get_student_book(students_json, level: int, unit: int):
    level_key = f"level{level}"
    unit_str = str(unit)
    try:
        return students_json[level_key]["units"][unit_str]
    except Exception:
        return None


def get_wistia_links(wistia_json, level: int, unit: int):
    level_key = f"level{level}"
    unit_str = str(unit)
    try:
        lessons = wistia_json[level_key]["units"][unit_str]
    except Exception:
        return None
    # Expect lessons "1".."3"
    return [lessons.get(str(i)) for i in range(1, 4)]


def main():
    ap = ArgumentParser(
        description="Merge lesson codes with read_aloud_cards, student_books, and wistiaLinks."
    )
    ap.add_argument(
        "--codes", default="data/meta/codes.json", help="Path to codes.json"
    )
    ap.add_argument(
        "--read",
        default="data/meta/read_aloud_cards.json",
        help="Path to read_aloud_cards.json",
    )
    ap.add_argument(
        "--students",
        default="data/meta/student_books.json",
        help="Path to student_books.json",
    )
    ap.add_argument(
        "--wistia",
        default="data/meta/wistiaLinks.json",
        help="Path to wistiaLinks.json",
    )
    ap.add_argument("--out", default="units.json", help="Output JSON path")
    ap.add_argument(
        "--keyed",
        action="store_true",
        help="Output as an object keyed by the original codes.json keys (default: array of objects)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any enrichment is missing (default: fill with nulls)",
    )
    args = ap.parse_args()

    codes = load_json(Path(args.codes), "codes.json")
    read = load_json(Path(args.read), "read_aloud_cards.json")
    students = load_json(Path(args.students), "student_books.json")
    wistia = load_json(Path(args.wistia), "wistiaLinks.json")

    merged_array = []
    merged_map = {}

    # Sort keys stably by level, unit, lesson
    def sort_key(k: str):
        try:
            return parse_key(k)
        except Exception:
            # Nonconforming keys go last in lexicographic order
            return (9999, 9999, 9999, k)

    errors = []
    for k in sorted(codes.keys(), key=sort_key):
        code = codes[k]
        try:
            level, unit, lesson = parse_key(k)
        except ValueError as e:
            if args.strict:
                sys.exit(f"[fatal] {e}")
            errors.append(str(e))
            # Put a placeholder row and continue
            level = unit = lesson = None

        # Lookups by (level, unit)
        rac = get_read_aloud_cards(read, level, unit) if level and unit else None
        stu = get_student_book(students, level, unit) if level and unit else None
        wis = get_wistia_links(wistia, level, unit) if level and unit else None

        # Strict checks
        if args.strict:
            if rac is None or any(v is None for v in (rac or [])):
                sys.exit(
                    f"[fatal] Missing read_aloud_cards for Level {level} Unit {unit}"
                )
            if stu is None:
                sys.exit(f"[fatal] Missing student_book for Level {level} Unit {unit}")
            if wis is None or any(v is None for v in (wis or [])):
                sys.exit(f"[fatal] Missing wistia_links for Level {level} Unit {unit}")

        row = {
            "level": level,
            "unit": unit,
            "lesson": lesson,
            "key": k,  # keep original string key for traceability
            "code": code,
            "read_aloud_cards": rac,  # length 5 or None
            "student_book": stu,  # string or None
            "wistia_links": wis,  # length 3 or None
        }

        if args.keyed:
            merged_map[k] = row
        else:
            merged_array.append(row)

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps(
            merged_map if args.keyed else merged_array, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )

    # Simple summary
    total = len(merged_map) if args.keyed else len(merged_array)
    print(f"[ok] Wrote {total} merged records → {out_path}")

    if errors and not args.strict:
        print(
            f"[warn] {len(errors)} nonconforming keys encountered (output contains placeholders)."
        )


if __name__ == "__main__":
    main()
