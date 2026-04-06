#!/usr/bin/env node
/**
 * translate-tool.js
 * ==================
 * Công cụ dịch thuật Trung → Việt cho dự án ArcReel.
 *
 * Sử dụng:
 *   node translate-tool.js scan          → Tìm tất cả chuỗi tiếng Trung, báo cáo những gì CHƯA có trong DB
 *   node translate-tool.js apply         → Áp dụng bản dịch từ DB vào toàn bộ mã nguồn
 *   node translate-tool.js add "中文" "Tiếng Việt" "context tùy chọn"  → Thêm cặp dịch mới vào DB
 *   node translate-tool.js lookup "中文" → Tra cứu bản dịch trong DB
 *   node translate-tool.js report        → Thống kê: đã dịch / chưa dịch
 */

const fs   = require('fs');
const path = require('path');

// ────────────────────────────────────────────────
// Cấu hình
// ────────────────────────────────────────────────
const DB_FILE    = path.resolve(__dirname, 'translation_db.json');
const SRC_DIRS   = ['frontend/src', 'server', 'lib', 'scripts'];
const EXTENSIONS = ['.ts', '.tsx', '.py', '.html', '.css', '.md'];
const SKIP_DIRS  = new Set(['node_modules', '.git', '__pycache__', 'dist', 'build', '.venv', 'venv']);

// ────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────
function loadDB() {
  if (!fs.existsSync(DB_FILE)) {
    console.error(`❌ Không tìm thấy DB file: ${DB_FILE}`);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
}

function saveDB(db) {
  fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf8');
}

function isChinese(str) {
  return /[\u4e00-\u9fa5]/.test(str);
}

function collectFiles(dirs) {
  const results = [];
  function walk(dir) {
    let entries;
    try { entries = fs.readdirSync(dir); } catch { return; }
    for (const e of entries) {
      if (SKIP_DIRS.has(e)) continue;
      const full = path.join(dir, e);
      let stat;
      try { stat = fs.statSync(full); } catch { continue; }
      if (stat.isDirectory()) {
        walk(full);
      } else if (EXTENSIONS.some(ext => e.endsWith(ext))) {
        results.push(full);
      }
    }
  }
  for (const d of dirs) {
    const abs = path.resolve(__dirname, d);
    if (fs.existsSync(abs)) walk(abs);
  }
  return results;
}

/** Trích xuất tất cả chuỗi tiếng Trung xuất hiện trong file */
function extractChineseFromFile(filepath) {
  const content = fs.readFileSync(filepath, 'utf8');
  const lines   = content.split('\n');
  const found   = []; // { line, lineNo, phrase }

  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (!isChinese(ln)) continue;

    // Trích xuất các chuỗi trong nháy đơn, nháy kép, backtick hoặc giữa các thẻ HTML/JSX chứa tiếng Trung
    // Cách này giúp bắt trọn vẹn cụm từ lai như "Lưu中..."
    const phraseRegex = /(?:["'`])([^"'`]*?[\u4e00-\u9fa5]+[^"'`]*?)(?:["'`])|(?:>)([^<]*?[\u4e00-\u9fa5]+[^<]*?)(?:<)|(?:})([^<{}]*?[\u4e00-\u9fa5]+[^<{}]*?)(?:{)/g;
    let match;
    let foundInLine = false;
    
    while ((match = phraseRegex.exec(ln)) !== null) {
      let phrase = match[1] || match[2] || match[3];
      if (phrase) {
        phrase = phrase.trim();
        if (phrase && isChinese(phrase)) {
          found.push({ line: ln.trim(), lineNo: i + 1, phrase });
          foundInLine = true;
        }
      }
    }
    
    // Fallback if regex didn't catch it but line has Chinese (e.g. comments or plain strings without brackets)
    if (!foundInLine) {
        const matches = ln.match(/[\u4e00-\u9fa5][A-Za-z0-9_\s\.\u4e00-\u9fa5]{0,80}/g) || [];
        for (const m of matches) {
          const phrase = m.trim();
          if (phrase && isChinese(phrase)) {
            found.push({ line: ln.trim(), lineNo: i + 1, phrase });
          }
        }
    }
  }
  return found;
}

// ────────────────────────────────────────────────
// Lệnh: scan
// ────────────────────────────────────────────────
function cmdScan() {
  const db     = loadDB();
  const phrases = db.phrases || {};
  const files  = collectFiles(SRC_DIRS);

  const missing  = new Map(); // phrase → [file:line, ...]
  const covered  = new Set();

  for (const f of files) {
    const hits = extractChineseFromFile(f);
    for (const h of hits) {
      // Chỉ khi TRONG DB CÓ CHÍNH XÁC KEY NÀY thì mới tính là covered! Không chơi trò "includes" nữa.
      if (!phrases[h.phrase]) {
        const key = h.phrase;
        if (!missing.has(key)) missing.set(key, []);
        missing.get(key).push(`${path.relative(__dirname, f)}:${h.lineNo}`);
      } else {
        covered.add(h.phrase);
      }
    }
  }

  console.log(`\n📊 Kết quả scan:`);
  console.log(`   ✅ Đã có trong DB : ~${covered.size} cụm phrase`);
  console.log(`   ❌ CHƯA có trong DB: ${missing.size} phrase\n`);

  if (missing.size > 0) {
    console.log('❌ Các phrase CHƯA được dịch (cần thêm vào DB):');
    let idx = 1;
    for (const [phrase, locs] of [...missing].slice(0, 80)) {
      console.log(`  ${idx++}. "${phrase}"`);
      for (const loc of locs.slice(0, 3)) console.log(`        → ${loc}`);
    }
    if (missing.size > 80) console.log(`  ... và ${missing.size - 80} phrase khác`);
  } else {
    console.log('🎉 Tất cả phrase tiếng Trung đã có trong DB!');
  }
}

// ────────────────────────────────────────────────
// Lệnh: apply
// ────────────────────────────────────────────────
function cmdApply() {
  const db      = loadDB();
  const phrases = db.phrases || {};
  const files   = collectFiles(SRC_DIRS);

  // Sắp xếp key dài trước (tránh replace ngắn làm hỏng dài)
  const sortedKeys = Object.keys(phrases).sort((a, b) => b.length - a.length);

  let totalFiles = 0;
  let totalReplacements = 0;

  for (const filepath of files) {
    let content = fs.readFileSync(filepath, 'utf8');
    if (!isChinese(content)) continue;

    let changed = false;
    let fileReps = 0;

    for (const zh of sortedKeys) {
      const vi = phrases[zh]?.vi;
      if (!vi || zh === vi) continue;
      if (!content.includes(zh)) continue;

      // Thay thế toàn bộ, không dùng regex để an toàn cú pháp
      const before = content;
      content = content.split(zh).join(vi);
      if (content !== before) {
        const count = (before.split(zh).length - 1);
        fileReps += count;
        changed = true;
      }
    }

    if (changed) {
      fs.writeFileSync(filepath, content, 'utf8');
      totalFiles++;
      totalReplacements += fileReps;
      console.log(`  ✅ ${path.relative(__dirname, filepath)} — ${fileReps} thay thế`);
    }
  }

  console.log(`\n🎯 Hoàn tất: ${totalFiles} file | ${totalReplacements} thay thế`);
}

// ────────────────────────────────────────────────
// Lệnh: add
// ────────────────────────────────────────────────
function cmdAdd(zh, vi, context) {
  if (!zh || !vi) {
    console.error('❌ Cú pháp: node translate-tool.js add "中文" "Tiếng Việt" ["context"]');
    process.exit(1);
  }
  const db = loadDB();
  if (!db.phrases) db.phrases = {};

  if (db.phrases[zh]) {
    console.log(`⚠️  "${zh}" đã tồn tại trong DB.`);
    console.log(`   Bản dịch cũ: "${db.phrases[zh].vi}"`);
    console.log(`   Bản dịch mới: "${vi}"`);
    db.phrases[zh].vi = vi;
    if (context) db.phrases[zh].context = context;
    saveDB(db);
    console.log('   ✅ Đã cập nhật.');
  } else {
    db.phrases[zh] = { vi, context: context || '' };
    saveDB(db);
    console.log(`✅ Đã thêm: "${zh}" → "${vi}"`);
  }
}

// ────────────────────────────────────────────────
// Lệnh: lookup
// ────────────────────────────────────────────────
function cmdLookup(query) {
  if (!query) {
    console.error('❌ Cú pháp: node translate-tool.js lookup "中文"');
    process.exit(1);
  }
  const db      = loadDB();
  const phrases = db.phrases || {};

  // Tìm chính xác
  if (phrases[query]) {
    const entry = phrases[query];
    console.log(`\n🔍 Kết quả cho: "${query}"`);
    console.log(`   🇻🇳 Việt : ${entry.vi}`);
    console.log(`   📌 Context: ${entry.context || '(không có)'}`);
    return;
  }

  // Tìm gần đúng (chứa query)
  const partialMatches = Object.entries(phrases).filter(
    ([zh]) => zh.includes(query) || query.includes(zh)
  );

  if (partialMatches.length === 0) {
    console.log(`❌ Không tìm thấy "${query}" trong DB.`);
  } else {
    console.log(`\n🔍 Kết quả gần đúng cho: "${query}"`);
    for (const [zh, entry] of partialMatches.slice(0, 10)) {
      console.log(`  "${zh}" → "${entry.vi}"  [${entry.context || ''}]`);
    }
  }
}

// ────────────────────────────────────────────────
// Lệnh: report
// ────────────────────────────────────────────────
function cmdReport() {
  const db      = loadDB();
  const phrases = db.phrases || {};
  const files   = collectFiles(SRC_DIRS);

  let totalChinese = 0;
  let totalMissing = 0;
  const fileReport = [];

  for (const f of files) {
    const hits = extractChineseFromFile(f);
    if (hits.length === 0) continue;

    let missingInFile = 0;
    for (const h of hits) {
      const inDB = Object.keys(phrases).some(key => h.phrase.includes(key) || key.includes(h.phrase));
      if (!inDB) missingInFile++;
    }

    totalChinese += hits.length;
    totalMissing += missingInFile;

    fileReport.push({
      file: path.relative(__dirname, f),
      total: hits.length,
      missing: missingInFile,
      coverage: Math.round(((hits.length - missingInFile) / hits.length) * 100)
    });
  }

  console.log('\n📊 BÁO CÁO DỊCH THUẬT ArcReel');
  console.log('=' .repeat(60));
  console.log(`  Tổng phrases tiếng Trung tìm thấy : ${totalChinese}`);
  console.log(`  Đã có trong DB                    : ${totalChinese - totalMissing}`);
  console.log(`  Chưa có trong DB                  : ${totalMissing}`);
  console.log(`  Số entry trong DB                 : ${Object.keys(phrases).length}`);
  const overall = totalChinese > 0 ? Math.round(((totalChinese - totalMissing) / totalChinese) * 100) : 100;
  console.log(`  Độ phủ tổng thể                   : ${overall}%\n`);

  console.log('  File breakdown (file có tiếng Trung):');
  fileReport
    .sort((a, b) => a.coverage - b.coverage)
    .slice(0, 30)
    .forEach(r => {
      const bar = '█'.repeat(Math.round(r.coverage / 5)) + '░'.repeat(20 - Math.round(r.coverage / 5));
      console.log(`  [${bar}] ${r.coverage}%  ${r.file}  (${r.missing} chưa dịch)`);
    });
}

// ────────────────────────────────────────────────
// Điều phối lệnh
// ────────────────────────────────────────────────
const [,, cmd, ...args] = process.argv;

switch (cmd) {
  case 'scan'   : cmdScan(); break;
  case 'apply'  : cmdApply(); break;
  case 'add'    : cmdAdd(args[0], args[1], args[2]); break;
  case 'lookup' : cmdLookup(args[0]); break;
  case 'report' : cmdReport(); break;
  default:
    console.log(`
╔══════════════════════════════════════════════════════════════╗
║           ArcReel Translation Tool  (Zh → Vi)               ║
╠══════════════════════════════════════════════════════════════╣
║  node translate-tool.js scan                                 ║
║    → Tìm phrase tiếng Trung chưa có trong DB                 ║
║                                                              ║
║  node translate-tool.js apply                                ║
║    → Áp dụng DB vào toàn bộ mã nguồn                        ║
║                                                              ║
║  node translate-tool.js add "中文" "Tiếng Việt" "context"   ║
║    → Thêm/cập nhật cặp dịch trong DB                        ║
║                                                              ║
║  node translate-tool.js lookup "中文"                        ║
║    → Tra cứu bản dịch                                       ║
║                                                              ║
║  node translate-tool.js report                               ║
║    → Thống kê độ phủ dịch thuật theo file                   ║
╚══════════════════════════════════════════════════════════════╝
`);
}
