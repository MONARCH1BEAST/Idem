"""
Smoke test for idem.llm._call_provider.

Run:
    python -u C:\\Idem\\test_llm.py

Required env vars (PowerShell):
    $env:IDEM_BASE_URL = 'https://api.openai.com/v1'
    $env:IDEM_API_KEY  = 'sk-...'
    $env:IDEM_MODEL    = 'gpt-4o-mini'
"""

from __future__ import annotations

import json
import os
import sys

from idem import llm


def main() -> int:
    # Show what we're about to use, so a 404 is obvious immediately.
    print("BASE_URL :", os.environ.get("IDEM_BASE_URL", llm.DEFAULT_BASE_URL))
    print("MODEL    :", os.environ.get("IDEM_MODEL", llm.DEFAULT_MODEL))
    print("API_KEY  :", "set" if os.environ.get("IDEM_API_KEY") else "MISSING")
    print("-" * 60)

    system = "Reply with JSON only."
    user = 'Return {"status": "ok"}'

    try:
        result = llm._call_provider(system, user)
    except llm.LLMError as e:
        print("LLM call failed:", file=sys.stderr)
        print(e, file=sys.stderr)
        return 1

    print("Raw response:")
    print(result)

    try:
        print("Parsed JSON:", json.loads(result))
    except json.JSONDecodeError:
        print("(note: response was not valid JSON)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())