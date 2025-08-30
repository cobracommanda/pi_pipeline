import json
import shutil
from pathlib import Path

# Parent directory containing unit1 ... unit30
parent_dir = Path("/Users/DRobinson/Desktop/PI_MASTER_lv3/units")
# Final destination directory for preprocessed files
dest_dir = Path("/Users/DRobinson/Desktop/pi_pipeline/data/pre_processed")
dest_dir.mkdir(parents=True, exist_ok=True)


def combine_unit(unit_dir: Path):
    json_files = sorted([f for f in unit_dir.glob("*.json") if f.is_file()])
    if not json_files:
        print(f"⚠️  No JSON files in {unit_dir}")
        return None

    # Identify CV file
    cv_file = next((f for f in json_files if "_CV" in f.stem), None)
    if not cv_file:
        print(f"⚠️  No CV file found in {unit_dir}")
        return None

    # Extract base key
    base_key = cv_file.stem.replace("_CV", "").replace(".indd", "")
    combined = {base_key: {}}

    # Sorting function
    def sort_key(path):
        stem = path.stem.replace(".indd", "")
        if "_CV" in stem:
            return (0, 0)
        if "_L" in stem:
            try:
                return (1, int(stem.split("_L")[-1]))
            except ValueError:
                return (1, 999)
        return (2, 0)

    # Build combined JSON
    for file_path in sorted(json_files, key=sort_key):
        key_name = file_path.stem.replace(".indd", "")
        with open(file_path, "r", encoding="utf-8") as f:
            combined[base_key][key_name] = json.load(f)

    # Save combined JSON inside the unit folder
    output_path = unit_dir / f"{base_key}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    # Copy to pre_processed directory
    dest_path = dest_dir / output_path.name
    shutil.copy2(output_path, dest_path)

    print(f"✅ Combined JSON saved to: {output_path}")
    print(f"📂 Copied to: {dest_path}")
    return output_path


def main():
    for i in range(1, 31):  # unit1 ... unit30
        unit_dir = parent_dir / f"unit{i}"
        if unit_dir.is_dir():
            combine_unit(unit_dir)
        else:
            print(f"⚠️  Missing folder: {unit_dir}")


if __name__ == "__main__":
    main()
