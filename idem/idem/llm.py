"""Thin LLM wrapper with a deterministic on-disk cache.

Every LLM call in Idem goes through call_llm(). Responses are cached in
samples/cached/ so the demo can run offline. Nothing here raises to the
caller: failures come back as (None, "human-readable error").

Logging goes to stderr only (stdout belongs to the UI / pipeline).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = PACKAGE_DIR.parent
PROMPTS_DIR = PACKAGE_DIR / "prompts"
CACHE_DIR = ROOT / "samples" / "cached"

# The full task prompt (rendered from prompts/*.txt) is sent as the user
# message. Because it is part of the cache key, editing a prompt template
# automatically invalidates stale cache entries.
SYSTEM_PROMPT = (
    "You are a precise assistant. Respond with a single valid JSON object "
    "and nothing else: no prose, no markdown fences."
)

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
MAX_TOKENS = 4096          # Ollama num_predict: max tokens generated
DEFAULT_NUM_CTX = 8192     # Ollama context window (prompt + output)
CONNECT_TIMEOUT = 5.0      # fail fast if Ollama isn't running
READ_TIMEOUT = 600.0       # local models can be slow, especially on CPU

load_dotenv(ROOT / ".env")  # load .env once, at import time


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def _log(msg: str) -> None:
    print(f"[idem.llm] {msg}", file=sys.stderr)


def _model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def _num_ctx() -> int:
    try:
        return int(os.getenv("LLM_NUM_CTX", str(DEFAULT_NUM_CTX)))
    except ValueError:
        return DEFAULT_NUM_CTX


def _temperature() -> float:
    try:
        return float(os.getenv("LLM_TEMPERATURE", "0.0"))
    except ValueError:
        return 0.0


def _trim(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


def _cache_key(prompt_name: str, model: str, temperature: float, input_text: str) -> str:
    h = hashlib.sha256()
    h.update(prompt_name.encode())
    h.update(model.encode())
    h.update(str(temperature).encode())
    h.update(input_text.encode())
    return h.hexdigest()[:16]


def render_prompt(prompt_name: str, cobol_src: str, **extras: str) -> str:
    """Load prompts/{prompt_name}.txt and fill in its placeholders.

    {COBOL_SOURCE} is replaced with cobol_src. Each extra keyword fills both
    {key} and {KEY}, e.g. analysis_json="..." fills {analysis_json} and
    {ANALYSIS_JSON}. Plain str.replace is used (not str.format) so the JSON
    braces in prompts and COBOL source are safe.
    """
    text = (PROMPTS_DIR / f"{prompt_name}.txt").read_text(encoding="utf-8")
    for name, value in extras.items():
        for token in ("{" + name + "}", "{" + name.upper() + "}"):
            text = text.replace(token, str(value))
    return text.replace("{COBOL_SOURCE}", cobol_src)


# --------------------------------------------------------------------------
# provider (the ONLY place that talks to an LLM API)
# --------------------------------------------------------------------------
def _ollama_error_message(error: httpx.HTTPStatusError, model: str) -> str:
    try:
        detail = error.response.json().get("error", "")
    except ValueError:
        detail = ""
    if error.response.status_code == 404:
        return f"Ollama doesn't have model '{model}'. Download it with: ollama pull {model}"
    return f"Ollama returned HTTP {error.response.status_code}: {detail or error.response.text[:200]}"


def _call_provider(system: str, user: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider != "ollama":
        raise RuntimeError(f"Unsupported LLM_PROVIDER '{provider}'. Only 'ollama' is wired up.")

    base_url = os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = _model()
    payload = {
        "model": model,
        "stream": False,
        "format": "json",  # Ollama constrains the output to valid JSON
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {
            "temperature": _temperature(),
            "seed": 0,  # extra determinism on top of temperature
            "num_ctx": _num_ctx(),
            "num_predict": MAX_TOKENS,
        },
    }

    try:
        response = httpx.post(
            f"{base_url}/api/chat",
            json=payload,
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        )
        response.raise_for_status()
        return response.json()["message"]["content"]
    except httpx.ConnectError:
        raise RuntimeError(
            f"Cannot reach Ollama at {base_url}. Is it running? Start it with: ollama serve"
        ) from None
    except httpx.TimeoutException:
        raise RuntimeError(
            f"Ollama did not answer within {int(READ_TIMEOUT)}s. Try a smaller model."
        ) from None
    except httpx.HTTPStatusError as e:
        raise RuntimeError(_ollama_error_message(e, model)) from None
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("Ollama sent a response in an unexpected format.") from None


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------
def _extract_json(raw: str) -> str:
    """Return the first complete {...} object found in raw."""
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in the model response.")
    try:
        _, end = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as e:
        raise ValueError(f"Response contained malformed JSON: {e}") from e
    return raw[start : start + end]


def _parse(raw: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str | None]:
    try:
        return schema.model_validate_json(_extract_json(raw)), None
    except (ValidationError, ValueError) as e:
        return None, _trim(str(e))


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------
def _read_cache(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _log(f"ignoring unreadable cache file {path.name}: {e}")
        return None


def _write_cache(
    key: str,
    prompt_name: str,
    model: str,
    temperature: float,
    input_text: str,
    raw: str,
    result: BaseModel | None,
) -> None:
    entry = {
        "key": key,
        "prompt_name": prompt_name,
        "model": model,
        "temperature": temperature,
        "input_hash": hashlib.sha256(input_text.encode()).hexdigest(),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "raw_response": raw,
        "parsed": result.model_dump(mode="json") if result is not None else None,
    }
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / f"{key}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic: no half-written cache files
    except OSError as e:
        _log(f"could not write cache file for {key}: {e}")


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def call_llm(
    prompt_name: str,
    input_text: str,
    schema: type[BaseModel],
    regenerate: bool = False,
    retries: int = 1,
) -> tuple[BaseModel | None, str | None]:
    """Call the LLM (or the cache) and return (parsed_result, error_message).

    On success: (model_instance, None).
    On failure: (None, "human-readable error"). Never raises.
    """
    model = _model()
    temperature = _temperature()
    user_message = input_text
    last_error = "Unknown error."

    for attempt in range(retries + 1):
        key = _cache_key(prompt_name, model, temperature, user_message)
        entry = None if regenerate else _read_cache(CACHE_DIR / f"{key}.json")

        if entry is not None:
            # --- replay from cache -------------------------------------
            cached_parsed = entry.get("parsed")
            if cached_parsed is not None:
                try:
                    _log(f"cache hit {key}")
                    return schema.model_validate(cached_parsed), None
                except ValidationError as e:
                    _log(f"cached 'parsed' no longer matches schema ({key}): {e.error_count()} error(s)")
            raw = entry.get("raw_response", "")
        else:
            # --- real provider call ------------------------------------
            try:
                _log(f"calling provider for {prompt_name} (key {key}, attempt {attempt + 1})")
                raw = _call_provider(SYSTEM_PROMPT, user_message)
            except Exception as e:  # noqa: BLE001 - UI must never crash
                return None, f"LLM call failed: {e}"

        result, error = _parse(raw, schema)

        if entry is None:
            # write BEFORE returning, so a failed attempt is cached under its own key
            _write_cache(key, prompt_name, model, temperature, user_message, raw, result)

        if result is not None:
            return result, None

        last_error = error or last_error
        user_message = (
            f"{input_text}\n\nYour previous response failed validation: {last_error}. "
            "Return only valid JSON matching the schema."
        )

    return None, f"Model output failed validation after {retries + 1} attempt(s): {last_error}"