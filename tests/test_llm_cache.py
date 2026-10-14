import json

from idem import llm
from idem.schemas import AnalysisResult


FAKE = AnalysisResult(summary="x", inputs=[], outputs=[], business_rules=[], risks=[])


def test_cache_hit_does_not_call_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def fake_provider(system, user, schema):
        calls["n"] += 1
        return FAKE.model_dump_json()

    monkeypatch.setattr(llm, "_call_provider", fake_provider)
    r1, e1 = llm.call_llm("analyze", "same input", AnalysisResult)
    r2, e2 = llm.call_llm("analyze", "same input", AnalysisResult)

    assert e1 is None and e2 is None
    assert r1.summary == r2.summary == "x"
    assert calls["n"] == 1
    cached = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert cached["parsed"]["summary"] == "x"


def test_provider_uses_ollama_schema_and_endpoint(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"message":{"content":"{}"}}'

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(llm, "OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setattr(llm, "OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)

    assert llm._call_provider("system", "user", AnalysisResult) == "{}"
    assert seen["url"] == "http://localhost:11434/api/chat"
    assert seen["method"] == "POST"
    assert seen["payload"]["model"] == "qwen2.5-coder:7b"
    assert seen["payload"]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert seen["payload"]["stream"] is False
    assert seen["payload"]["format"] == AnalysisResult.model_json_schema()
    assert seen["payload"]["options"]["temperature"] == 0.0