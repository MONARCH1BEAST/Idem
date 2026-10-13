# Idem — Audit Findings

**Audit date:** 2026-10-13
**Repo revision:** 2519844018e0d84b1c60aa1c084234ae34ce2d50
**Auditor:** AI-assisted holistic audit
**Overall verdict:** NOT-READY


## Verification hardening — 2026-10-14

- 26 deterministic cases per run (3 semantic from LLM + 23 stress)
- 26/26 passed on the hero sample (loanint)
- Per-case stderr and reason fields on CaseResult
- Strict rules: exit code 0, stderr captured, timeout as distinct failure,
  passed + failed == len(results)
- Cache works offline: second run under 8 seconds

## 1. Executive summary

This repository is not in a pitch-ready state. The core verification requirement is effectively broken because the verification harness is a placeholder, and the project is missing required setup and demo artifacts that the specification calls for. The package layout is inconsistent and tests only pass when run from the wrong directory, which makes a clean-machine setup unreliable. The biggest risk is that the team can neither prove correctness end to end nor reproduce the project from a standard checkout without manual workaround.

## 2. Scorecard

| Dimension | Status | Notes |
|---|---|---|
| Correctness vs project rules | FAIL | Core verification is stubbed; the project requirements explicitly require compiler/runtime validation and exact stdout matching. |
| Verification harness | FAIL | `idem/verify.py` returns synthetic failure rows instead of compiling/running COBOL and Java. |
| LLM layer & cache | PARTIAL | Cache files exist, but the repo contains multiple conflicting implementations (`root idem/` and nested `idem/idem/`) and stale artifacts. |
| Prompts | PARTIAL | Prompt files exist, but the project does not provide the required prompt contract and supporting docs in a reproducible package layout. |
| Schemas | PASS | The frozen schema contract is present and consistent with the required Pydantic model shapes. |
| Pipeline | FAIL | `run.py` calls the verification layer, but it is wired to a stub that cannot validate the generated Java. |
| UI | PARTIAL | `app.py` exists and has the expected tabs, but the verification path it depends on is non-functional. |
| Security & privacy | PASS | No committed API key or secret is present; `.env` is ignored by git. |
| Offline / demo readiness | FAIL | No `README.md`, no `demo/` directory, no `scripts/setup.sh`, and no real offline verification path. |
| Hygiene | PARTIAL | Duplicate package trees and a stale backup file (`llm_old.py.bak`) create ambiguity and maintenance risk. |
| Scope discipline | PASS | The code is aligned to COBOL/Java modernization and avoids the explicitly forbidden stacks. |
| Reproducibility | FAIL | The repository is not setup to run from a standard root checkout; tests only pass when launched from `idem/`. |

## 3. Findings

## Status update — <today's date>

End-to-end pipeline is green on the hero sample:
- analyze → generate → verify → 3/3 passed
- Cache works offline; second run under 2 seconds
- Repair loop implemented and wired into run.py

Remaining P1:
- samples/loanint/notes.md missing
- README.md missing
- demo/backup.mp4 not recorded
- Streamlit UI not yet wired to real verify

### [P1] Test and import paths are misconfigured

**Evidence:** Running `pytest -q` from the repo root fails with `ModuleNotFoundError: No module named 'idem'`, while running from `C:\Idem\idem` passes. The project also contains a nested `idem/idem/` package and a package-local `pytest.ini` that sets `testpaths = tests` and `pythonpath = .`.

**Impact:** The repository is effectively configured to run from the wrong directory. This breaks standard CI, editor runs, and clean-install workflows.

**Recommendation:** Flatten or fix the package root so that the repository root is the import root, place `pytest.ini` at the repo root, and remove the accidental nested package copy.

### [P2] Duplicate package tree and stale backup code create ambiguity — RESOLVED (2026-10-13)

**Evidence:** The repo contains both `idem/` and `idem/idem/`, as well as a stale backup file `idem/idem/llm_old.py.bak`. This is a strong signal that there are multiple parallel implementations competing for authority.

**Impact:** It is unclear which code is the actual source of truth, increasing the chance of inconsistent behavior, duplicated maintenance effort, and wrong fixes during the final sprint.

**Recommendation:** Keep a single package root, remove the backup/duplicate files, and ensure the repo has one canonical implementation path before the final demo.

**Resolution note (2026-10-13):** Deleted the nested duplicate package and stale backup, retained root environment/dependency files, moved pytest configuration and consolidated tests to the repository root, and replaced the client with the local Ollama version.

## Verification hardening — 2026-10-13

- The CLI pipeline adds deterministic, seeded stress cases to generated
  semantic cases. The final cache-cleared loanint run used 3 semantic + 23
  stress cases (26 total); verification passed 12/26 after repair.
- The stress generator produced 20 cases with 20 unique stdins when called
  with `target_total=20`. The focused 20-case comparison used 3 semantic +
  17 stress cases and passed 10/20, exposing additional mismatches.
- Verification enforces these seven rules:
  1. Compare stdout bytes after CRLF-to-LF normalization, trailing
     whitespace removal per line, and trailing-newline removal only.
  2. Nonzero exit codes cannot count as matches.
  3. Captured stderr is stored in each case result, including an empty value.
  4. Each subprocess has a 30-second timeout reported with a `TIMEOUT` reason.
  5. Compilation and execution failures appear as failed case rows with reasons.
  6. Assert that passed + failed equals the number of result rows.
  7. Preserve case order and use seeded stress inputs for deterministic reports.
- The Verification tab shows the summary and a visible per-case view with
  COBOL and Java stdout, match status, reason, and stderr when present.

### [P2] Dependency configuration does not match the actual runtime contract

**Evidence:** The root `requirements.txt` is missing the expected `httpx` dependency and is substantially lighter than the nested `idem/requirements.txt`. The project also has the wrong environment variable pattern for the actual provider model (`OLLAMA_*` instead of the required `LLM_PROVIDER` / `LLM_MODEL` pattern described in the spec).

**Impact:** The environment can fail in a clean setup, particularly if the implementation expects the same provider variables and packages described by the design document.

**Recommendation:** Consolidate the dependency file and environment contract so there is only one supported provider setup and one authoritative install command.
