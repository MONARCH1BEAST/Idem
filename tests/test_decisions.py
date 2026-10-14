import json

import pytest

from idem import decisions
from idem.repair import _build_diff_payload
from idem.schemas import CaseResult, DivergenceDecision, TestCase, VerificationReport
from idem.verify import _verification_report


def _decision(case_name: str, decision: str) -> DivergenceDecision:
    return DivergenceDecision(
        case_name=case_name,
        cobol_output="COBOL",
        java_output="Java",
        decision=decision,
    )


def test_decisions_create_directory_and_require_explicit_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "SAMPLES_DIR", tmp_path)
    decision = _decision("sample case", "accept_java")

    decisions.save_decision("student", decision)

    decision_file = tmp_path / "student" / "decisions.json"
    stored = json.loads(decision_file.read_text(encoding="utf-8"))
    assert stored["sample case"]["decision"] == "accept_java"
    assert stored["sample case"]["decided_at"]
    assert decisions.load_decisions("student")["sample case"].case_name == "sample case"

    with pytest.raises(ValueError, match="clear_decision"):
        decisions.save_decision("student", decision)

    decisions.clear_decision("student", "sample case")
    assert decisions.load_decisions("student") == {}


def test_verification_marks_only_mismatches_accepted_by_reviewer(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(decisions, "SAMPLES_DIR", tmp_path)
    decisions.save_decision("student", _decision("accepted", "accept_java"))
    decisions.save_decision("student", _decision("preserved", "preserve_cobol"))
    decisions.save_decision("student", _decision("skipped", "skip"))

    report = _verification_report(
        [
            CaseResult(
                name="accepted",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
            ),
            CaseResult(
                name="preserved",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
            ),
            CaseResult(
                name="skipped",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
            ),
        ],
        "student",
    )

    assert report.passed == 0
    assert report.failed == 3
    assert report.accepted == 1
    assert report.results[0].accepted_by_reviewer
    assert all(not result.accepted_by_reviewer for result in report.results[1:])


def test_repair_omits_accepted_and_skipped_cases():
    report = VerificationReport(
        results=[
            CaseResult(
                name="accepted",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
                accepted_by_reviewer=True,
            ),
            CaseResult(
                name="skipped",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
            ),
            CaseResult(
                name="preserved",
                cobol_output="COBOL",
                java_output="Java",
                match=False,
            ),
        ],
        passed=0,
        failed=3,
        accepted=1,
        decisions=[
            _decision("accepted", "accept_java"),
            _decision("skipped", "skip"),
            _decision("preserved", "preserve_cobol"),
        ],
    )

    payload = _build_diff_payload(
        [
            TestCase(name="accepted", stdin="1"),
            TestCase(name="skipped", stdin="2"),
            TestCase(name="preserved", stdin="3"),
        ],
        report,
    )

    assert [case["name"] for case in payload] == ["preserved"]
