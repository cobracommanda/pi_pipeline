#!/usr/bin/env python3
import json, re
from pathlib import Path

MAIN_FILE_RE = re.compile(r"^Y\d+_TG_L\d+_U\d+\.json$")

# ---------------- helpers ----------------


def iter_nodes(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_nodes(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_nodes(item)


def _normalize_dashes(s: str) -> str:
    return (s or "").translate(
        {
            0x2013: "-",
            0x2014: "-",
            0x2011: "-",
            0x2212: "-",
            0x2012: "-",
            0x2043: "-",
        }
    )


def _norm(s: str) -> str:
    s = _normalize_dashes(s)
    return re.sub(r"\s+", " ", s).strip()


def _unique_ordered(seq, key=lambda x: x):
    seen, out = set(), []
    for x in seq:
        k = key(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def _fix_page_ranges(text: str) -> str:
    """Normalize 'pages 12 13' / 'pages 12–13' / 'pages 1213' / 'pages 811'."""

    # 1) dash OR whitespace as separator (requires at least one space if no dash)
    def repl_sep(m):
        a, b = m.group(1), m.group(2)
        return f"pages {int(a)}-{int(b)}"

    text = re.sub(
        r"(?i)\bpages?\s+(\d{1,2})\s*(?:[-–—−]|\s+)\s*(\d{1,2})\b", repl_sep, text
    )

    # 2) glued digits (3 or 4 digits): 811 -> 8-11, 1213 -> 12-13, 2021 -> 20-21
    def repl_glued(m):
        block = m.group(1)
        a, b = (block[0], block[1:]) if len(block) == 3 else (block[:2], block[2:])
        return f"pages {int(a)}-{int(b)}"

    text = re.sub(r"(?i)\bpages?\s+(\d{3,4})\b", repl_glued, text)

    return text


def _style_key(s: str) -> str:
    """Normalize style names & strip override '+'."""
    s = (s or "").replace("–", "-").replace("—", "-").strip()
    s = re.sub(r"\s*\+\s*$", "", s)  # caption_centered+ -> caption_centered
    s = s.lower().replace("-", "_").replace(" ", "_")
    s = re.sub(r"_+", "_", s).strip("_")
    return s


# ---------------- core API ----------------


def extract_captions_from_doc(doc, centered_numeric_only: bool = True) -> list[str]:
    """
    Return ordered, de-duplicated list of strings from:
      - style 'caption' (always)
      - style 'caption_centered' (kept only if it contains digits when centered_numeric_only=True)
    """
    out = []
    for node in iter_nodes(doc):
        if node.get("type") != "para":
            continue
        skey = _style_key(node.get("style", ""))
        if skey not in {"caption", "caption_centered"}:
            continue

        runs = node.get("runs", [])
        pieces = [r.get("text", "") for r in runs if isinstance(r, dict)]
        pieces = _unique_ordered(pieces, key=_norm)  # de-dupe within paragraph
        txt = _norm("".join(pieces))
        if not txt:
            continue

        if (
            skey == "caption_centered"
            and centered_numeric_only
            and not re.search(r"\d", txt)
        ):
            continue

        out.append(_fix_page_ranges(txt))

    return _unique_ordered(out, key=_norm)


def find_main_files(base_dir: Path):
    return sorted(
        (p for p in base_dir.rglob("*.json") if MAIN_FILE_RE.match(p.name)),
        key=lambda p: p.name,
    )


def collect_unit_captions(
    base_dir: Path, join_with: str | None = None, centered_numeric_only: bool = True
) -> dict[str, list[str] | str]:
    """
    Walk base_dir, read each main unit JSON, and return {file_stem: captions}.
    - join_with=None -> list per file (default)
    - join_with="\\n" (or ", ") -> single string per file
    """
    results = {}
    for jf in find_main_files(base_dir):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Could not read {jf}: {e}")
            continue
        captions = extract_captions_from_doc(
            data, centered_numeric_only=centered_numeric_only
        )
        results[jf.stem] = (
            join_with.join(captions) if join_with is not None else captions
        )
    return results


# ----------- optional run block (edit paths or import instead) -------------

if __name__ == "__main__":
    BASE_DIR = Path(
        "/Users/DRobinson/Desktop/PI_MASTER_lv3/units"
    )  # <-- change if needed
    OUTPUT = Path("unit_caption_texts.json")
    result = collect_unit_captions(BASE_DIR)  # both styles by default
    OUTPUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {OUTPUT} with {len(result)} entries.")
