import pytest
from pydantic import ValidationError

from idem.schemas import (
    AnalysisResult,
    BusinessRule,
    CaseResult,
    GenerationResult,
    TestCase,
    VerificationReport,
)

RULE = {
    "id": "R1",
    "description": "Interest is principal times rate times term.",
    "cobol_lines": "42-48",
    "confidence": 0.9,
}


def test_business_rule_and_confidence_bounds():
    rule = BusinessRule(**RULE)
    assert rule.id == "R1"
    assert rule.cobol_lines == "42-48"
    assert rule.confidence == 0.9
    for invalid_confidence in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            BusinessRule(**{**RULE, "confidence": invalid_confidence})


def test_analysis_result_roundtrip():
    a = AnalysisResult(
        summary="Adds two numbers.",
        inputs=["A", "B"],
        outputs=["SUM"],
        business_rules=[
            BusinessRule(id="R1", description="Sum.", cobol_lines="10-12", confidence=0.9)
        ],
        risks=[],
    )
    assert AnalysisResult.model_validate(a.model_dump()).summary == "Adds two numbers."


def test_generation_result_roundtrip():
    g = GenerationResult(
        java_source="class Main {}",
        test_cases=[TestCase(name="t1", stdin="1\n2\n")],
        notes=[],
    )
    assert GenerationResult.model_validate(g.model_dump()).test_cases[0].name == "t1"


def test_verification_models():
    result = CaseResult(name="typical", cobol_output="X=1", java_output="X=1", match=True)
    report = VerificationReport(results=[result], passed=1, failed=0)
    assert report.passed + report.failed == len(report.results)