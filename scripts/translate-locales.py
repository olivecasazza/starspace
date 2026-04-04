#!/usr/bin/env python3
"""Translate locale files using the Anthropic API.

Reads zh.json (Chinese source) and fills in missing translations for
en.json and ja.json using Claude as the translation backend.

Usage:
    ANTHROPIC_API_KEY=sk-... python3 scripts/translate-locales.py [--lang en] [--lang ja]

Requires:
    pip install anthropic
"""

import argparse
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Install anthropic: pip install anthropic")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "frontend" / "locales"

LANG_NAMES = {
    "en": "English",
    "ja": "Japanese",
}

BATCH_SIZE = 50  # Strings per API call


def load_json(path: Path) -> OrderedDict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def translate_batch(client, strings: dict, target_lang: str) -> dict:
    """Translate a batch of Chinese strings to target language."""
    lang_name = LANG_NAMES.get(target_lang, target_lang)

    prompt = f"""Translate the following Chinese UI strings to {lang_name}.
These are from a pixel-art AI agent dashboard application.
Return ONLY a JSON object with the same keys and translated values.
Keep technical terms, brand names, and code references unchanged.
Match the tone and length of the originals -- these are UI labels and messages.

Input:
{json.dumps(strings, ensure_ascii=False, indent=2)}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    # Extract JSON from response (handle markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(description="Translate locale files")
    parser.add_argument("--lang", action="append", default=None,
                        help="Target language(s) (default: en, ja)")
    args = parser.parse_args()

    targets = args.lang or ["en", "ja"]

    zh_path = LOCALES / "zh.json"
    if not zh_path.exists():
        print("Run extract-strings.py first to generate zh.json")
        sys.exit(1)

    zh = load_json(zh_path)
    print(f"Source: {len(zh)} strings")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    for lang in targets:
        lang_path = LOCALES / f"{lang}.json"
        if lang_path.exists():
            existing = load_json(lang_path)
        else:
            existing = OrderedDict()

        # Find strings that need translation
        todo = OrderedDict()
        for key, value in zh.items():
            if key not in existing or not existing[key]:
                todo[key] = value

        if not todo:
            print(f"{lang}: already complete ({len(existing)} strings)")
            continue

        print(f"{lang}: {len(todo)} strings to translate...")

        # Process in batches
        keys = list(todo.keys())
        translated = OrderedDict()

        for i in range(0, len(keys), BATCH_SIZE):
            batch_keys = keys[i:i + BATCH_SIZE]
            batch = OrderedDict((k, todo[k]) for k in batch_keys)
            print(f"  Batch {i // BATCH_SIZE + 1}/{(len(keys) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} strings)")

            try:
                result = translate_batch(client, batch, lang)
                translated.update(result)
            except Exception as e:
                print(f"  Error: {e}")
                # Fill with empty strings on failure
                for k in batch_keys:
                    translated[k] = ""

        # Merge with existing
        for key in zh:
            if key in translated and translated[key]:
                existing[key] = translated[key]
            elif key not in existing:
                existing[key] = ""

        lang_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Wrote {lang_path.relative_to(ROOT)} ({len(existing)} strings)")


if __name__ == "__main__":
    main()
