import re, json
from collections import defaultdict

WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']*")


def parse_slide_index(path: str) -> int:
    m = re.search(r"slides\s*>\s*\[(\d+)\]", path)
    return int(m.group(1)) if m else -1


def extract_words_from_notes(notes: str):
    """
    Extract tokens that follow 'the word'/'the words' up to the next '>'.
    Keeps both words separated by 'and', commas, etc., removes fillers.
    """
    anomalies = []
    if not notes:
        return [], ["empty notes"]

    m = re.search(r"\bthe\s+words?\b", notes, flags=re.IGNORECASE)
    if not m:
        # OK for slide 1; not an anomaly unless role later claims 2/3/4
        return [], anomalies

    # take everything after 'the word(s)' up to the next '>'
    tail = notes[m.end() :]
    tail = tail.split(">", 1)[0]
    tail = tail.lstrip(" :,-.;")

    tokens = WORD_RE.findall(tail)
    fillers = {"and", "the", "word", "words"}
    words = [t for t in tokens if t.lower() not in fillers]

    # de-dupe preserving order
    seen, deduped = set(), []
    for w in words:
        wl = w.lower()
        if wl not in seen:
            seen.add(wl)
            deduped.append(w)

    if not deduped:
        anomalies.append("word(s) phrase present but no tokens parsed")

    return deduped, anomalies


def classify_role(notes: str) -> str:
    if not notes:
        return "other"
    s = notes.lower()
    if "show vocabulary card" in s and "word" not in s:
        return "vocab_slide_1"
    if "show the vocabulary card" in s and "words" in s:
        return "vocab_slide_4"
    if "show the vocabulary card" in s and "word" in s:
        return "vocab_slide_2_or_3"
    return "other"


def extract_vocab_records_with_sequence(data):
    """
    Input: list of dicts {sheet_name, path, notes}
    Output: list of dicts enriched with:
      - slide_index (int)
      - words (list[str])
      - role (vocab_slide_1|_2|_3|_4|other)
      - sequence (1..4 or None)  <-- lesson-local order
      - paired_words (list[str] or None) on sequence==4
      - anomalies (list[str])
    """
    records = []
    # 1) Parse basics
    for rec in data:
        sheet = rec.get("sheet_name", "")
        path = rec.get("path", "")
        notes = rec.get("notes", "")
        slide_index = parse_slide_index(path)
        words, anomalies = extract_words_from_notes(notes)
        role = classify_role(notes)

        records.append(
            {
                "sheet_name": sheet,
                "slide_index": slide_index,
                "path": path,
                "raw_notes": notes,
                "words": words,
                "role": role,
                "sequence": None,
                "paired_words": None,
                "anomalies": anomalies,
            }
        )

    # 2) Group by lesson (sheet_name) to assign sequences and validate
    by_sheet = defaultdict(list)
    for r in records:
        by_sheet[r["sheet_name"]].append(r)

    for sheet, items in by_sheet.items():
        items.sort(key=lambda r: r["slide_index"])

        # Identify candidates by role
        s1 = [r for r in items if r["role"] == "vocab_slide_1"]
        s23 = [
            r
            for r in items
            if r["role"] in ("vocab_slide_2_or_3", "vocab_slide_2", "vocab_slide_3")
        ]
        s4 = [r for r in items if r["role"] == "vocab_slide_4"]

        # Basic expectations
        if len(s1) != 1:
            for r in items:
                r["anomalies"].append(f"expected exactly one slide_1, found {len(s1)}")
        if len(s23) != 2:
            for r in items:
                r["anomalies"].append(
                    f"expected exactly two slide_2/3, found {len(s23)}"
                )
        if len(s4) != 1:
            for r in items:
                r["anomalies"].append(f"expected exactly one slide_4, found {len(s4)}")

        # Assign sequence for slide 1 (prefer earliest matching role)
        if s1:
            s1_sorted = sorted(s1, key=lambda r: r["slide_index"])
            s1_sorted[0]["sequence"] = 1
            if len(s1_sorted[0]["words"]) != 0:
                s1_sorted[0]["anomalies"].append("slide_1 should have 0 words")

        # Disambiguate 2 vs 3 by slide_index
        if len(s23) >= 1:
            s23_sorted = sorted(s23, key=lambda r: r["slide_index"])
            if len(s23_sorted) >= 1:
                s23_sorted[0]["role"] = "vocab_slide_2"
                s23_sorted[0]["sequence"] = 2
                if len(s23_sorted[0]["words"]) != 1:
                    s23_sorted[0]["anomalies"].append("slide_2 should have 1 word")
            if len(s23_sorted) >= 2:
                s23_sorted[1]["role"] = "vocab_slide_3"
                s23_sorted[1]["sequence"] = 3
                if len(s23_sorted[1]["words"]) != 1:
                    s23_sorted[1]["anomalies"].append("slide_3 should have 1 word")

        # Assign sequence for slide 4 and pair words from 2&3
        if s4:
            s4_item = sorted(s4, key=lambda r: r["slide_index"])[-1]
            s4_item["sequence"] = 4
            if len(s4_item["words"]) < 2:
                s4_item["anomalies"].append("slide_4 should have >=2 words")

            # Only set paired_words if BOTH seq 2 and seq 3 are present
            w2 = next(
                (r["words"][0] for r in items if r.get("sequence") == 2 and r["words"]),
                None,
            )
            w3 = next(
                (r["words"][0] for r in items if r.get("sequence") == 3 and r["words"]),
                None,
            )
            if w2 and w3:
                s4_item["paired_words"] = [w2, w3]
                # consistency check with slide_4 words (if any)
                have = {w.lower() for w in s4_item["words"]}
                need = {w2.lower(), w3.lower()}
                if have and not need.issubset(have):
                    s4_item["anomalies"].append(
                        f"slide_4 words {sorted(have)} do not include slide 2/3 words {sorted(need)}"
                    )
            else:
                s4_item["paired_words"] = None

        # Flag any slides that still have no sequence but look vocab-like
        for r in items:
            if r["sequence"] is None and r["role"].startswith("vocab_slide"):
                r["anomalies"].append(
                    "vocab-like slide did not get a sequence (pattern broken)"
                )

    return records


def extract_sheetname_and_pairs(data):
    """
    Input: full lesson JSON [{sheet_name, path, notes}, ...]
    Output: [{sheet_name, paired_words}, ...] one object per lesson.

    NEW precedence (to honor explicit slide-4 text like
    '<visual: Show the vocabulary card and the words compelled and swarms>'):
      1) Use slide_4's own parsed words if it has >=2.
      2) Else use paired_words from seq 2 & 3 if BOTH present.
      3) Else, stitch available words from seq 2 & 3 (may be <2).
    """
    from collections import defaultdict

    records = extract_vocab_records_with_sequence(data)

    by_sheet = defaultdict(list)
    for r in records:
        by_sheet[r["sheet_name"]].append(r)

    results = []
    for sheet, items in by_sheet.items():
        s4 = next((r for r in items if r.get("sequence") == 4), None)

        # 1) Prefer slide_4's explicit words if two or more are present
        if s4 and len(s4.get("words", [])) >= 2:
            pairs = s4["words"]

        # 2) Else prefer explicit 2+3 pairing if BOTH exist
        elif s4 and s4.get("paired_words") and len(s4["paired_words"]) >= 2:
            pairs = s4["paired_words"]

        # 3) Else stitch from whatever is available in seq 2 & 3
        else:
            w2 = next(
                (r["words"][0] for r in items if r.get("sequence") == 2 and r["words"]),
                None,
            )
            w3 = next(
                (r["words"][0] for r in items if r.get("sequence") == 3 and r["words"]),
                None,
            )
            pairs = [w for w in (w2, w3) if w]

        results.append({"sheet_name": sheet, "paired_words": pairs})

    return results


# --- Example CLI usage (optional) ---
if __name__ == "__main__":
    with open("/Users/DRobinson/Desktop/pi_pipeline/vocab.json", "r") as f:
        data = json.load(f)

    pairs = extract_sheetname_and_pairs(data)
    with open("vocab_card_pairs.json", "w") as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    print("Wrote parsed_vocab_with_sequence.json and vocab_card_pairs.json")
