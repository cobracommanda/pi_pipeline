#!/usr/bin/env node
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
const INCLUDE_ALL = Boolean(args.get("--all")); // if set: keep every cell (no style filter)

// ---------- Helpers ----------
function readJson(filePath) {
  const txt = fs.readFileSync(filePath, "utf8");
  return JSON.parse(txt);
}

function detectRootKey(obj) {
  const keys = Object.keys(obj || {});
  if (keys.length !== 1)
    throw new Error(`Expected exactly 1 root key, found ${keys.length}.`);
  return keys[0]; // often "Y49397_TG_L3_U3" in unit-level files, but can be "Frame_1" in per-lesson dumps
}

function unitSuffixFrom(rootKey, inputPath) {
  // Preferred: from rootKey like "Y49397_TG_L3_U3" -> "L3_U3"
  let m = /_TG_(L\d+_U\d+)/.exec(rootKey);
  if (m) return m[1];

  // Fallback: from filename like "Y49397_TG_L3_U3_L04.indd.json" -> "L3_U3"
  const base = path.basename(inputPath).replace(/\.json$/i, "");
  m = /_TG_(L\d+_U\d+)/.exec(base);
  if (m) return m[1];

  // Last resort: keep rootKey (avoids crashing, but filenames may be odd)
  return rootKey;
}

// Deep iterator over any JS value to yield every {type:"table"} node.
function* iterTablesDeep(node) {
  if (!node) return;
  if (Array.isArray(node)) {
    for (const item of node) yield* iterTablesDeep(item);
    return;
  }
  if (typeof node === "object") {
    if (node.type === "table" && node.rows) yield node;
    for (const v of Object.values(node)) yield* iterTablesDeep(v);
  }
}

// Iterate over cells in a table
function* iterCells(table) {
  if (!table?.rows) return;
  for (const row of table.rows) {
    if (!Array.isArray(row)) continue;
    for (const cell of row) {
      if (cell && cell.type === "cell") yield cell;
    }
  }
}

// Relaxed predicate for "lesson-ish" cells.
// Set --all to bypass and keep everything.
function isLessonContentCell(cell) {
  if (INCLUDE_ALL) return true;
  if (!Array.isArray(cell?.blocks)) return false;

  let headerHit = false;
  let bodyHit = false;

  for (const blk of cell.blocks) {
    const style = (blk?.style || "").trim();
    if (
      blk?.type === "header" &&
      (blk.level === 3 || blk.level === 2) &&
      /^lesson_C-hd\b/.test(style) // allow trailing spaces/variants
    ) {
      headerHit = true;
    }
    if (
      blk?.type === "para" &&
      /lesson_Body/i.test(style) // accept lesson_Body, lesson_Body-txt, etc.
    ) {
      bodyHit = true;
    }
  }
  return headerHit || bodyHit;
}

function collectCellsFromLesson(lessonObj) {
  const tables = [...iterTablesDeep(lessonObj)];
  const cells = [];
  for (const t of tables) {
    for (const c of iterCells(t)) {
      if (isLessonContentCell(c)) cells.push(c);
    }
  }
  return { tablesCount: tables.length, cells };
}

// Prefer real lesson keys present in the root object; else synthesize L01..L10
function lessonKeysPresent(rootObj) {
  return Object.keys(rootObj || {})
    .filter((k) => /_L\d{2}$/i.test(k))
    .sort();
}
function lessonKeysFor(rootKey) {
  const prefix = `${rootKey}_L`;
  return Array.from(
    { length: 10 },
    (_, i) => `${prefix}${String(i + 1).padStart(2, "0")}`
  );
}

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

// ---------- Core per-file processing ----------
function processOneJson(inputPath, outDir) {
  const abs = path.resolve(inputPath);
  const data = readJson(abs);
  const ROOT_KEY = detectRootKey(data); // may be Y49397_TG_L3_U3 or something else
  const UNIT_SUFFIX = unitSuffixFrom(ROOT_KEY, abs);
  const root = data[ROOT_KEY] || {};

  let keys = lessonKeysPresent(root);
  if (keys.length === 0) keys = lessonKeysFor(ROOT_KEY); // fallback

  const pageOutputs = { 1: {}, 2: {}, 3: {} };

  for (const key of keys) {
    const lesson = root[key] || {};
    // In some files, lessons don’t split by page sections; do a single deep scan
    // If you *know* lesson0/1/2 map to pages, keep the per-page shape but reuse deep scan.
    const { tablesCount, cells } = collectCellsFromLesson(lesson);

    // Minimal heuristic: if the lesson object has lesson0/1/2, attribute by those; else dump all to pg1
    const hasPageSections = ["lesson0", "lesson1", "lesson2"].some((k) =>
      Array.isArray(lesson[k])
    );
    if (hasPageSections) {
      const p1 = collectCellsFromLesson({ lesson0: lesson.lesson0 }).cells;
      const p2 = collectCellsFromLesson({ lesson1: lesson.lesson1 }).cells;
      const p3 = collectCellsFromLesson({ lesson2: lesson.lesson2 }).cells;
      pageOutputs[1][key] = p1;
      pageOutputs[2][key] = p2;
      pageOutputs[3][key] = p3;
      if (p1.length + p2.length + p3.length === 0 && tablesCount > 0) {
        console.warn(
          `[WARN] ${path.basename(
            abs
          )} ${key}: found ${tablesCount} table(s) but 0 cells after style filter within lesson0/1/2.`
        );
      }
    } else {
      // No explicit page sections → put everything on page 1
      pageOutputs[1][key] = cells;
      pageOutputs[2][key] = [];
      pageOutputs[3][key] = [];
      if (cells.length === 0) {
        console.warn(
          `[WARN] ${path.basename(
            abs
          )} ${key}: 0 cells (tables seen: ${tablesCount}).`
        );
      }
    }
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
      "Usage:\n  node a.js --dir <folder> [--out <folder>] [--all]\n  node a.js --input <file.json> [--out <folder>] [--all]"
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
