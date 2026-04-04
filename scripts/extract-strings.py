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

# Regex to match Chinese character runs (with surrounding punctuation/mixed text)
CHINESE_RE = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef][\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\w\s\d.,!?;:\-\'"()/\\%#@&*+=<>{}[\]|~`\u2026\u2014\u2018\u2019\u201c\u201d]*')


def make_key(text: str, filepath: str) -> str:
    """Generate a stable key from the text and source file."""
    # Use first 40 chars of text + hash for uniqueness
    prefix = Path(filepath).stem.replace("-", "_").replace(".", "_")
    short = text[:30].strip()
    # Create a short hash for uniqueness
    h = hashlib.md5(text.encode()).hexdigest()[:6]
    # Sanitize for use as JSON key
    key = re.sub(r'[^\w]', '_', short)
    key = re.sub(r'_+', '_', key).strip('_')
    return f"{prefix}.{key}_{h}"


def extract_from_file(filepath: Path) -> dict:
    """Extract Chinese strings from a file."""
    strings = OrderedDict()
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  Skip {filepath}: {e}")
        return strings

    for match in CHINESE_RE.finditer(content):
        text = match.group().strip()
        # Skip very short strings (single chars that are likely punctuation)
        if len(text) < 2:
            continue
        # Skip strings that are just comments
        if text.startswith("//") or text.startswith("#"):
            continue
        key = make_key(text, str(filepath))
        if key not in strings:
            strings[key] = text

    return strings


def main():
    all_strings = OrderedDict()

    for filepath in SCAN_FILES:
        if not filepath.exists():
            print(f"  Skip (not found): {filepath}")
            continue
        print(f"  Scanning: {filepath.relative_to(ROOT)}")
        file_strings = extract_from_file(filepath)
        all_strings.update(file_strings)
        print(f"    Found {len(file_strings)} strings")

    print(f"\nTotal unique strings: {len(all_strings)}")

    # Write zh.json (source of truth)
    locales_dir = FRONTEND / "locales"
    locales_dir.mkdir(exist_ok=True)

    zh_path = locales_dir / "zh.json"
    zh_path.write_text(
        json.dumps(all_strings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {zh_path.relative_to(ROOT)}")

    # Write en.json and ja.json stubs (keys only, empty values)
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
