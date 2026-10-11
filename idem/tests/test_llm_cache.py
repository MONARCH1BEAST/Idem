"""Offline tests for idem.llm. The provider is always mocked; no network."""
import hashlib
import json

import httpx
import pytest

from idem import llm
from idem.schemas import AnalysisResult

VALID = json.dumps(
    {
        "summary": "Computes loan interest.",
        "inputs": ["PRINCIPAL", "RATE", "TERM"],
        "outputs": ["INTEREST", "TOTAL"],
        "business_rules": [
            {
                "id": "R1",
                "description": "Interest is principal times rate times term.",
                "cobol_lines": "10-12",
                "confidence": 0.95,
            }
        ],
        "risks": ["Implicit rounding"],
    }
)
BAD = '{"summary": "missing every other field"}'


class FakeProvider:
    """Returns the given responses in order (repeating the last one) and records calls."""

    def __init__(self, *responses: str):
        self.responses = list(responses)
        self.calls: list[str] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append(user)
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.0")


def _install(monkeypatch, provider):
    monkeypatch.setattr(llm, "_call_provider", provider)
    return provider


# ---- the core guarantee: second call never touches the provider ----------
def test_second_call_is_served_from_cache(monkeypatch):
    provider = _install(monkeypatch, FakeProvider(VALID))

    first, err1 = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    second, err2 = llm.call_llm("analyze", "COBOL here", AnalysisResult)

    assert err1 is None and err2 is None
    assert isinstance(first, AnalysisResult)
    assert second == first
    assert len(provider.calls) == 1


def test_cache_works_with_provider_completely_offline(monkeypatch):
    _install(monkeypatch, FakeProvider(VALID))
    llm.call_llm("analyze", "COBOL here", AnalysisResult)

    def no_network(system, user):
        raise ConnectionError("offline")

    monkeypatch.setattr(llm, "_call_provider", no_network)
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert err is None
    assert result.summary == "Computes loan interest."


def test_cache_file_format(monkeypatch, tmp_path):
    _install(monkeypatch, FakeProvider(VALID))
    llm.call_llm("analyze", "COBOL here", AnalysisResult)

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    entry = json.loads(files[0].read_text())

    assert set(entry) == {
        "key", "prompt_name", "model", "temperature",
        "input_hash", "created_at", "raw_response", "parsed",
    }
    assert files[0].stem == entry["key"] == llm._cache_key("analyze", "test-model", 0.0, "COBOL here")
    assert len(entry["key"]) == 16
    assert entry["prompt_name"] == "analyze"
    assert entry["model"] == "test-model"
    assert entry["temperature"] == 0.0
    assert entry["input_hash"] == hashlib.sha256(b"COBOL here").hexdigest()
    assert entry["raw_response"] == VALID
    assert entry["parsed"]["summary"] == "Computes loan interest."
    assert not list(tmp_path.glob("*.tmp"))  # no temp files left behind


def test_regenerate_bypasses_cache(monkeypatch):
    provider = _install(monkeypatch, FakeProvider(VALID))
    llm.call_llm("analyze", "COBOL here", AnalysisResult)
    llm.call_llm("analyze", "COBOL here", AnalysisResult, regenerate=True)
    assert len(provider.calls) == 2


# ---- validation + retry ---------------------------------------------------
def test_retries_once_with_corrective_message(monkeypatch, tmp_path):
    provider = _install(monkeypatch, FakeProvider(BAD, VALID))

    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)

    assert err is None
    assert isinstance(result, AnalysisResult)
    assert len(provider.calls) == 2
    assert "Your previous response failed validation" in provider.calls[1]
    assert "Return only valid JSON matching the schema." in provider.calls[1]
    assert len(list(tmp_path.glob("*.json"))) == 2  # failed attempt + retry, each cached

    # failed attempt is cached with parsed == null
    entries = [json.loads(p.read_text()) for p in tmp_path.glob("*.json")]
    assert sorted(e["parsed"] is None for e in entries) == [False, True]


def test_retry_is_replayed_from_cache_offline(monkeypatch):
    provider = _install(monkeypatch, FakeProvider(BAD, VALID))
    llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert len(provider.calls) == 2

    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert err is None and result is not None
    assert len(provider.calls) == 2  # no new provider calls


def test_gives_error_after_retries_exhausted(monkeypatch):
    provider = _install(monkeypatch, FakeProvider(BAD))

    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)

    assert result is None
    assert "failed validation" in err
    assert len(provider.calls) == 2  # original + 1 retry


def test_retries_zero_means_single_attempt(monkeypatch):
    provider = _install(monkeypatch, FakeProvider(BAD))
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult, retries=0)
    assert result is None and err
    assert len(provider.calls) == 1


def test_accepts_json_wrapped_in_markdown_fences(monkeypatch):
    _install(monkeypatch, FakeProvider(f"Here you go:\n```json\n{VALID}\n```"))
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert err is None
    assert result.outputs == ["INTEREST", "TOTAL"]


def test_no_json_at_all_is_an_error_not_a_crash(monkeypatch):
    _install(monkeypatch, FakeProvider("Sorry, I can't help with that."))
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert result is None
    assert err


def test_provider_exception_returns_error_and_does_not_raise(monkeypatch, tmp_path):
    def boom(system, user):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm, "_call_provider", boom)
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)

    assert result is None
    assert err == "LLM call failed: boom"
    assert not list(tmp_path.glob("*.json"))  # provider failures are not cached


# ---- cache key + prompt rendering -----------------------------------------
def test_cache_key_is_deterministic_16_hex():
    key = llm._cache_key("analyze", "m", 0.0, "text")
    assert key == llm._cache_key("analyze", "m", 0.0, "text")
    assert len(key) == 16
    int(key, 16)  # valid hex


@pytest.mark.parametrize(
    "args",
    [("generate", "m", 0.0, "text"), ("analyze", "other", 0.0, "text"),
     ("analyze", "m", 0.2, "text"), ("analyze", "m", 0.0, "other")],
)
def test_cache_key_changes_with_every_input(args):
    assert llm._cache_key(*args) != llm._cache_key("analyze", "m", 0.0, "text")


def test_render_prompt_fills_placeholders(monkeypatch, tmp_path):
    (tmp_path / "demo.txt").write_text(
        "order={input_order}\nanalysis={ANALYSIS_JSON}\ncobol={COBOL_SOURCE}\njson={\"a\": 1}"
    )
    monkeypatch.setattr(llm, "PROMPTS_DIR", tmp_path)

    out = llm.render_prompt("demo", "MOVE 1 TO X.", analysis_json="{AJ}", input_order="A,B")

    assert "order=A,B" in out
    assert "analysis={AJ}" in out
    assert "cobol=MOVE 1 TO X." in out
    assert 'json={"a": 1}' in out  # braces elsewhere are untouched


# ---- Ollama provider (httpx is mocked; no server needed) -------------------
def _ollama_response(status=200, json_body=None):
    return httpx.Response(
        status, json=json_body, request=httpx.Request("POST", "http://localhost:11434/api/chat")
    )


def test_ollama_request_shape_and_response(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, payload=json)
        return _ollama_response(200, {"message": {"role": "assistant", "content": VALID}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/")

    out = llm._call_provider("SYS", "USER")

    assert out == VALID
    assert seen["url"] == "http://localhost:11434/api/chat"
    payload = seen["payload"]
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]
    assert payload["options"]["temperature"] == 0.0


def test_ollama_not_running_gives_friendly_error(monkeypatch):
    def refuse(url, json, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm.httpx, "post", refuse)
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert result is None
    assert "Cannot reach Ollama" in err and "ollama serve" in err


def test_ollama_missing_model_gives_pull_hint(monkeypatch):
    def not_found(url, json, timeout):
        return _ollama_response(404, {"error": "model 'test-model' not found"})

    monkeypatch.setattr(llm.httpx, "post", not_found)
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert result is None
    assert "ollama pull test-model" in err


def test_ollama_timeout_gives_friendly_error(monkeypatch):
    def slow(url, json, timeout):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", slow)
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert result is None
    assert "did not answer" in err


def test_unsupported_provider_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "somethingelse")
    result, err = llm.call_llm("analyze", "COBOL here", AnalysisResult)
    assert result is None
    assert "Unsupported LLM_PROVIDER" in err