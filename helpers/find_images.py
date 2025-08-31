#!/usr/bin/env python3
import json
import re
import unicodedata
from difflib import get_close_matches

# === Load your input ===
with open("/Users/DRobinson/Desktop/pi_pipeline/sound_spelling_cards.json", "r") as f:
    lessons = json.load(f)

# === Your reference filenames ===
image_filenames = [
    "Closed-Syllables.jpg",
    "Complex-Vowel-ô.jpg",
    "Complex-Vowel-oo.jpg",
    "Consonant-le-Syllables.jpg",
    "Digraph-ch.jpg",
    "Digraph-ng.jpg",
    "Digraph-ph.jpg",
    "Digraph-th.jpg",
    "Digraph-sh.jpg",
    "Digraph-wh.jpg",
    "Diphthong-OI.jpg",
    "Diphthong-OU.jpg",
    "L-Blends.jpg",
    "Letter-A_Medial.jpg",
    "Letter-E-Medial.jpg",
    "Letter-I-Medial.jpg",
    "Letter-O_Medial.jpg",
    "Letter-U_Medial.jpg",
    "Long-A.jpg",
    "Long-E.jpg",
    "Long-I.jpg",
    "Long-O.jpg",
    "Long-U.jpg",
    "Open-Syllables.jpg",
    "R-Blends.jpg",
    "R-Controlled-Syllables.jpg",
    "r-controlled-vowel-ar.jpg",
    "r-controlled-vowel-or.jpg",
    "r-controlled-vowel-ur.jpg",
    "S-Blends.jpg",
    "Silent-Letters.jpg",
    "Soft-C.jpg",
    "Soft-G.jpg",
    "Three-Letter-Blends.jpg",
    "Vowel-Consonant-e-Syllables.jpg",
    "Vowel-Team-Syllables.jpg",
]

# === Reference mappings ===
explicit_digraph_map = {
    "ch": "Digraph-ch.jpg",
    "sh": "Digraph-sh.jpg",
    "ph": "Digraph-ph.jpg",
    "th": "Digraph-th.jpg",
    "wh": "Digraph-wh.jpg",
    "ng": "Digraph-ng.jpg",
}

keyword_to_fragment = {
    **explicit_digraph_map,
    "tch": "Soft-C.jpg",  # fallback if needed
    "l-blends": "L-Blends.jpg",
    "r-blends": "R-Blends.jpg",
    "s-blends": "S-Blends.jpg",
    "3-letter blends": "Three-Letter-Blends.jpg",
    "three-letter blends": "Three-Letter-Blends.jpg",
    "closed syllables": "Closed-Syllables.jpg",
    "open syllables": "Open-Syllables.jpg",
    "long a": "Long-A.jpg",
    "long e": "Long-E.jpg",
    "long i": "Long-I.jpg",
    "long o": "Long-O.jpg",
    "long u": "Long-U.jpg",
    # r-controlled (explicit targets)
    "r-controlled syllables": "R-Controlled-Syllables.jpg",
    "r-controlled vowel ar": "r-controlled-vowel-ar.jpg",
    "r-controlled vowel or": "r-controlled-vowel-or.jpg",
    "r-controlled vowel ur": "r-controlled-vowel-ur.jpg",
    # diphthongs
    "diphthong oi": "Diphthong-OI.jpg",
    "diphthong ou": "Diphthong-OU.jpg",
    # NEW: vowel-consonant-e / magic-e
    "vowel-consonant-e syllables": "Vowel-Consonant-e-Syllables.jpg",
    "vowel consonant e syllables": "Vowel-Consonant-e-Syllables.jpg",
    "vowel-consonant-e": "Vowel-Consonant-e-Syllables.jpg",
    "vce syllables": "Vowel-Consonant-e-Syllables.jpg",
    "magic e syllables": "Vowel-Consonant-e-Syllables.jpg",
    "silent e syllables": "Vowel-Consonant-e-Syllables.jpg",
    # NEW: consonant-le (c-le)
    "consonant-le syllables": "Consonant-le-Syllables.jpg",
    "consonant le syllables": "Consonant-le-Syllables.jpg",
    "c-le syllables": "Consonant-le-Syllables.jpg",
    "cle syllables": "Consonant-le-Syllables.jpg",
}

# Vowels handled as a group
vowel_terms = {
    "a": "Letter-A_Medial.jpg",
    "e": "Letter-E-Medial.jpg",
    "i": "Letter-I_Medial.jpg",
    "o": "Letter-O_Medial.jpg",
    "u": "Letter-U_Medial.jpg",
}

restricted_keywords = set(explicit_digraph_map.keys())


# === Normalization helpers (handles /âr/, /ôr/, /ûr/, dashes, spacing, etc.) ===
def strip_diacritics(s: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn"
    )


def normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = strip_diacritics(s)

    # unify dashes to ASCII hyphen
    s = s.replace("–", "-").replace("—", "-")

    # normalize common hyphen/space variants
    s = re.sub(r"\b(r)\s*[- ]\s*(controlled)\b", r"\1-controlled", s)
    s = re.sub(r"\bvowel\s*[- ]\s*consonant\s*[- ]\s*e\b", "vowel-consonant-e", s)
    s = re.sub(r"\bconsonant\s*[- ]\s*le\b", "consonant-le", s)

    # remove slashes around phoneme tokens: "/ar/" -> "ar"
    s = re.sub(r"/\s*([a-z]+)\s*/", r"\1", s)

    # collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


# === Matching functions ===
def contextually_allowed_improved(text_norm: str, keyword: str) -> bool:
    if keyword not in restricted_keywords:
        return True
    # handle plural grouped case: "digraphs ch, th, ph"
    if "digraphs" in text_norm:
        match = re.search(r"digraphs ([a-z,\sand]+)", text_norm)
        if match:
            digraph_list = re.split(r"[,\sand]+", match.group(1))
            digraph_list = [d.strip() for d in digraph_list if d.strip()]
            return keyword in digraph_list
    return (f"digraph {keyword}" in text_norm) or (
        f"the digraph {keyword}" in text_norm
    )


def improved_match(keyword: str):
    if keyword in explicit_digraph_map:
        return [explicit_digraph_map[keyword]]
    elif keyword in keyword_to_fragment:
        target = keyword_to_fragment[keyword].lower()
        candidates = [f for f in image_filenames if target in f.lower()]
        return candidates
    else:
        # fuzzy fallback
        cleaned = re.sub(r"[^a-z0-9]", "", keyword.lower())
        normalized_index = {
            re.sub(r"[^a-z0-9]", "", f.lower()): f for f in image_filenames
        }
        matches = get_close_matches(cleaned, normalized_index.keys(), n=1, cutoff=0.6)
        return [normalized_index[m] for m in matches] if matches else []


# === Main loop ===
for lesson in lessons:
    raw = lesson.get("notes") or ""
    text_norm = normalize_text(raw)

    matched_images = set()

    if (
        ("short medial vowels" in text_norm)
        or ("short vowels" in text_norm)
        or ("medial vowels" in text_norm)
    ):
        for v in ["a", "e", "i", "o", "u"]:
            matched_images.add(vowel_terms[v])
    else:
        for keyword in keyword_to_fragment:
            if keyword in text_norm and contextually_allowed_improved(
                text_norm, keyword
            ):
                matched_images.update(improved_match(keyword))

    lesson["images"] = sorted(matched_images)

# === Save output ===
with open("sound_spelling_cards.json", "w") as f:
    json.dump(lessons, f, indent=2)

print("✅ Done. Output saved as sound_spelling_cards.json")
