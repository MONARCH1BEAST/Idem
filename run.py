import sys
from pathlib import Path

from idem.analyze import analyze
from idem.generate import generate
from idem.repair import repair


def run_pipeline(cobol_path: Path, regenerate: bool = False) -> dict:
    cobol = cobol_path.read_text(encoding="utf-8")

    print("[1/3] analyze...", file=sys.stderr)
    analysis, err = analyze(cobol, regenerate=regenerate)
    if err:
        return {"stage": "analyze", "error": err}

    print("[2/3] generate...", file=sys.stderr)
    generation, err = generate(cobol, analysis, regenerate=regenerate)
    if err:
        return {"stage": "generate", "error": err}

    print("[3/3] verify...", file=sys.stderr)
    try:
        from idem.verify import verify
        report = verify(cobol, generation.java_source, generation.test_cases)
        repaired_once = False
        if report.failed > 0 and not repaired_once:
            print("[4/4] repair...", file=sys.stderr)
            repaired, err = repair(
                cobol,
                generation.java_source,
                generation.test_cases,
                report,
            )
            if repaired:
                report = verify(cobol, repaired.java_source, repaired.test_cases)
                generation = repaired
            elif err:
                print(f"  repair failed: {err}", file=sys.stderr)
            repaired_once = True
    except ImportError:
        report = None
        print("  (verify.py not available yet — skipping)", file=sys.stderr)

    return {
        "analysis": analysis,
        "generation": generation,
        "report": report,
    }


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/loanint/loanint.cob")
    result = run_pipeline(sample)

    if "error" in result:
        print(f"FAILED at {result['stage']}: {result['error']}")
        sys.exit(1)

    print("\n=== SUMMARY ===")
    print(result["analysis"].summary)
    print("\n=== BUSINESS RULES ===")
    for rule in result["analysis"].business_rules:
        print(f"  {rule.id}: {rule.description}")

    if result["report"]:
        print(f"\n=== VERIFICATION: {result['report'].passed}/{len(result['report'].results)} passed ===")