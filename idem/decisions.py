"""Reviewer decisions are stored per sample and treated as an audit
trail. Each entry records the case, the COBOL output, the Java
output, the reviewer's decision, and when it was made. Do not
silently overwrite an existing decision; require an explicit
clear_decision() call first.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from idem.schemas import DivergenceDecision


SAMPLES_DIR = Path(__file__).resolve().parents[1] / "samples"
VALID_DECISIONS = {"preserve_cobol", "accept_java", "skip"}


def _decision_file(sample_key: str) -> Path:
    if (
        not sample_key
        or sample_key in {".", ".."}
        or "/" in sample_key
        or "\\" in sample_key
    ):
        raise ValueError(f"Invalid sample key: {sample_key!r}")
    return SAMPLES_DIR / sample_key / "decisions.json"


def load_decisions(sample_key: str) -> dict[str, DivergenceDecision]:
    path = _decision_file(sample_key)
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}

    if not isinstance(stored, dict):
        raise ValueError(f"Decision file must contain a JSON object: {path}")

    decisions = {}
    for case_name, payload in stored.items():
        decision = DivergenceDecision.model_validate(payload)
        if decision.case_name != case_name:
            raise ValueError(
                f"Decision key does not match case_name in {path}: {case_name!r}"
            )
        decisions[case_name] = decision
    return decisions


def save_decision(sample_key: str, decision: DivergenceDecision) -> None:
    if decision.decision not in VALID_DECISIONS:
        raise ValueError(f"Invalid reviewer decision: {decision.decision!r}")

    path = _decision_file(sample_key)
    decisions = load_decisions(sample_key)
    if decision.case_name in decisions:
        raise ValueError(
            f"A decision already exists for {decision.case_name!r}; "
            "call clear_decision() before saving a replacement."
        )

    if not decision.decided_at:
        decision = decision.model_copy(
            update={"decided_at": datetime.now(timezone.utc).isoformat()}
        )
    decisions[decision.case_name] = decision
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {name: item.model_dump(mode="json") for name, item in decisions.items()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def clear_decision(sample_key: str, case_name: str) -> None:
    path = _decision_file(sample_key)
    decisions = load_decisions(sample_key)
    if case_name not in decisions:
        return
    del decisions[case_name]
    path.write_text(
        json.dumps(
            {name: item.model_dump(mode="json") for name, item in decisions.items()},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
