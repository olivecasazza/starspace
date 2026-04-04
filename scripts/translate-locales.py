#!/usr/bin/env python3
"""Translate locale files using OpenRouter API.

Reads zh.json (Chinese source) and fills in missing translations for
en.json and ja.json using Qwen 3 235B via OpenRouter.

Usage:
    OPENROUTER_API_KEY=sk-or-... python3 scripts/translate-locales.py [--lang en] [--lang ja]
    python3 scripts/translate-locales.py --model google/gemini-2.5-flash --lang en

Requires:
    pip install openai
"""

import argparse
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("Install openai: pip install openai")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "frontend" / "locales"

LANG_NAMES = {
    "en": "English",
    "ja": "Japanese",
}

DEFAULT_MODEL = "qwen/qwen3-235b-a22b-2507"
BATCH_SIZE = 50  # Strings per API call


def load_json(path: Path) -> OrderedDict:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def translate_batch(client, model: str, strings: dict, target_lang: str) -> dict:
    """Translate a batch of Chinese strings to target language."""
    lang_name = LANG_NAMES.get(target_lang, target_lang)

    prompt = f"""Translate the following Chinese UI strings to {lang_name}.
These are from a pixel-art AI agent dashboard application called "Star Office".
Return ONLY a valid JSON object with the same keys and translated values.
Do NOT include any markdown formatting, code fences, or explanation.

Rules:
- Keep technical terms, brand names, and code references unchanged
- Match the tone and length of the originals -- these are short UI labels and messages
- Preserve any HTML tags, placeholders like {{name}}, and special characters
- For Japanese: use natural UI Japanese (not overly formal keigo)

{json.dumps(strings, ensure_ascii=False, indent=2)}"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=8192,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    # Try to find JSON object in the response
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    return json.loads(text)


def main():
    parser = argparse.ArgumentParser(description="Translate locale files via OpenRouter")
    parser.add_argument("--lang", action="append", default=None,
                        help="Target language(s) (default: en, ja)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"OpenRouter model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                        help=f"Strings per API call (default: {BATCH_SIZE})")
    args = parser.parse_args()

    targets = args.lang or ["en", "ja"]

    zh_path = LOCALES / "zh.json"
    if not zh_path.exists():
        print("Run extract-strings.py first to generate zh.json")
        sys.exit(1)

    zh = load_json(zh_path)
    print(f"Source: {len(zh)} strings")
    print(f"Model: {args.model}")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY environment variable")
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

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
        failed = 0

        for i in range(0, len(keys), args.batch_size):
            batch_keys = keys[i:i + args.batch_size]
            batch = OrderedDict((k, todo[k]) for k in batch_keys)
            batch_num = i // args.batch_size + 1
            total_batches = (len(keys) + args.batch_size - 1) // args.batch_size
            print(f"  Batch {batch_num}/{total_batches} ({len(batch)} strings)...", end=" ", flush=True)

            try:
                result = translate_batch(client, args.model, batch, lang)
                translated.update(result)
                print("ok")
            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
                failed += len(batch_keys)
                for k in batch_keys:
                    translated[k] = ""
            except Exception as e:
                print(f"error: {e}")
                failed += len(batch_keys)
                for k in batch_keys:
                    translated[k] = ""

        # Merge with existing (preserve key order from zh.json)
        result = OrderedDict()
        for key in zh:
            if key in translated and translated[key]:
                result[key] = translated[key]
            elif key in existing and existing[key]:
                result[key] = existing[key]
            else:
                result[key] = ""

        lang_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        completed = sum(1 for v in result.values() if v)
        print(f"  Wrote {lang_path.relative_to(ROOT)} ({completed}/{len(result)} translated, {failed} failed)")


if __name__ == "__main__":
    main()
