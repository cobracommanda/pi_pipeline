
#!/usr/bin/env python3
import json, re, argparse
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import OrderedDict
from typing import Iterable, Tuple, Optional, Any, Dict

# ===== Namespaces =====
NS = {
    "cs": "https://w3id.org/xapi/profiles/cmi5/v1/CourseStructure.xsd",
    "bec": "https://cmi5extension.benchmarkuniverse.com/cmi5/BecPlayerExtension.xsd",
}
ET.register_namespace("", NS["cs"])
ET.register_namespace("bec", NS["bec"])


# ===== Utilities =====
def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r'[“”"\']', "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "section"


def canonical_block_title(section: str) -> str:
    low = (section or "").strip().lower()
    if low in ("unit intro", "intro", "lesson opener"):
        return "Lesson Opener"
    if "warm-up" in low or "warm up" in low or "review and repetition" in low:
        return "Warm-up Review and Repetition"
    if "multimodal mini" in low:
        return "Multimodal Minilesson"
    if "vocabulary booster" in low:
        return "Vocabulary Booster"
    if "apply to reading and writing" in low:
        return "Apply to Reading and Writing"
    if "additional supports" in low:
        return "Additional Supports"
    return section or "Lesson"


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(str(v))
    except Exception:
        try:
            return int(float(str(v)))
        except Exception:
            return default


# ===== XML Builder =====
def build_xml_for_sheet(
    sheet: dict, xcode: Optional[str] = None
) -> Tuple[Optional[ET.ElementTree], str]:
    """
    Build CourseStructure XML for a single sheet.
    Returns (xml_tree_or_None_if_skipped, base_filename_stem).
    """
    sheet_name = str(sheet.get("sheet_name", "")).strip() or "Sheet"
    base = str(sheet.get("base", "")).strip() or slugify(sheet_name)
    xcode = xcode or sheet.get("xcode") or sheet.get("code") or "XCODE"
    xcode = str(xcode).strip()

    level_str = str(sheet.get("level", "")).strip()
    unit_str = str(sheet.get("unit", "")).strip()
    lesson_num = _to_int(sheet.get("lesson_num", 0), 0)
    unit_num = _to_int(unit_str, 0)

    # placeholders for SKUs
    ph_skill = f"{sheet_name}:skill"
    ph_book1 = f"{sheet_name}:book1"
    ph_book2 = f"{sheet_name}:book2"
    ph_read = f"{sheet_name}:read_aloud_card"

    # root + course
    root = ET.Element(ET.QName(NS["cs"], "courseStructure"))
    course = ET.SubElement(
        root,
        ET.QName(NS["cs"], "course"),
        {"id": f"http://benchmarkuniverse.com/{xcode}"},
    )

    # titles/descriptions with dynamic level/unit + {skill} placeholder
    title = ET.SubElement(course, ET.QName(NS["cs"], "title"))
    ET.SubElement(title, ET.QName(NS["cs"], "langstring")).text = (
        f"Benchmark Phonics Intervention - Level {level_str} Unit {unit_str} {{{ph_skill}}}"
    )

    desc = ET.SubElement(course, ET.QName(NS["cs"], "description"))
    ET.SubElement(desc, ET.QName(NS["cs"], "langstring"), {"lang": "en-US"}).text = (
        f"Benchmark Phonics Intervention - Level {level_str} Unit {unit_str} {{{ph_skill}}}"
    )

    # player config
    ET.SubElement(course, ET.QName(NS["bec"], "packageVersion")).text = "1.0"
    sp = ET.SubElement(course, ET.QName(NS["bec"], "showPlayer"))
    ET.SubElement(sp, ET.QName(NS["bec"], "section")).text = "all"
    header = ET.SubElement(course, ET.QName(NS["bec"], "playerHeader"))
    ET.SubElement(header, ET.QName(NS["bec"], "backgroundColor")).text = "#eee"
    ET.SubElement(header, ET.QName(NS["bec"], "programLogoUrl")).text = (
        "contents/images/logo.png"
    )
    sidebar = ET.SubElement(course, ET.QName(NS["bec"], "playerSideBar"))
    ET.SubElement(sidebar, ET.QName(NS["bec"], "tableOfContentLabel")).text = (
        "Table of Contents"
    )
    ET.SubElement(sidebar, ET.QName(NS["bec"], "additionalResourcesLabel")).text = (
        "Lesson Materials"
    )

    # additional resources
    add = ET.SubElement(course, ET.QName(NS["bec"], "additionalResources"))

    def add_res(title_txt, desc_txt, sku_txt):
        res = ET.SubElement(add, ET.QName(NS["bec"], "resource"))
        rt = ET.SubElement(res, ET.QName(NS["bec"], "title"))
        ET.SubElement(rt, ET.QName(NS["cs"], "langstring")).text = title_txt
        rd = ET.SubElement(res, ET.QName(NS["bec"], "description"))
        ET.SubElement(rd, ET.QName(NS["cs"], "langstring")).text = desc_txt
        ET.SubElement(res, ET.QName(NS["bec"], "sku")).text = sku_txt
        ET.SubElement(res, ET.QName(NS["bec"], "role")).text = "student"

    # Student Book 1 (current unit)
    add_res(
        f"Reading Collection Unit {unit_str}", f"Unit {unit_str} Student Book", ph_book1
    )
    # Student Book 2 (unit + 1) — keep SKU as ':book2'
    unit_plus = unit_num + 1
    add_res(
        f"Reading Collection Unit {unit_plus}",
        f"Unit {unit_plus} Student Book",
        ph_book2,
    )
    # Read-Aloud Card
    add_res("Read-Aloud Card", f"Unit {unit_str} Student Book", ph_read)

    toc = sheet.get("toc", [])
    if not toc:
        print(f"[WARN] Skipping: Sheet {sheet_name} has no 'toc'.")
        return None, base

    # group and title map
    grouped = OrderedDict()
    for item in toc:
        grouped.setdefault(canonical_block_title(item.get("section")), []).append(item)

    title_by_slide = {}
    slide_numbers = []
    for t in toc:
        sn = _to_int(t.get("slide_number"), None)
        if sn is None:
            continue
        slide_numbers.append(sn)
        title_by_slide[sn] = t.get("title")

    if not slide_numbers:
        print(f"[WARN] Skipping: Sheet {sheet_name} has empty/invalid 'toc'.")
        return None, base

    last_slide_num = max(slide_numbers)

    block_index = -1
    for block_title, items in grouped.items():
        # opener block
        if block_title == "Lesson Opener":
            block_el = ET.SubElement(
                root,
                ET.QName(NS["cs"], "block"),
                {
                    "id": f"http://benchmarkuniverse.com/{xcode}/block/lesson_opener_block"
                },
            )
            bt = ET.SubElement(block_el, ET.QName(NS["cs"], "title"))
            ET.SubElement(bt, ET.QName(NS["cs"], "langstring")).text = block_title
            bd = ET.SubElement(block_el, ET.QName(NS["cs"], "description"))
            ET.SubElement(
                bd, ET.QName(NS["cs"], "langstring"), {"lang": "en-US"}
            ).text = block_title

            for it in sorted(items, key=lambda x: _to_int(x.get("slide_number"), 0)):
                sn = _to_int(it.get("slide_number"), 0)
                au = ET.SubElement(
                    block_el,
                    ET.QName(NS["cs"], "au"),
                    {
                        "id": f"http://benchmarkuniverse.com/{xcode}/block/lesson_opener_lesson",
                        "moveOn": "NotApplicable",
                    },
                )
                at = ET.SubElement(au, ET.QName(NS["cs"], "title"))
                ET.SubElement(at, ET.QName(NS["cs"], "langstring")).text = (
                    title_by_slide.get(sn) or "Lesson Opener"
                )
                ad = ET.SubElement(au, ET.QName(NS["cs"], "description"))
                ET.SubElement(ad, ET.QName(NS["cs"], "langstring")).text = (
                    title_by_slide.get(sn) or "Lesson Opener"
                )
                ET.SubElement(au, ET.QName(NS["cs"], "url")).text = (
                    f"contents/lesson/{sn}.html"
                )
                ET.SubElement(au, ET.QName(NS["bec"], "teacherResource")).text = (
                    f"contents/teacherResources/support_{sn}.html"
                )
                sk = ET.SubElement(au, ET.QName(NS["bec"], "skill"))
                ET.SubElement(sk, ET.QName(NS["bec"], "code")).text = ph_skill
            continue

        # skip any inlined "Additional Supports" (we'll add one canonical block at end)
        if block_title == "Additional Supports":
            continue

        # standard blocks
        block_index += 1
        slug = slugify(items[0].get("section") if items else block_title)
        block_id = f"http://benchmarkuniverse.com/{xcode}/block{block_index}/lesson_{lesson_num}/{slug}"
        block_el = ET.SubElement(root, ET.QName(NS["cs"], "block"), {"id": block_id})

        bt = ET.SubElement(block_el, ET.QName(NS["cs"], "title"))
        ET.SubElement(bt, ET.QName(NS["cs"], "langstring")).text = block_title
        bd = ET.SubElement(block_el, ET.QName(NS["cs"], "description"))
        ET.SubElement(bd, ET.QName(NS["cs"], "langstring"), {"lang": "en-US"}).text = (
            block_title
        )

        seen = {}
        for it in sorted(items, key=lambda x: _to_int(x.get("slide_number"), 0)):
            sn = _to_int(it.get("slide_number"), 0)
            au_title = title_by_slide.get(sn) or f"Slide {sn}"
            key = slugify(au_title)
            seen[key] = seen.get(key, 0) + 1
            au_slug = key if seen[key] == 1 else f"{key}_{seen[key]}"
            au_id = f"{block_id.rsplit('/', 1)[0]}/{au_slug}"

            au = ET.SubElement(
                block_el,
                ET.QName(NS["cs"], "au"),
                {"id": au_id, "moveOn": "NotApplicable"},
            )
            at = ET.SubElement(au, ET.QName(NS["cs"], "title"))
            ET.SubElement(at, ET.QName(NS["cs"], "langstring")).text = au_title
            ad = ET.SubElement(au, ET.QName(NS["cs"], "description"))
            ET.SubElement(ad, ET.QName(NS["cs"], "langstring")).text = au_title
            ET.SubElement(au, ET.QName(NS["cs"], "url")).text = (
                f"contents/lesson/{sn}.html"
            )
            ET.SubElement(au, ET.QName(NS["bec"], "teacherResource")).text = (
                f"contents/teacherResources/support_{sn}.html"
            )
            sk = ET.SubElement(au, ET.QName(NS["bec"], "skill"))
            ET.SubElement(sk, ET.QName(NS["bec"], "code")).text = ph_skill

    # === FORCE: Additional Supports LAST, linking to last_slide + 1 ===
    block_index += 1
    add_block_id = f"http://benchmarkuniverse.com/{xcode}/block{block_index}/lesson_{lesson_num}/additional_supports"
    add_block = ET.SubElement(root, ET.QName(NS["cs"], "block"), {"id": add_block_id})
    bt = ET.SubElement(add_block, ET.QName(NS["cs"], "title"))
    ET.SubElement(bt, ET.QName(NS["cs"], "langstring")).text = "Additional Supports"
    bd = ET.SubElement(add_block, ET.QName(NS["cs"], "description"))
    ET.SubElement(bd, ET.QName(NS["cs"], "langstring"), {"lang": "en-US"}).text = (
        "Additional Supports"
    )

    au = ET.SubElement(
        add_block,
        ET.QName(NS["cs"], "au"),
        {
            "id": f"http://benchmarkuniverse.com/{xcode}/block{block_index}/lesson_{lesson_num}/additionalsupports_0",
            "moveOn": "NotApplicable",
        },
    )
    at = ET.SubElement(au, ET.QName(NS["cs"], "title"))
    ET.SubElement(at, ET.QName(NS["cs"], "langstring")).text = "Additional Supports"
    ad = ET.SubElement(au, ET.QName(NS["cs"], "description"))
    ET.SubElement(ad, ET.QName(NS["cs"], "langstring")).text = "Additional Supports"
    # IMPORTANT: last page + 1 as requested
    ET.SubElement(au, ET.QName(NS["cs"], "url")).text = (
        f"contents/lesson/{last_slide_num + 1}.html"
    )

    return ET.ElementTree(root), base


# ===== Input Normalization =====
def _extract_sheets(data: Any) -> Iterable[Tuple[Dict[str, Any], Optional[str]]]:
    """
    Yield (sheet_dict, xcode) pairs from:
      - [ { ..., "sheet": {...}, "code": "X..." }, ... ]   # new format
      - { "sheet": {...}, "code": "X..." }                 # single record
      - { "sheets": [ {...}, ... ] }                       # legacy workbook
      - { ... }                                            # raw sheet
    """
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            if "sheet" in item and isinstance(item["sheet"], dict):
                yield item["sheet"], (item.get("code") or item.get("xcode"))
            elif "sheets" in item and isinstance(item["sheets"], list):
                for s in item["sheets"]:
                    if isinstance(s, dict):
                        yield s, (item.get("code") or s.get("xcode"))
            else:
                yield item, (item.get("code") or item.get("xcode"))
        return

    if isinstance(data, dict):
        if "sheets" in data and isinstance(data["sheets"], list):
            for s in data["sheets"]:
                if isinstance(s, dict):
                    yield s, (data.get("code") or s.get("xcode"))
            return
        if "sheet" in data and isinstance(data["sheet"], dict):
            yield data["sheet"], (data.get("code") or data["sheet"].get("xcode"))
            return
        yield data, (data.get("code") or data.get("xcode"))
        return

    raise SystemExit("Unsupported input JSON structure.")


# ===== Writer (per-unit only) =====
def _write_per_unit(
    tree: ET.ElementTree, base: str, outdir: Path, level_val: Any, unit_val: Any
) -> Path:
    """Write XML once into outdir/xml_output_lvl{level}_u{unit}/{base}.xml"""
    unit_num = _to_int(unit_val, 0)
    level_num = _to_int(level_val, 0)
    unit_dir = outdir / f"xml_output_lvl{level_num}_u{unit_num}"
    unit_dir.mkdir(parents=True, exist_ok=True)
    out_path = unit_dir / f"{base}.xml"
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


# ===== CLI =====
def main():
    ap = argparse.ArgumentParser(
        description="Generate CourseStructure XML per sheet; outputs once into per-unit folders xml_output_lvl{level}_u{unit}/."
    )
    ap.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="JSON file (list of lessons with 'sheet', or legacy forms).",
    )
    ap.add_argument(
        "-o", "--outdir", required=True, type=Path, help="Root output directory."
    )
    args = ap.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    args.outdir.mkdir(parents=True, exist_ok=True)

    total = 0
    written = 0
    skipped = 0

    for sheet_obj, xcode in _extract_sheets(data):
        total += 1
        tree, base = build_xml_for_sheet(sheet_obj, xcode=xcode)
        if tree is None:
            skipped += 1
            continue
        out_path = _write_per_unit(
            tree, base, args.outdir, sheet_obj.get("level"), sheet_obj.get("unit")
        )
        print(
            f"Wrote {out_path}   (L{sheet_obj.get('level')} U{sheet_obj.get('unit')} Lesson {sheet_obj.get('lesson_num')}, code={xcode or 'XCODE'})"
        )
        written += 1

    print(f"\nDone. total={total}, written={written}, skipped(no toc)={skipped}")
    if written == 0:
        raise SystemExit("No sheets written. Check input structure.")


if __name__ == "__main__":
    main()
