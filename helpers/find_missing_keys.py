from pathlib import Path
import json, re
from typing import Dict, List, Callable, Any, Optional


def find_empty_keys_in_dir(
    dir_path: str,
    pattern: str = "*.json",
    recursive: bool = False,
    key_regex: Optional[str] = None,
    exclude_key_regex: Optional[str] = None,
    is_empty: Optional[Callable[[Any], bool]] = None,
) -> Dict[str, List[str]]:
    """
    Return: { "<file path>": ["<empty_key1>", ...], ... }
    - key_regex: include only keys matching this regex.
    - exclude_key_regex: drop keys matching this regex (e.g., r"_L10$").
    - is_empty: predicate; default is exactly [].
    """
    if is_empty is None:
        is_empty = lambda v: isinstance(v, list) and len(v) == 0

    paths = Path(dir_path).rglob(pattern) if recursive else Path(dir_path).glob(pattern)
    rx_inc = re.compile(key_regex) if key_regex else None
    rx_exc = re.compile(exclude_key_regex) if exclude_key_regex else None

    results: Dict[str, List[str]] = {}
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        empties: List[str] = []
        for k, v in data.items():
            if rx_inc and not rx_inc.search(k):
                continue
            if rx_exc and rx_exc.search(k):
                continue
            if is_empty(v):
                empties.append(k)

        if empties:
            results[str(p)] = empties
    return results


def print_empty_keys_report(results: Dict[str, List[str]]) -> None:
    for file_path in sorted(results):
        keys = results[file_path]
        print(f"{Path(file_path).name}: {len(keys)} empty -> {', '.join(keys)}")


# 1) Basic: find keys with [] values in all *.json files (non-recursive)
res = find_empty_keys_in_dir("level_3_units")
print_empty_keys_report(res)

# 2) Restrict to lesson-like keys only (e.g., ..._L01, ..._L02, ...)
res = find_empty_keys_in_dir("level_3_units", exclude_key_regex=r"_L10$")
print_empty_keys_report(res)

# 3) Recurse through subfolders
res = find_empty_keys_in_dir("level_3_units", recursive=True)
print_empty_keys_report(res)

# 4) If you later decide that other “empties” count too (e.g., "", {}, None),
#    pass a custom predicate:
# only L01..L09 keys
res = find_empty_keys_in_dir(
    "level_3_units", key_regex=r"_L0[1-9]$"  # includes _L01 .. _L09, excludes _L10
)
print_empty_keys_report(res)
