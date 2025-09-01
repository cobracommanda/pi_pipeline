import json
from pathlib import Path


def escape_html(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def run_to_span(run):
    classes = []
    if run.get("bold"):
        classes.append("bold")
    if run.get("italic"):
        classes.append("italic")
    if run.get("underline"):
        classes.append("underline")
    span_open = f'<span class="{" ".join(classes)}">' if classes else ""
    span_close = "</span>" if classes else ""
    return span_open + escape_html(run["text"]) + span_close


def style_to_block_classes(style_name):
    classes = []
    if style_name and "teacher" in style_name.lower():
        classes.append("teacher_talk")
    return classes


def block_to_html(block):
    content = "".join([run_to_span(run) for run in block.get("runs", [])])
    block_classes = style_to_block_classes(block.get("style", ""))
    class_attr = f' class="{" ".join(block_classes)}"' if block_classes else ""
    if block["type"] == "header":
        tag = f"h{block.get('level', 3)}"
        return f"<{tag}{class_attr}>{content}</{tag}>"
    elif block["type"] == "para":
        return f"<p{class_attr}>{content}</p>"
    elif block["type"] == "table":
        html = "<table>"
        for row in block.get("rows", []):
            html += "<tr>"
            for cell in row:
                cell_content = "".join(block_to_html(b) for b in cell.get("blocks", []))
                html += f"<td>{cell_content}</td>"
            html += "</tr>"
        html += "</table>"
        return html
    return ""


def indd_block_to_html(blocks):
    if isinstance(blocks, list):
        return "".join(block_to_html(block) for block in blocks)
    elif isinstance(blocks, dict):
        return block_to_html(blocks)
    return ""


def process_json_for_python(input_path, output_py_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(output_py_path, "w", encoding="utf-8") as f:
        f.write("lesson_blocks_with_html = [\n")
        for obj in data:
            f.write("  {\n")
            for k, v in obj.items():
                if k.startswith("page") and isinstance(v, list):
                    html_list = [indd_block_to_html(cell["blocks"]) for cell in v]
                    f.write(f'    "html_{k}": [\n')
                    for html in html_list:
                        f.write(f'      """{html}""",\n')
                    f.write("    ],\n")
                else:
                    f.write(f"    {json.dumps(k)}: {json.dumps(v)},\n")
            f.write("  },\n")
        f.write("]\n")


if __name__ == "__main__":
    # process_json_for_python("data.json", "777.py")
    # process_json_for_python("lvl_3_4_metadata.json", "lvl_3_4_metadata.py")
    process_json_for_python(
        "units.json", "units.py"
    )
