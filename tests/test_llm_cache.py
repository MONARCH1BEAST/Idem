from unittest.mock import patch

from idem.llm import call_llm
from idem.schemas import AnalysisResult


FAKE = AnalysisResult(
    summary="x",
    inputs=[],
    outputs=[],
    business_rules=[],
    risks=[],
)


def test_cache_hit_does_not_call_provider(tmp_path, monkeypatch):
    monkeypatch.setattr("idem.llm.CACHE_DIR", tmp_path)
    calls = {"n": 0}

    def fake_provider(system, user, schema):
        calls["n"] += 1
        return FAKE.model_dump_json()

    with patch("idem.llm._call_provider", side_effect=fake_provider):
        r1, e1 = call_llm("analyze", "same input", AnalysisResult)
        r2, e2 = call_llm("analyze", "same input", AnalysisResult)

    assert e1 is None and e2 is None
    assert r1.summary == r2.summary == "x"
    assert calls["n"] == 1