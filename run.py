import argparse
import sys
from pathlib import Path

from idem.analyze import analyze
from idem.generate import generate
from idem.testcases import generate_stress_cases


def run_pipeline(
    cobol_path: Path,
    regenerate: bool = False,
    improve: bool = False,
) -> dict:
    cobol = cobol_path.read_text(encoding="utf-8")
    sample_key = (
        cobol_path.parent.name
        if cobol_path.parent.parent.name == "samples"
        else cobol_path.stem
    )

    print("[1/3] analyze...", file=sys.stderr)
    analysis, err = analyze(cobol, regenerate=regenerate)
    if err:
        return {"stage": "analyze", "error": err}

    print("[2/3] generate...", file=sys.stderr)
    generation, err = generate(
        cobol,
        analysis,
        regenerate=regenerate,
        improve=improve,
    )
    if err:
        return {"stage": "generate", "error": err}

    print("[3/3] verify...", file=sys.stderr)
    try:
        from idem.verify import verify
        stress = generate_stress_cases("loanint")
        all_cases = list(generation.test_cases) + stress
        print(
            f"  {len(generation.test_cases)} semantic + {len(stress)} stress = "
            f"{len(all_cases)} cases",
            file=sys.stderr,
        )
        report = verify(cobol, generation.java_source, all_cases, sample_key)
    except ImportError:
        report = None
        print("  (verify.py not available yet — skipping)", file=sys.stderr)

    return {
        "analysis": analysis,
        "generation": generation,
        "report": report,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate and verify Java from COBOL.")
    parser.add_argument(
        "sample",
        nargs="?",
        type=Path,
        default=Path("samples/loanint/loanint.cob"),
        help="COBOL source file (defaults to the loanint sample)",
    )
    parser.add_argument(
        "--improve",
        action="store_true",
        help="Generate logically correct Java when COBOL has an obvious bug",
    )
    args = parser.parse_args()
    result = run_pipeline(args.sample, improve=args.improve)

    if "error" in result:
        print(f"FAILED at {result['stage']}: {result['error']}")
        sys.exit(1)

    print("\n=== SUMMARY ===")
    print(result["analysis"].summary)
    print("\n=== BUSINESS RULES ===")
    for rule in result["analysis"].business_rules:
        print(f"  {rule.id}: {rule.description}")

    if result["report"]:
        report = result["report"]
        print(f"\n=== VERIFICATION: {report.passed}/{len(report.results)} passed ===")
        if report.accepted:
            print(f"({report.accepted} accepted divergences)")
            accepted = [case for case in report.results if case.accepted_by_reviewer]
            print("Accepted divergences:", file=sys.stderr)
            for case in accepted:
                print(f"  {case.name}", file=sys.stderr)

        unresolved = [
            case
            for case in report.results
            if not case.match and not case.accepted_by_reviewer
        ]
        if unresolved:
            print("\n=== UNRESOLVED VERIFICATION CASES ===", file=sys.stderr)
            for case in unresolved:
                print(f"  {case.name}: {case.reason}", file=sys.stderr)