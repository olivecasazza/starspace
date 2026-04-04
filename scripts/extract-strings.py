#!/usr/bin/env python3
"""Extract Chinese strings from Star Office UI source files.

Scans HTML and JS files for Chinese text, generates a zh.json locale file
with auto-generated keys, and creates stub en.json / ja.json files.

Usage:
    python3 scripts/extract-strings.py

Output:
    frontend/locales/zh.json  -- Chinese source strings
    frontend/locales/en.json  -- Empty stubs (translate with translate-locales.py)
    frontend/locales/ja.json  -- Empty stubs
"""

import json
import os
import re
import hashlib
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"

# Files to scan
SCAN_FILES = [
    FRONTEND / "index.html",
    FRONTEND / "electron-standalone.html",
    FRONTEND / "game.js",
    FRONTEND / "layout.js",
    FRONTEND / "join.html",
    FRONTEND / "invite.html",
    BACKEND / "app.py",
    BACKEND / "memo_utils.py",
]

# Match runs of Chinese characters with interspersed punctuation, spaces, digits
# but NOT HTML tags, attributes, or code
CHINESE_RE = re.compile(
    r'[\u4e00-\u9fff]'                          # starts with Chinese char
    r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef' # Chinese + CJK punctuation
    r'\w\s\d.,!?;:\-\'\"()/\\%\u2026\u2014\u2018\u2019\u201c\u201d]*'
)

# Patterns to extract text from HTML
HTML_TEXT_RE = re.compile(r'>([^<]+)<')  # text between tags
HTML_ATTR_RE = re.compile(r'(?:title|placeholder|alt|aria-label|data-tooltip)\s*=\s*["\']([^"\']+)["\']')

# JS string patterns
JS_STRING_RE = re.compile(r'''(?:['"`])([^'"`\n]+)(?:['"`])''')


def make_key(text: str, filepath: str, idx: int) -> str:
    """Generate a stable key from the text and source file."""
    prefix = Path(filepath).stem.replace("-", "_").replace(".", "_")
    h = hashlib.md5(text.encode()).hexdigest()[:8]
    return f"{prefix}.{h}"


def has_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def clean_text(text: str) -> str:
    """Clean extracted text."""
    text = text.strip()
    # Remove leading/trailing punctuation that isn't Chinese
    text = re.sub(r'^[\s\-:;,./\\|]+', '', text)
    text = re.sub(r'[\s\-:;,./\\|]+$', '', text)
    return text.strip()


def extract_chinese_phrases(text: str) -> list:
    """Extract clean Chinese phrases from a text block."""
    results = []
    for m in CHINESE_RE.finditer(text):
        phrase = clean_text(m.group())
        if len(phrase) >= 2 and has_chinese(phrase):
            results.append(phrase)
    return results


def extract_from_html(filepath: Path) -> OrderedDict:
    """Extract Chinese strings from HTML file."""
    strings = OrderedDict()
    content = filepath.read_text(encoding="utf-8")

    # Extract text content between HTML tags
    for m in HTML_TEXT_RE.finditer(content):
        text = m.group(1)
        for phrase in extract_chinese_phrases(text):
            key = make_key(phrase, str(filepath), len(strings))
            strings[key] = phrase

    # Extract from HTML attributes
    for m in HTML_ATTR_RE.finditer(content):
        text = m.group(1)
        for phrase in extract_chinese_phrases(text):
            key = make_key(phrase, str(filepath), len(strings))
            strings[key] = phrase

    return strings


def extract_from_js(filepath: Path) -> OrderedDict:
    """Extract Chinese strings from JS file."""
    strings = OrderedDict()
    content = filepath.read_text(encoding="utf-8")

    # Get strings from JS string literals
    for m in JS_STRING_RE.finditer(content):
        text = m.group(1)
        for phrase in extract_chinese_phrases(text):
            key = make_key(phrase, str(filepath), len(strings))
            strings[key] = phrase

    # Also check comments and template literals for Chinese
    for line in content.split('\n'):
        for phrase in extract_chinese_phrases(line):
            key = make_key(phrase, str(filepath), len(strings))
            if key not in strings:
                strings[key] = phrase

    return strings


def extract_from_python(filepath: Path) -> OrderedDict:
    """Extract Chinese strings from Python file."""
    strings = OrderedDict()
    content = filepath.read_text(encoding="utf-8")

    for m in JS_STRING_RE.finditer(content):
        text = m.group(1)
        for phrase in extract_chinese_phrases(text):
            key = make_key(phrase, str(filepath), len(strings))
            strings[key] = phrase

    return strings


def main():
    all_strings = OrderedDict()

    for filepath in SCAN_FILES:
        if not filepath.exists():
            print(f"  Skip (not found): {filepath}")
            continue

        rel = filepath.relative_to(ROOT)
        suffix = filepath.suffix

        if suffix == '.html':
            file_strings = extract_from_html(filepath)
        elif suffix == '.js':
            file_strings = extract_from_js(filepath)
        elif suffix == '.py':
            file_strings = extract_from_python(filepath)
        else:
            continue

        # Deduplicate within file
        for k, v in file_strings.items():
            if v not in all_strings.values():
                all_strings[k] = v

        print(f"  {rel}: {len(file_strings)} raw, {len([v for v in file_strings.values() if v not in list(all_strings.values())[:len(all_strings)-len(file_strings)]])} new")

    print(f"\nTotal unique strings: {len(all_strings)}")

    # Write zh.json
    locales_dir = FRONTEND / "locales"
    locales_dir.mkdir(exist_ok=True)

    zh_path = locales_dir / "zh.json"
    zh_path.write_text(
        json.dumps(all_strings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {zh_path.relative_to(ROOT)}")

    # Write en.json and ja.json stubs
    for lang in ("en", "ja"):
        lang_path = locales_dir / f"{lang}.json"
        stubs = OrderedDict((k, "") for k in all_strings)
        lang_path.write_text(
            json.dumps(stubs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Wrote {lang_path.relative_to(ROOT)} ({len(stubs)} keys)")


if __name__ == "__main__":
    main()
