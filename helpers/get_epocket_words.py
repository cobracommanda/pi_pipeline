import json, re
from typing import List, Dict, Any

# Pattern 1: "... following words ... : word, word, ... >"
EPOCKET_FOLLOWING_RE = re.compile(
    r"following\W*words[^:]*:\s*(?P<list>[^>]+)",
    re.IGNORECASE | re.DOTALL,
)

# Pattern 2: "<visual: ... show words word, word, ... >"
SHOW_WORDS_RE = re.compile(
    r"<visual:\s*[^>]*show\s+(?:the\s+)?words?\s+(?P<list>[^>]+)>",
    re.IGNORECASE | re.DOTALL,
)


def sanitize_token(tok: str) -> str:
    """
    Strip non-alphanumeric chars but keep case (so 'I' stays 'I').
    """
    return re.sub(r"[^A-Za-z0-9]", "", tok).strip()


def split_list_text(list_text: str) -> List[str]:
    """
    Split a captured list into tokens:
      1) split on commas to preserve order
      2) then split each segment on whitespace (handles odd inputs)
      3) sanitize each token (remove punctuation)
    """
    parts: List[str] = []
    for seg in list_text.split(","):
        seg = seg.strip()
        if not seg:
            continue
        for w in re.split(r"\s+", seg):
            w = sanitize_token(w)
            if w:
                parts.append(w)
    return parts


def extract_words_from_notes(notes: str) -> List[str]:
    """
    Return the list of words parsed from notes, or [] if no explicit list found.
    Handles:
      - nested '<visual: <visual: ...'
      - 'following words ... :' lists
      - '<visual: ... show words ... >' lists
      - trailing text like 'in e-pocket chart.> Note: ...'
    """
    # Try 'following words ... :' anywhere
    m = EPOCKET_FOLLOWING_RE.search(notes)
    if m:
        return split_list_text(m.group("list"))

    # Try '<visual: ... show words ... >'
    m = SHOW_WORDS_RE.search(notes)
    if m:
        return split_list_text(m.group("list"))

    # No explicit list detected
    return []


def extract_epocket_bulletproof(
    file_path: str,
    output_path: str,
    as_arrays: bool = True,
) -> str:
    """
    Read epocket.json and write a parsed file to output_path.
      - If an explicit word list is detected, emit either:
          { sheet_name, path, words: [...] }  (as_arrays=True)
        or { sheet_name, path, notes: "<original>" } (as_arrays=False)
      - If no list is detected, always emit:
          { sheet_name, path, notes: "<original>" }
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    results: List[Dict[str, Any]] = []
    for entry in data:
        notes = (entry.get("notes") or "").strip()
        words = extract_words_from_notes(notes)

        base = {
            "sheet_name": entry.get("sheet_name", ""),
            "path": entry.get("path", ""),
        }

        if words and as_arrays:
            base["words"] = words
        else:
            base["notes"] = notes

        results.append(base)

    with open(output_path, "w") as out_f:
        json.dump(results, out_f, indent=2)

    print(f"✅ Export complete. File saved at: {output_path}")
    return output_path


# Example usage:
if __name__ == "__main__":
    # Arrays (default): lists become `words`, everything else stays as `notes`
    extract_epocket_bulletproof(
        "/Users/DRobinson/Desktop/pi_pipeline/epocket.json",
        "epocketWords.json",
        as_arrays=True,
    )

    # If you prefer to keep the original `notes` even for list entries:
    extract_epocket_bulletproof(
        "/Users/DRobinson/Desktop/pi_pipeline/epocket.json",
        "epocketLog.json",
        as_arrays=False,
    )
