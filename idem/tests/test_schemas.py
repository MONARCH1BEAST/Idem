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


def test_business_rule():
    rule = BusinessRule(**RULE)
    assert rule.id == "R1"
    assert rule.cobol_lines == "42-48"
    assert rule.confidence == 0.9


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_business_rule_confidence_out_of_range(bad):
    with pytest.raises(ValidationError):
        BusinessRule(**{**RULE, "confidence": bad})


def test_analysis_result():
    result = AnalysisResult(
        summary="Computes loan interest.",
        inputs=["PRINCIPAL", "RATE", "TERM"],
        outputs=["INTEREST", "TOTAL"],
        business_rules=[RULE],
        risks=["Implicit rounding on COMPUTE"],
    )
    assert result.inputs == ["PRINCIPAL", "RATE", "TERM"]
    assert result.business_rules[0].id == "R1"
    assert result.risks == ["Implicit rounding on COMPUTE"]


def test_analysis_result_missing_field():
    with pytest.raises(ValidationError):
        AnalysisResult(summary="only a summary")


def test_test_case():
    case = TestCase(name="typical", stdin="10000.00\n5.25\n36\n")
    assert case.name == "typical"
    assert case.stdin.endswith("\n")


def test_generation_result():
    result = GenerationResult(
        java_source="public class Main {}",
        test_cases=[{"name": "zero", "stdin": "0\n0\n0\n"}],
        notes=["Uses BigDecimal."],
    )
    assert result.java_source.startswith("public class Main")
    assert result.test_cases[0].name == "zero"
    assert result.notes == ["Uses BigDecimal."]


def test_case_result():
    case = CaseResult(name="typical", cobol_output="A=1.00", java_output="A=1.00", match=True)
    assert case.match is True


def test_verification_report():
    report = VerificationReport(
        results=[
            {"name": "a", "cobol_output": "X=1", "java_output": "X=1", "match": True},
            {"name": "b", "cobol_output": "X=1", "java_output": "X=2", "match": False},
        ],
        passed=1,
        failed=1,
    )
    assert report.passed + report.failed == len(report.results)
    assert report.results[1].match is False