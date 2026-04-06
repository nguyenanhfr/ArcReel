import os
import re
import json

def is_chinese_char(c):
    return '\u4e00' <= c <= '\u9fa5'

def extract_strings():
    extensions = {'.ts', '.tsx', '.py', '.html', '.css'}
    result = {} # original line containing chinese -> same line (placeholder)
    
    for root, dirs, files in os.walk('.'):
        for f in files:
            if any(f.endswith(ext) for ext in extensions):
                path = os.path.join(root, f)
                try:
                    with open(path, 'r', encoding='utf-8') as file:
                        lines = file.readlines()
                        for i, line in enumerate(lines):
                            if any(is_chinese_char(c) for c in line):
                                # keep original line as key and value
                                result[line] = line
                except Exception as e:
                    pass
    
    with open('to_translate.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    extract_strings()
    print("Done")
