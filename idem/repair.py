"""Single-attempt repair loop.

Given a failing VerificationReport, build a diff payload that shows the LLM
exactly what COBOL printed versus what Java printed, then ask the model for
a corrected Java source.
"""

from idem.llm import call_llm, render_prompt
from idem.schemas import (
    GenerationResult,
    TestCase,
    VerificationReport,
)


def _build_diff_payload(
    test_cases: list[TestCase],
    report: VerificationReport,
) -> list[dict]:
    """Return a list of failing cases with stdin, cobol_output, java_output."""
    stdin_by_name = {tc.name: tc.stdin for tc in test_cases}
    failures = []
    for case in report.results:
        if case.match:
            continue
        failures.append({
            "name": case.name,
            "stdin": stdin_by_name.get(case.name, ""),
            "cobol_output": case.cobol_output,
            "java_output": case.java_output,
        })
    return failures


def repair(
    cobol_src: str,
    java_src: str,
    test_cases: list[TestCase],
    report: VerificationReport,
    regenerate: bool = False,
) -> tuple[GenerationResult | None, str | None]:
    """Ask the LLM to fix the Java, given the exact mismatches."""
    failures = _build_diff_payload(test_cases, report)
    if not failures:
        return None, "No failing cases to repair."

    import json
    diff_json = json.dumps(failures, indent=2)

    prompt = render_prompt(
        "repair",
        cobol_source=cobol_src,
        java_source=java_src,
        diff_json=diff_json,
    )

    return call_llm(
        "repair",
        prompt,
        GenerationResult,
        regenerate=regenerate,
    )