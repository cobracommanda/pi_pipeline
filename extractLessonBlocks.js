import fs from "fs";
import path from "path";

// ---------- CLI ----------
const args = new Map(
  process.argv
    .slice(2)
    .map((v, i, arr) => (v.startsWith("--") ? [v, arr[i + 1] || true] : null))
    .filter(Boolean)
);
const INPUT_DIR = args.get("--dir") || null; // e.g., data/json
const INPUT_FILE = args.get("--input") || null; // e.g., data/json/Y49397_TG_L3_U3.json
const OUT_DIR = args.get("--out") || "."; // default: current dir

// ---------- Helpers ----------
function readJson(filePath) {
  const txt = fs.readFileSync(filePath, "utf8");
  return JSON.parse(txt);
}

function detectRootKey(obj) {
  const keys = Object.keys(obj || {});
  if (keys.length !== 1)
    throw new Error(`Expected exactly 1 root key, found ${keys.length}.`);
  return keys[0]; // e.g., "Y49397_TG_L3_U3"
}

function unitSuffixFromRootKey(rootKey) {
  // from "Y49397_TG_L3_U3" -> "L3_U3"
  const m = rootKey.match(/_TG_(.+)$/);
  return m ? m[1] : rootKey;
}

function getTablesFromSection(lessonObj, sectionKey) {
  if (!lessonObj || typeof lessonObj !== "object") return [];
  const arr = Array.isArray(lessonObj[sectionKey]) ? lessonObj[sectionKey] : [];
  return arr.filter((b) => b && b.type === "table");
}

function* iterCells(table) {
  if (!table?.rows) return;
  for (const row of table.rows) {
    if (!Array.isArray(row)) continue;
    for (const cell of row) {
      if (cell && cell.type === "cell") yield cell;
    }
  }
}

// Keep cells that look like lesson content (header/body styles you showed).
// If you truly want EVERY cell, just return true here.
function isLessonContentCell(cell) {
  if (!Array.isArray(cell?.blocks)) return false;
  let hasHeader = false;
  let hasBody = false;
  for (const blk of cell.blocks) {
    if (blk.type === "header" && blk.level === 3 && blk.style === "lesson_C-hd")
      hasHeader = true;
    if (blk.type === "para" && blk.style === "lesson_Body-txt") hasBody = true;
  }
  return hasHeader || hasBody;
}

function collectCells(tables) {
  const out = [];
  for (const table of tables) {
    for (const cell of iterCells(table)) {
      if (isLessonContentCell(cell)) out.push(cell); // FULL cell object
    }
  }
  return out;
}

function lessonKeysFor(rootKey) {
  // lessons always L01..L10 under the same prefix as root
  const LESSON_PREFIX = `${rootKey}_L`;
  return Array.from(
    { length: 10 },
    (_, i) => `${LESSON_PREFIX}${String(i + 1).padStart(2, "0")}`
  );
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

// ---------- Core per-file processing ----------
function processOneJson(inputPath, outDir) {
  const abs = path.resolve(inputPath);
  const data = readJson(abs);
  const ROOT_KEY = detectRootKey(data); // e.g., Y49397_TG_L3_U3
  const UNIT_SUFFIX = unitSuffixFromRootKey(ROOT_KEY); // e.g., L3_U3
  const root = data[ROOT_KEY] || {};
  const keys = lessonKeysFor(ROOT_KEY);

  const pageOutputs = { 1: {}, 2: {}, 3: {} };

  for (const key of keys) {
    const lesson = root[key] || {};
    const pg1Tables = getTablesFromSection(lesson, "lesson0");
    const pg2Tables = getTablesFromSection(lesson, "lesson1");
    const pg3Tables = getTablesFromSection(lesson, "lesson2");

    pageOutputs[1][key] = collectCells(pg1Tables);
    pageOutputs[2][key] = collectCells(pg2Tables);
    pageOutputs[3][key] = collectCells(pg3Tables);
  }

  ensureDir(outDir);
  const outPg1 = path.join(outDir, `${UNIT_SUFFIX}_pg1.json`);
  const outPg2 = path.join(outDir, `${UNIT_SUFFIX}_pg2.json`);
  const outPg3 = path.join(outDir, `${UNIT_SUFFIX}_pg3.json`);
  fs.writeFileSync(outPg1, JSON.stringify(pageOutputs[1], null, 2), "utf8");
  fs.writeFileSync(outPg2, JSON.stringify(pageOutputs[2], null, 2), "utf8");
  fs.writeFileSync(outPg3, JSON.stringify(pageOutputs[3], null, 2), "utf8");
  console.log(`Wrote ${outPg1}, ${outPg2}, ${outPg3}`);
}

// ---------- Batch runner ----------
function main() {
  if (!INPUT_DIR && !INPUT_FILE) {
    console.error(
      "Usage:\n  node a.js --dir <folder> [--out <folder>]\n  node a.js --input <file.json> [--out <folder>]"
    );
    process.exit(1);
  }

  if (INPUT_FILE) {
    processOneJson(INPUT_FILE, OUT_DIR);
    return;
  }

  const dir = path.resolve(INPUT_DIR);
  const files = fs
    .readdirSync(dir)
    .filter((f) => f.toLowerCase().endsWith(".json"));
  if (files.length === 0) {
    console.warn(`No .json files found in ${dir}`);
    return;
  }

  for (const f of files) {
    try {
      processOneJson(path.join(dir, f), OUT_DIR);
    } catch (err) {
      console.error(`Failed ${f}: ${err.message}`);
    }
  }
}

main();
