# Idem — Audit Findings

**Audit date:** 2026-10-13
**Repo revision:** 2519844018e0d84b1c60aa1c084234ae34ce2d50
**Auditor:** AI-assisted holistic audit
**Overall verdict:** NOT-READY

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

### [P0] Verification harness is a stub

**Status:** RESOLVED (2026-10-13)

**Evidence:** `idem/verify.py` contains a placeholder implementation that returns `CaseResult(..., match=False)` for every test case and `VerificationReport(results=..., passed=0, failed=len(results))` instead of invoking `cobc` and `javac` or comparing SSA output. This directly contradicts the project’s “core is verification” requirement.

**Impact:** The finished product cannot prove that generated Java matches COBOL behavior. The core demo/pitch promise is therefore not met.

**Recommendation:** Replace the placeholder with a real compiler-runner that compiles the COBOL and generated Java, executes both on the same stdin, and compares exact stdout output with a clear `VerificationReport`.

**Resolution note:** [P0] Verification harness is a stub — Replaced the placeholder with compiler-backed COBOL/Java execution, exact normalized stdout comparison, a runnable sample CLI, and a compiler smoke test.

### [P1] Clean-machine setup is broken and documentation is missing

**Evidence:** The repository root has no `README.md`, no `B_CONTEXT.md`, and no `samples/loanint/notes.md`. The project also lacks the required `demo/` assets and `scripts/setup.sh` referenced by the spec. These are not optional extras; they are part of the acceptance criteria.

**Impact:** A fresh machine cannot follow the documented setup path, and the project cannot be audited or demoed without ad hoc manual steps.

**Recommendation:** Add the missing docs and demo assets, and make the setup reproducible from the repo root with a single documented install path.

### [P1] Test and import paths are misconfigured

**Evidence:** Running `pytest -q` from the repo root fails with `ModuleNotFoundError: No module named 'idem'`, while running from `C:\Idem\idem` passes. The project also contains a nested `idem/idem/` package and a package-local `pytest.ini` that sets `testpaths = tests` and `pythonpath = .`.

**Impact:** The repository is effectively configured to run from the wrong directory. This breaks standard CI, editor runs, and clean-install workflows.

**Recommendation:** Flatten or fix the package root so that the repository root is the import root, place `pytest.ini` at the repo root, and remove the accidental nested package copy.

### [P2] Duplicate package tree and stale backup code create ambiguity — RESOLVED (2026-10-13)

**Evidence:** The repo contains both `idem/` and `idem/idem/`, as well as a stale backup file `idem/idem/llm_old.py.bak`. This is a strong signal that there are multiple parallel implementations competing for authority.

**Impact:** It is unclear which code is the actual source of truth, increasing the chance of inconsistent behavior, duplicated maintenance effort, and wrong fixes during the final sprint.

**Recommendation:** Keep a single package root, remove the backup/duplicate files, and ensure the repo has one canonical implementation path before the final demo.

**Resolution note (2026-10-13):** Deleted the nested duplicate package and stale backup, retained root environment/dependency files, moved pytest configuration and consolidated tests to the repository root, and replaced the client with the local Ollama version.

### [P2] Dependency configuration does not match the actual runtime contract

**Evidence:** The root `requirements.txt` is missing the expected `httpx` dependency and is substantially lighter than the nested `idem/requirements.txt`. The project also has the wrong environment variable pattern for the actual provider model (`OLLAMA_*` instead of the required `LLM_PROVIDER` / `LLM_MODEL` pattern described in the spec).

**Impact:** The environment can fail in a clean setup, particularly if the implementation expects the same provider variables and packages described by the design document.

**Recommendation:** Consolidate the dependency file and environment contract so there is only one supported provider setup and one authoritative install command.
