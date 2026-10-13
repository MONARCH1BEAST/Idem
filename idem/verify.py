"""Placeholder — Person A owns the real implementation.

This stub lets Person B's pipeline run end to end before verify.py exists.
Replace this file entirely when A's version is ready.
"""

from idem.schemas import CaseResult, TestCase, VerificationReport


def verify(cobol_src: str, java_src: str, test_cases: list[TestCase]) -> VerificationReport:
    results = [
        CaseResult(
            name=tc.name,
            cobol_output="(not run — verify.py is a stub)",
            java_output="(not run — verify.py is a stub)",
            match=False,
        )
        for tc in test_cases
    ]
    return VerificationReport(results=results, passed=0, failed=len(results))