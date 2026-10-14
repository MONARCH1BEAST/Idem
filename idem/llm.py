import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
CACHE_DIR = ROOT / "samples" / "cached"

load_dotenv(ROOT / ".env")

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
TEMPERATURE = 0.0


def _cache_key(prompt_name, model, temperature, input_text):
    digest = hashlib.sha256()
    digest.update(prompt_name.encode("utf-8"))
    digest.update(model.encode("utf-8"))
    digest.update(str(temperature).encode("utf-8"))
    digest.update(input_text.encode("utf-8"))
    return digest.hexdigest()[:16]


def _read_cache(key):
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"[llm] ignoring unreadable cache file {path.name}: {error}", file=sys.stderr)
        return None


def _write_cache(key, prompt_name, input_text, raw, parsed):
    entry = {
        "key": key,
        "prompt_name": prompt_name,
        "model": OLLAMA_MODEL,
        "temperature": TEMPERATURE,
        "input_hash": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raw_response": raw,
        "parsed": parsed,
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary_path, path)


def _call_provider(system, user, schema):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": schema.model_json_schema(),
        "options": {"temperature": TEMPERATURE},
    }
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=900) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body["message"]["content"]


def _load_prompt(prompt_name):
    return (PROMPTS_DIR / f"{prompt_name}.txt").read_text(encoding="utf-8")


def render_prompt(prompt_name, cobol_src=None, **kwargs):
    template = _load_prompt(prompt_name)
    if cobol_src is not None:
        kwargs["cobol_source"] = cobol_src
    for name, value in kwargs.items():
        template = template.replace("{" + name.upper() + "}", str(value))
    return template


def call_llm(prompt_name, input_text, schema, regenerate=False, retries=1):
    system = (
        "You are a precise assistant. Respond with a single valid JSON object "
        "and nothing else: no prose, no markdown fences."
    )
    user_message = input_text
    last_error = "Unknown validation error."

    for attempt in range(retries + 1):
        key = _cache_key(prompt_name, OLLAMA_MODEL, TEMPERATURE, user_message)
        cached = None if regenerate else _read_cache(key)
        raw = None
        result = None

        if cached is not None:
            parsed = cached.get("parsed")
            if parsed is not None:
                try:
                    return schema.model_validate(parsed), None
                except ValidationError as error:
                    last_error = str(error)
            raw = cached.get("raw_response")

        if raw is None:
            try:
                raw = _call_provider(system, user_message, schema)
            except Exception as error:
                return None, f"LLM call failed: {error}"

        try:
            result = schema.model_validate_json(raw)
        except (ValidationError, ValueError) as error:
            last_error = str(error)

        try:
            _write_cache(
                key,
                prompt_name,
                user_message,
                raw,
                result.model_dump(mode="json") if result is not None else None,
            )
        except OSError as error:
            return None, f"Could not write LLM cache: {error}"

        if result is not None:
            return result, None

        print(f"[llm] attempt {attempt + 1} failed validation: {last_error}", file=sys.stderr)
        user_message = (
            f"{input_text}\n\nYour previous response failed validation: {last_error}. "
            "Return only valid JSON matching the schema."
        )

    return None, f"LLM output failed validation after {retries + 1} attempt(s): {last_error}"
