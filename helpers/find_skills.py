#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

MAIN_FILE_RE = re.compile(r"^Y\d+_TG_L\d+_U\d+\.json$")
COMPANY = "Benchmark Education Company, LLC"


def iter_nodes(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_nodes(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_nodes(item)


def _norm(s: str) -> str:
    # normalize dashes + collapse spaces for dedupe comparisons
    s = (s or "").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s).strip()


def _unique_ordered(seq, key=lambda x: x):
    seen = set()
    out = []
    for x in seq:
        k = key(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def extract_footer_text(doc) -> str:
    """Return a single normalized, de-duplicated Footer-A string for this doc."""
    # Collect per-paragraph texts with run-level de-duplication
    para_texts = []
    for node in iter_nodes(doc):
        if node.get("type") == "para" and node.get("style") == "Footer-A":
            runs = node.get("runs", [])
            # de-dupe runs while preserving order (normalize for comparison)
            run_pieces = [r.get("text", "") for r in runs if isinstance(r, dict)]
            run_pieces = _unique_ordered(run_pieces, key=_norm)
            txt = "".join(run_pieces)
            if txt:
                para_texts.append(txt)

    if not para_texts:
        return ""

    # De-dupe whole paragraphs (after normalization)
    para_texts = _unique_ordered(para_texts, key=_norm)
    text = " ".join(para_texts)

    # Move company string to the end exactly once
    if COMPANY in text:
        # remove all occurrences then append once
        text_wo = _norm(text.replace(COMPANY, " "))
        text = (text_wo + " " + COMPANY).strip()
    else:
        text = _norm(text)

    return text


def find_main_files(base_dir: Path):
    return sorted(
        (p for p in base_dir.rglob("*.json") if MAIN_FILE_RE.match(p.name)),
        key=lambda p: p.name,
    )


def run(base_dir: Path, out_path: Path):
    results = {}
    for jf in find_main_files(base_dir):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not read {jf}: {e}")
            continue
        footer = extract_footer_text(data)
        results[jf.stem] = footer
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {out_path} with {len(results)} entries.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Extract Footer-A text from unit main JSON files (deduped)."
    )
    ap.add_argument(
        "base_dir",
        type=Path,
        help="Root folder containing unit subfolders (e.g., /Users/DRobinson/Desktop/PI_MASTER_lv3/units)",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("unit_footer_texts.json"),
        help="Output JSON (default: unit_footer_texts.json)",
    )
    args = ap.parse_args()
    run(args.base_dir, args.output)
# python helpers/find_skills.py "/Users/DRobinson/Desktop/PI_MASTER_lv3/units" -o "unit_footer_texts.json"
