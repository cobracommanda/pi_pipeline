#!/usr/bin/env python3
import builtins  # (unused, but keeping since you had it)
from pathlib import Path
import json

# === CONFIG ===
input_path = Path("units.py")
py_output_path = Path("level_3.py")
json_output_path = Path("level_3.json")
target_var = "lesson_blocks_with_html"


def inject_tags(obj):
    """Recursively inject tag for every audio block with 'filename' and no 'tag'."""
    if isinstance(obj, dict):
        if "filename" in obj and "tag" not in obj:
            filename = obj["filename"]
            obj["tag"] = f'<audio src="../audio/{filename}.mp3"></audio>'
        for k in obj:
            obj[k] = inject_tags(obj[k])
    elif isinstance(obj, list):
        obj = [inject_tags(item) for item in obj]
    return obj


def to_python_literal(obj, indent=0):
    """Format Python object as valid .py literal."""
    pad = "  " * indent
    if isinstance(obj, dict):
        lines = ["{"]
        for k, v in obj.items():
            lines.append(f"{pad}  {repr(k)}: {to_python_literal(v, indent + 1)},")
        lines.append(pad + "}")
        return "\n".join(lines)
    elif isinstance(obj, list):
        lines = ["["]
        for item in obj:
            lines.append(f"{pad}  {to_python_literal(item, indent + 1)},")
        lines.append(pad + "]")
        return "\n".join(lines)
    else:
        return repr(obj)


# === EXECUTE INPUT PYTHON FILE ===
# Allow JSON-style literals inside units.py (null/true/false)
scope = {"null": None, "true": True, "false": False}
exec(input_path.read_text(encoding="utf-8"), scope)

if target_var not in scope:
    raise SystemExit(f"❌ Variable '{target_var}' not found in {input_path}")

data = scope[target_var]
modified = inject_tags(data)

# === WRITE PYTHON OUTPUT ===
wrapped_py = f"{target_var} = {to_python_literal(modified)}\n"
py_output_path.write_text(wrapped_py, encoding="utf-8")
print(f"✅ Tagged and saved Python: {py_output_path.resolve()}")

# === WRITE JSON OUTPUT ===
# Writes an object with the same top-level name for clarity.
# If you prefer a bare array, change `payload = {target_var: modified}` to `payload = modified`.
payload = {target_var: modified}
json_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ Tagged and saved JSON:   {json_output_path.resolve()}")