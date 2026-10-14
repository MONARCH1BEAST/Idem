from pathlib import Path

from idem.schemas import TestCase
from idem.verify import verify


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "loanint"


def test_loanint_compiles_and_matches_cobol():
    cobol_source = (SAMPLE / "loanint.cob").read_text(encoding="utf-8")
    java_source = (SAMPLE / "loanint.java").read_text(encoding="utf-8")

    report = verify(
        cobol_source,
        java_source,
        [TestCase(name="typical", stdin="10000\n5\n36\n")],
    )

    assert report.passed == 1
    assert report.failed == 0
    assert report.results[0].cobol_output == "INTEREST=0001500.00\nTOTAL=0011500.00"
    assert report.results[0].java_output == report.results[0].cobol_output