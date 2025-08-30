#!/usr/bin/env python3
import os
import shutil
import zipfile
from pathlib import Path
import runpy
import re
import argparse

# -------------------------
# CONFIGURABLE CONSTANTS
# -------------------------

# Only these placeholders in NAMES/CONTENTS get swapped to the lesson's code.
PLACEHOLDER_TOKENS = ["xxxxx", "XXXXX"]

# If the template zip has a single-root folder (e.g. "xxxxx/", "xcode/"), flatten it.
PLACEHOLDER_DIR_CANDIDATES = ["xxxxx", "XXXXX", "xcode", "XCODE"]

# Editable skill labels; update here as you add units.
skill = {
    "Unit 1": "Open and Closed Syllables",
    "Unit 2": "Open and Closed Syllables",
    "Unit 3": "Long a (a, ai, ea, ay, a_e)",
    # Add more as needed: "Unit 4": "...", etc.
}
SKILL_BY_UNIT = skill

# Student book SKUs by unit pairs: (1,2), (3,4), (5,6), ...
# book1 = first unit in the pair, book2 = second unit in the pair
STUDENT_BOOK = {
    "1": "X84145",
    "2": "X84147",
    "3": "X84149",
    "4": "X84151",
    "5": "X84153",
    "6": "X84155",
    # Add more if you have additional books for higher units
}

# Default audio source directory (where lesson audio lives)
DEFAULT_AUDIO_ROOT = "assets/lesson_audio"

# -------------------------
# UTILITIES
# -------------------------


def safe_rmtree(p: Path):
    if p.exists():
        shutil.rmtree(p)


def is_text_file(path: Path, sniff_bytes: int = 8192) -> bool:
    try:
        with path.open("rb") as f:
            chunk = f.read(sniff_bytes)
        chunk.decode("utf-8")
        return True
    except Exception:
        return False


def replace_in_file(path: Path, replacements: dict):
    try:
        data = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return
    original = data
    for needle, repl in replacements.items():
        data = data.replace(needle, repl)
    if data != original:
        path.write_text(data, encoding="utf-8")


def rename_placeholders_in_tree(root: Path, code: str):
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames:
            new_name = name
            for token in PLACEHOLDER_TOKENS:
                if token in new_name:
                    new_name = new_name.replace(token, code)
            if new_name != name:
                (Path(dirpath) / name).rename(Path(dirpath) / new_name)
        for name in dirnames:
            new_name = name
            for token in PLACEHOLDER_TOKENS:
                if token in new_name:
                    new_name = new_name.replace(token, code)
            if new_name != name:
                (Path(dirpath) / name).rename(Path(dirpath) / new_name)


def replace_placeholders_in_contents(root: Path, code: str):
    reps = {token: code for token in PLACEHOLDER_TOKENS}
    text_exts = {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".json",
        ".txt",
        ".md",
        ".xml",
        ".svg",
        ".py",
        ".yaml",
        ".yml",
        ".ini",
        ".cfg",
        ".ts",
        ".tsx",
        ".jsx",
        ".svelte",
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in ("__MACOSX", ".git", ".svn", ".DS_Store")
        ]
        for fname in filenames:
            if fname in (".DS_Store",):
                continue
            p = Path(dirpath) / fname
            if p.suffix.lower() in text_exts or is_text_file(p):
                replace_in_file(p, reps)


def extract_template_to(template_zip: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template_zip, "r") as zf:
        zf.extractall(dest)
    junk = dest / "__MACOSX"
    if junk.exists():
        shutil.rmtree(junk, ignore_errors=True)


def move_children(src_dir: Path, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for child in src_dir.iterdir():
        target = dest_dir / child.name
        if target.exists():
            if child.is_dir():
                for root, dirs, files in os.walk(child):
                    rel = Path(root).relative_to(child)
                    (target / rel).mkdir(parents=True, exist_ok=True)
                    for f in files:
                        srcf = Path(root) / f
                        dstf = target / rel / f
                        shutil.copy2(srcf, dstf)
            else:
                shutil.copy2(child, target)
        else:
            shutil.move(str(child), str(target))


def flatten_if_needed(temp_dir: Path, dest: Path, code: str):
    children = [
        c for c in temp_dir.iterdir() if c.name not in (".DS_Store", "__MACOSX")
    ]
    if len(children) == 1 and children[0].is_dir():
        move_children(children[0], dest)
    else:
        picked = [
            c
            for c in children
            if c.is_dir() and (c.name in PLACEHOLDER_DIR_CANDIDATES or c.name == code)
        ]
        already = set()
        for c in picked:
            move_children(c, dest)
            already.add(c)
        for c in children:
            if c not in already:
                move_children(c, dest)


def flatten_named_child(dest: Path, name: str):
    child = dest / name
    if child.exists() and child.is_dir():
        move_children(child, dest)
        safe_rmtree(child)


# -------------------------
# DATA & MAPPINGS
# -------------------------

_LESSON_META = {}


def _pair_base_for_unit(unit: int) -> int:
    # Units grouped as (1,2), (3,4), (5,6), ...
    return unit if unit % 2 == 1 else unit - 1


def _compute_books_for_unit(unit: int):
    base = _pair_base_for_unit(unit)
    b1 = STUDENT_BOOK.get(str(base), "")
    b2 = STUDENT_BOOK.get(str(base + 1), "")
    return b1, b2


def _skill_for_unit(unit: int) -> str:
    # Prefer exact, else fall back to first unit in the pair. No "TBD" fallback.
    exact = SKILL_BY_UNIT.get(f"Unit {unit}")
    if exact:
        return exact
    base = _pair_base_for_unit(unit)
    return SKILL_BY_UNIT.get(f"Unit {base}", "")


def _build_xml_replacements(unit: int, lesson: int):
    """
    Build token -> value map for XML:
      Lvl_3_Unt_{u}_Lsn_{l}:skill
      Lvl_3_Unt_{u}_Lsn_{l}:book1
      Lvl_3_Unt_{u}_Lsn_{l}:book2
      Lvl_3_Unt_{u}_Lsn_{l}:read_aloud_card
    (supports both {braced} and bare forms; braced are replaced first)
    """
    prefix = f"Lvl_3_Unt_{unit}_Lsn_{lesson}"
    skill_val = _skill_for_unit(unit)
    book1, book2 = _compute_books_for_unit(unit)
    rac_list = (_LESSON_META.get((unit, lesson)) or {}).get("read_aloud_cards") or []
    read_aloud_card = str(rac_list[0]) if rac_list else ""

    # Bare tokens
    repl_bare = {
        f"{prefix}:skill": skill_val,
        f"{prefix}:book1": book1,
        f"{prefix}:book2": book2,
        f"{prefix}:read_aloud_card": read_aloud_card,
    }
    # Replace {braced} forms FIRST, then bare tokens
    repl = {f"{{{k}}}": v for k, v in repl_bare.items()}
    repl.update(repl_bare)
    return repl


def _parse_range(s: str) -> list[int]:
    """
    Accepts:
      - 'all' -> []
      - '1-30'
      - '1,2,5-7'
    Returns a sorted, deduped list of positive ints.
    Empty list means 'no filter' (i.e., include all).
    """
    s = (s or "").strip().lower()
    if s in ("", "all", "any", "*"):
        return []
    out = set()
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                a, b = int(a), int(b)
            except ValueError:
                continue
            if a > b:
                a, b = b, a
            out.update(range(max(1, a), b + 1))
        else:
            try:
                out.add(max(1, int(part)))
            except ValueError:
                pass
    return sorted(out)


def load_rows_from_units(
    data_py_path: Path,
    target_units: list[int] | None = None,
    lesson_min: int = 1,
    lesson_max: int = 10,
):
    """
    Reads data = [ ... ] from your data_py and returns
    [(unit, lesson, code), ...] for lessons within [lesson_min, lesson_max].
    If target_units is None or an empty list, includes ALL units found.
    Also fills _LESSON_META with read_aloud_cards per (unit, lesson).
    """
    ns = runpy.run_path(str(data_py_path))
    data = ns.get("data", [])

    global _LESSON_META
    _LESSON_META = {}

    unit_filter = set(target_units or [])  # empty set -> include all
    seen = set()
    rows = []

    for item in data:
        try:
            unit = int(item.get("unit"))
            lesson = int(item.get("lesson"))
            code = str(item.get("code") or "")
        except Exception:
            continue

        if not code:
            continue
        if unit_filter and unit not in unit_filter:
            continue
        if not (lesson_min <= lesson <= lesson_max):
            continue

        key = (unit, lesson)
        if key in seen:
            continue
        seen.add(key)
        rows.append((unit, lesson, code))
        _LESSON_META[key] = {
            "read_aloud_cards": list(item.get("read_aloud_cards") or [])
        }

    rows.sort(key=lambda t: (t[0], t[1]))
    return rows


# -------------------------
# XML WRITER
# -------------------------


def _write_xml_and_cmi5(dest: Path, unit: int, lesson: int, xml_root: Path):
    """
    Copy per-lesson XML into data/xml and also create a root cmi5.xml with token replacement.
    Looks for source at:
      <xml_root>/xml_output_lvl3_u{unit}/level_3_unit_{unit}_lesson_{lesson}.xml
    Writes:
      {dest}/data/xml/level_3_unit_{unit}_lesson_{lesson}.xml
      {dest}/cmi5.xml
    """
    xml_src = (
        xml_root
        / f"xml_output_lvl3_u{unit}"
        / f"level_3_unit_{unit}_lesson_{lesson}.xml"
    )
    print(f"[xml] looking for {xml_src}")
    if not xml_src.exists():
        print(f"[skip] {dest}: missing source XML: {xml_src}")
        return

    try:
        xml_text = xml_src.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return

    # Replace tokens (braced first, then bare)
    repl = _build_xml_replacements(unit, lesson)
    for k, v in repl.items():
        xml_text = xml_text.replace(k, v)

    # # Write lesson xml under data/xml
    # data_xml_dir = dest / "data" / "xml"
    # data_xml_dir.mkdir(parents=True, exist_ok=True)
    # (data_xml_dir / f"level_3_unit_{unit}_lesson_{lesson}.xml").write_text(
    #     xml_text, encoding="utf-8"
    # )

    # Also write cmi5.xml at the package root
    (dest / "cmi5.xml").write_text(xml_text, encoding="utf-8")


# -------------------------
# AUDIO COPIER
# -------------------------


def _copy_lesson_audio(dest: Path, unit: int, lesson: int, audio_root: Path):
    """
    Copy all lesson audio files for this unit/lesson into the package's contents/audio folder.

    Source (inside audio_root):
        level_3_unit_{unit}_lesson_{lesson}_*.mp3   # underscore ensures lesson boundary

    Destination:
        {dest}/contents/audio/<same filename>
    """
    src_dir = Path(audio_root)
    if not src_dir.exists():
        print(f"[audio][warn] audio root not found: {src_dir}")
        return 0

    # Require an underscore right after the lesson number to avoid matching 10 when lesson=1, etc.
    hard_glob = f"level_3_unit_{unit}_lesson_{lesson}_*.mp3"
    boundary_regex = re.compile(
        rf"^level_3_unit_{unit}_lesson_{lesson}(?:_|$).*\.mp3$", re.IGNORECASE
    )

    target_dir = dest / "contents" / "audio"
    target_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for p in src_dir.glob(hard_glob):
        try:
            shutil.copy2(p, target_dir / p.name)
            count += 1
        except Exception as e:
            print(f"[audio][err] failed to copy {p} -> {target_dir}: {e}")

    for p in src_dir.glob(f"level_3_unit_{unit}_lesson_{lesson}*.mp3"):
        if boundary_regex.match(p.name) and not (target_dir / p.name).exists():
            try:
                shutil.copy2(p, target_dir / p.name)
                count += 1
            except Exception as e:
                print(f"[audio][err] failed to copy {p} -> {target_dir}: {e}")

    print(
        f"[audio] {dest.name}: copied {count} file(s) for unit {unit} lesson {lesson}"
    )
    return count


# -------------------------
# MAIN FLOW
# -------------------------


def clone_from_zip_for_rows(
    template_zip: Path, out_root: Path, rows, xml_root: Path, audio_root: Path
):
    results = []
    for unit, lesson, code in rows:
        unit_dir = out_root / f"unit_{unit}"
        dest = unit_dir / code

        if dest.exists():
            shutil.rmtree(dest)
        unit_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = out_root / f"._tmp_extract_u{unit}_l{lesson}"
        safe_rmtree(temp_dir)
        extract_template_to(template_zip, temp_dir)

        dest.mkdir(parents=True, exist_ok=True)
        flatten_if_needed(temp_dir, dest, code)
        safe_rmtree(temp_dir)

        rename_placeholders_in_tree(dest, code)
        replace_placeholders_in_contents(dest, code)

        # remove accidental nested folders
        flatten_named_child(dest, "xcode")
        flatten_named_child(dest, code)

        # add lesson xml + root cmi5.xml
        print(f"[pkg] unit={unit} lesson={lesson} code={code} -> {dest}")
        _write_xml_and_cmi5(dest, unit, lesson, xml_root)

        # copy lesson audio
        _copy_lesson_audio(dest, unit, lesson, audio_root)

        results.append(str(dest))
    return results


def cleanup_old_lesson_dirs(out_root: Path):
    for unit_dir in out_root.glob("unit_*"):
        if unit_dir.is_dir():
            for child in unit_dir.iterdir():
                if child.is_dir() and child.name.startswith("lesson_"):
                    safe_rmtree(child)


def main():
    ap = argparse.ArgumentParser(
        description="Build per-lesson packages from a template zip."
    )
    ap.add_argument("--template-zip", default="data/xxxxx.zip")
    ap.add_argument("--data-py", default="data/level_3.py")
    ap.add_argument("--out-root", default="data/output")
    ap.add_argument("--xml-root", default="data/xml")
    ap.add_argument("--audio-root", default=DEFAULT_AUDIO_ROOT)
    ap.add_argument(
        "--units",
        default="1-3",
        help="Units to include: 'all', '1-30', or '1,2,5-7'. Default: 1-3",
    )
    ap.add_argument(
        "--lessons",
        default="1-10",
        help="Lessons to include per unit: '1-10' or '1,3,5'. Default: 1-10",
    )
    args = ap.parse_args()

    template_zip = Path(args.template_zip)
    data_py = Path(args.data_py)
    out_root = Path(args.out_root)
    xml_root = Path(args.xml_root)
    audio_root = Path(args.audio_root)

    print(f"[config] template_zip={template_zip}")
    print(f"[config] data_py={data_py}")
    print(f"[config] out_root={out_root}")
    print(f"[config] xml_root={xml_root}")
    print(f"[config] audio_root={audio_root}")

    out_root.mkdir(parents=True, exist_ok=True)

    if not template_zip.exists():
        raise FileNotFoundError(f"Template zip not found: {template_zip}")
    if not data_py.exists():
        raise FileNotFoundError(f"Units data not found: {data_py}")
    if not xml_root.exists():
        print(f"[warn] XML root not found: {xml_root} (skipping XML copy)")
    if not audio_root.exists():
        print(f"[warn] Audio root not found: {audio_root} (skipping audio copy)")

    # Parse unit filter
    unit_list = _parse_range(args.units)  # [] means include all
    # Parse lessons filter
    lesson_list = _parse_range(args.lessons)
    if lesson_list:
        lesson_min, lesson_max = min(lesson_list), max(lesson_list)
    else:
        lesson_min, lesson_max = 1, 10

    rows = load_rows_from_units(
        data_py_path=data_py,
        target_units=unit_list if unit_list else None,  # None => include all
        lesson_min=lesson_min,
        lesson_max=lesson_max,
    )

    print("Discovered (unit, lesson) -> code:")
    for unit, lesson, code in rows:
        print(f"  unit_{unit} lesson_{lesson} -> {code}")

    created = clone_from_zip_for_rows(
        template_zip, out_root, rows, xml_root, audio_root
    )
    cleanup_old_lesson_dirs(out_root)

    print("\nCreated destinations (sample):")
    for path in created[:20]:
        print(" ", path)
    if len(created) > 20:
        print(f"  ...and {len(created)-20} more")


if __name__ == "__main__":
    main()
