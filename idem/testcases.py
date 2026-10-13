"""Deterministic, locally generated test cases; this module does not use an LLM."""

import random

from idem.schemas import TestCase

SAMPLE_SPECS = {
    "loanint": [
        {"name": "principal", "safe_max": 100000},
        {"name": "rate", "safe_max": 99},
        {"name": "term", "safe_max": 360},
    ],
}


def _make_case(name: str, values: list[int]) -> TestCase:
    stdin = "\n".join(str(value) for value in values)
    return TestCase(name=name, stdin=f"{stdin}\n")


def _midpoint(spec: dict) -> int:
    return spec["safe_max"] // 2


def _random_case(
    name: str,
    specs: list[dict],
    rng: random.Random,
) -> TestCase:
    values = [rng.randint(0, spec["safe_max"]) for spec in specs]
    return _make_case(name, values)


def generate_stress_cases(
    sample_name: str,
    target_total: int | None = None,
    seed: int = 42,
) -> list[TestCase]:
    """Generate deterministic cases using raw integers.

    Inputs are integers. COBOL PIC clauses imply the decimal position;
    emitting a decimal point in stdin causes COBOL to misinterpret the
    input.
    """
    if sample_name not in SAMPLE_SPECS:
        raise ValueError(f"Unknown sample: {sample_name}")

    specs = SAMPLE_SPECS[sample_name]
    mid_values = [_midpoint(spec) for spec in specs]
    max_values = [spec["safe_max"] for spec in specs]
    candidates = [
        _make_case("All-zero anchor", [0] * len(specs)),
        _make_case("All-one anchor", [1] * len(specs)),
        _make_case("All-mid anchor", mid_values),
        _make_case("All-max safe anchor", max_values),
    ]

    for index, spec in enumerate(specs):
        axis_values = [0, 1, 10, 100, mid_values[index], max_values[index]]
        for value in axis_values:
            values = list(mid_values)
            values[index] = min(value, spec["safe_max"])
            candidates.append(
                _make_case(
                    f"{spec['name'].title()} sweep: {values[index]}",
                    values,
                )
            )

    unique_candidates = []
    seen = set()
    for case in candidates:
        if case.stdin not in seen:
            unique_candidates.append(case)
            seen.add(case.stdin)

    if target_total is None:
        target = len(unique_candidates) + 5
    else:
        target = max(0, target_total)
    cases = unique_candidates[:target]

    rng = random.Random(seed)
    random_index = 1
    while len(cases) < target:
        case = _random_case(f"Seeded random case {random_index}", specs, rng)
        random_index += 1
        if case.stdin in seen:
            continue
        seen.add(case.stdin)
        cases.append(case)

    return cases
