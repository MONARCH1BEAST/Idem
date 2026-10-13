import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

PROMPTS_DIR = Path(__file__).parent / "prompts"
CACHE_DIR = Path(__file__).parent.parent / "samples" / "cached"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
TEMPERATURE = 0.0


def _cache_key(prompt_name, model, temperature, input_text):
    h = hashlib.sha256()
    h.update(prompt_name.encode())
    h.update(model.encode())
    h.update(str(temperature).encode())
    h.update(input_text.encode())
    return h.hexdigest()[:16]


def _read_cache(key):
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_cache(key, prompt_name, input_text, raw, parsed):
    path = CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps({
        "key": key,
        "prompt_name": prompt_name,
        "model": OLLAMA_MODEL,
        "temperature": TEMPERATURE,
        "input_hash": hashlib.sha256(input_text.encode()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "raw_response": raw,
        "parsed": parsed,
    }, indent=2), encoding="utf-8")


def _call_provider(system, user, schema):
    """Call Qwen2.5 Coder via Ollama with structured JSON output."""
    url = f"{OLLAMA_HOST}/api/chat"
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
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return body["message"]["content"]


def _load_prompt(prompt_name):
    return (PROMPTS_DIR / f"{prompt_name}.txt").read_text(encoding="utf-8")


def render_prompt(prompt_name, **kwargs):
    template = _load_prompt(prompt_name)
    for key, value in kwargs.items():
        template = template.replace("{" + key.upper() + "}", str(value))
    return template


def call_llm(prompt_name, input_text, schema, regenerate=False, retries=1):
    key = _cache_key(prompt_name, OLLAMA_MODEL, TEMPERATURE, input_text)

    if not regenerate:
        cached = _read_cache(key)
        if cached and cached.get("parsed") is not None:
            return schema.model_validate(cached["parsed"]), None

    system = _load_prompt(prompt_name)
    last_error = None

    for attempt in range(retries + 1):
        try:
            raw = _call_provider(system, input_text, schema)
            parsed = schema.model_validate_json(raw)
            _write_cache(key, prompt_name, input_text, raw, parsed.model_dump())
            return parsed, None
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
            print(f"[llm] attempt {attempt + 1} failed: {last_error}", file=sys.stderr)
            input_text = (
                input_text
                + f"\n\nYour previous response failed validation: {last_error}. "
                + "Return only valid JSON matching the schema."
            )

    return None, f"LLM failed after {retries + 1} attempts: {last_error}"