from idem.schemas import AnalysisResult, BusinessRule, GenerationResult, TestCase


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