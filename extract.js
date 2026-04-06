const fs = require('fs');
const path = require('path');

function isChineseChar(c) {
    const code = c.charCodeAt(0);
    return code >= 0x4E00 && code <= 0x9FA5;
}

function extractStrings() {
    const extensions = ['.ts', '.tsx', '.py', '.html', '.css'];
    const result = {};
    
    function walk(dir) {
        let files = [];
        try {
            files = fs.readdirSync(dir);
        } catch(e) { return; }
        
        for (const file of files) {
            if (file === 'node_modules' || file === '.git') continue;
            
            const fullPath = path.join(dir, file);
            let stat;
            try {
                stat = fs.statSync(fullPath);
            } catch(e) { continue; }
            
            if (stat.isDirectory()) {
                walk(fullPath);
            } else if (extensions.some(ext => file.endsWith(ext))) {
                try {
                    const content = fs.readFileSync(fullPath, 'utf8');
                    const lines = content.split('\n');
                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i];
                        let hasChinese = false;
                        for (let j = 0; j < line.length; j++) {
                            if (isChineseChar(line[j])) {
                                hasChinese = true;
                                break;
                            }
                        }
                        if (hasChinese) {
                            result[line] = line;
                        }
                    }
                } catch(e) { }
            }
        }
    }
    
    walk('.');
    fs.writeFileSync('to_translate.json', JSON.stringify(result, null, 2), 'utf8');
    console.log('Done');
}

extractStrings();
