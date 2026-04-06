/**
 * auto-translate.js
 * ==================
 * Tự động tìm tất cả các chuỗi tiếng Trung còn sót lại chưa có trong DB,
 * sử dụng google-translate-api để dịch hàng loạt sang tiếng Việt, và lưu vào DB.
 */
const fs = require('fs');
const path = require('path');
const { translate } = require('bing-translate-api');

const DB_FILE    = path.resolve(__dirname, 'translation_db.json');
const SRC_DIRS   = ['frontend/src', 'server', 'lib', 'scripts'];
const EXTENSIONS = ['.ts', '.tsx', '.py', '.html', '.css', '.md'];
const SKIP_DIRS  = new Set(['node_modules', '.git', '__pycache__', 'dist', 'build', '.venv', 'venv']);

// --- Utilities ---
function loadDB() {
  if (!fs.existsSync(DB_FILE)) return { phrases: {} };
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
      if (stat.isDirectory()) walk(full);
      else if (EXTENSIONS.some(ext => e.endsWith(ext))) results.push(full);
    }
  }
  for (const d of dirs) {
    const abs = path.resolve(__dirname, d);
    if (fs.existsSync(abs)) walk(abs);
  }
  return results;
}

function extractChineseFromFile(filepath) {
  const content = fs.readFileSync(filepath, 'utf8');
  const lines   = content.split('\n');
  const found   = [];
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (!isChinese(ln)) continue;
    const matches = ln.match(/[\u4e00-\u9fa5][^\n"'`<>{}]{0,80}/g) || [];
    for (const m of matches) {
      const phrase = m.trim().replace(/^[^\u4e00-\u9fa5]+/, '').trim();
      if (phrase && isChinese(phrase)) found.push(phrase);
    }
  }
  return found;
}

// --- Main ---
async function main() {
  const db = loadDB();
  db.phrases = db.phrases || {};
  const files = collectFiles(SRC_DIRS);
  
  console.log(`🔍 Đang quét ${files.length} files để tìm các chuỗi còn thiếu...`);
  const missingSet = new Set();
  
  for (const f of files) {
    const hits = extractChineseFromFile(f);
    for (const phrase of hits) {
      // Check if already covered
      const inDB = Object.keys(db.phrases).some(k => phrase.includes(k) || k.includes(phrase));
      if (!inDB) missingSet.add(phrase);
    }
  }
  
  const missingArray = Array.from(missingSet);
  console.log(`⚠️ Tìm thấy ${missingArray.length} chuỗi chưa được dịch.`);
  
  if (missingArray.length === 0) {
    console.log("🎉 Không còn gì để dịch. Hoàn thành!");
    return;
  }
  
  console.log(`🤖 Bắt đầu tự động dịch BING (Chia thành các batch)...`);
  
  const BATCH_SIZE = 10; // Giảm batch size để an toàn hơn
  let translatedCount = 0;
  
  for (let i = 0; i < missingArray.length; i += BATCH_SIZE) {
    const batch = missingArray.slice(i, i + BATCH_SIZE);
    
    // Kiểm tra lại xem những chuỗi này đã được dịch chưa (phòng trường hợp DB đã cập nhật bên ngoài)
    const currentDB = loadDB();
    const subBatch = batch.filter(p => !currentDB.phrases[p]);
    
    if (subBatch.length === 0) {
      console.log(`⏩ Bỏ qua batch ${Math.floor(i/BATCH_SIZE) + 1} (Đã được dịch).`);
      continue;
    }

    const textsToTranslate = subBatch.join('\n|||\n');
    console.log(`⏳ Đang dịch batch ${Math.floor(i/BATCH_SIZE) + 1}/${Math.ceil(missingArray.length/BATCH_SIZE)} (${subBatch.length} chuỗi mới)...`);
    
    try {
      const res = await translate(textsToTranslate, 'zh-Hans', 'vi');
      const translatedTexts = res.translation.split(/\|\|\||\/\/\|\||\/\|/).map(s => s.trim());
      
      // Reload DB lần nữa ngay trước khi update để merge
      const dbToUpdate = loadDB();
      dbToUpdate.phrases = dbToUpdate.phrases || {};

      if (translatedTexts.length !== subBatch.length) {
        console.warn(`   ⚠️ Cảnh báo: Batch lệch. Đang dịch từng câu...`);
        for (const str of subBatch) {
          try {
            const singleRes = await translate(str, 'zh-Hans', 'vi');
            dbToUpdate.phrases[str] = { vi: singleRes.translation.trim(), context: "auto-bing" };
            translatedCount++;
          } catch(err) {
            console.error(`   ❌ Lỗi: "${str}" -`, err.message);
          }
          await new Promise(r => setTimeout(r, 500));
        }
      } else {
        for (let j = 0; j < subBatch.length; j++) {
          const original = subBatch[j];
          let viText = translatedTexts[j].replace(/^\\/, '');
          dbToUpdate.phrases[original] = { vi: viText, context: "auto-bing" };
          translatedCount++;
        }
      }
      
      saveDB(dbToUpdate);
      console.log(`   ✅ Đã lưu ${subBatch.length} chuỗi.`);
      await new Promise(r => setTimeout(r, 3000)); // Nghỉ 3s giữa các batch cho an toàn
      
    } catch (err) {
      console.error(`❌ Lỗi batch dịch BING: ${err.message}.`);
      console.log(`   Đang thử dịch dự phòng từng câu cho batch này...`);
      const dbFallback = loadDB();
      for (const str of subBatch) {
          try {
            const singleRes = await translate(str, 'zh-Hans', 'vi');
            dbFallback.phrases[str] = { vi: singleRes.translation.trim(), context: "auto-bing" };
            translatedCount++;
          } catch(e) { }
          await new Promise(r => setTimeout(r, 1000));
      }
      saveDB(dbFallback);
    }
  }
  
  console.log(`\n✅ Đã dịch và lưu tự động ${translatedCount}/${missingArray.length} đoạn văn bản.`);
  console.log(`🎯 Chạy 'node translate-tool.js apply' ngay sau đây để áp dụng vào code gốc!`);
}

main().catch(console.error);
