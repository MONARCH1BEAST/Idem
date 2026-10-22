# Idem — Technical Specification

## 1. Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language(s) | Python 3.11+; generated Java 21; input COBOL | Python implements the UI, pipeline, LLM integration, schemas, reviewer decisions, and verification orchestration. Idem translates COBOL source into a Java `Main` class, then compiles and executes both programs. |
| LLM & Inference Engine | Ollama local HTTP API (`/api/chat`); default model `qwen2.5-coder:7b`; temperature `0.0` | Produces structured analysis, Java generation, repair, and mismatch diagnosis. `OLLAMA_HOST` and `OLLAMA_MODEL` are configurable through the environment. |
| Web Framework & UI | Streamlit | Provides the sample/upload interface, Improve Mode, explanation/rules/Java/tests/verification tabs, repair-loop toggle, reviewer controls, and downloads. |
| Validation & Data Modeling | Pydantic 2 (`BaseModel`, `Field`) | Validates structured LLM responses and models analysis, generation, test cases, verification outcomes, and reviewer decisions. |
| Verification & Execution | GnuCOBOL `cobc`; Java `javac` and `java`; Python `subprocess` | Compiles COBOL and generated Java, runs both against identical stdin test inputs, captures output and diagnostics, and compares normalized stdout. |
| Storage & Caching | JSON files under `samples/cached/`; reviewer JSON at `samples/<sample_key>/decisions.json`; Streamlit session state | Reuses validated LLM results, persists human decisions per sample, and retains a run's results as the UI rerenders. No database is used. |
| Environment (OS/Containerization) | Python virtual environment; WSL2 Ubuntu development environment; Ollama may run on Windows | The project context describes WSL2 Ubuntu for application/runtime tools and Ollama on Windows for GPU access. The repository has no configured Dockerfile or container orchestration. |

Python dependencies declared in `requirements.txt` are `pydantic>=2.6`, `python-dotenv>=1.0`, `streamlit>=1.35`, and `pytest>=8.0`. The inference client uses Python's standard-library `urllib.request`; no Ollama SDK or external HTTP client is declared.

## 2. System Architecture Workflow

### UI run path

1. **Input selection:** In [app.py](./app.py), the user chooses the curated `loanint` sample or uploads a COBOL file. Sample runs expose a “Regenerate (ignore cache)” option, which defaults off. Upload runs always set `regenerate=True`. The UI also exposes Improve Mode and “Disable repair loop (faster demo),” which defaults on.
2. **Pipeline entry:** Clicking **Run pipeline** reads the sample or uploaded source and invokes `_run_pipeline(cobol, sample_key, regenerate, improve)`. The result is held in `st.session_state.result` so switching tabs does not rerun the pipeline.
3. **Analysis phase:** `idem.analyze.analyze` renders `idem/prompts/analyze.txt` with the COBOL source and calls `call_llm` with `AnalysisResult`. The result contains a summary, ordered inputs and outputs, business rules, and source-specific risks. A returned error is displayed and stops the pipeline.
4. **Generation phase:** `idem.generate.generate` selects `generate_improved.txt` when Improve Mode is on and `generate.txt` otherwise. It supplies the COBOL source and JSON-serialized analysis, then validates the response as `GenerationResult` (Java source, test cases, and notes). A returned error is displayed and stops the pipeline.
5. **Test case assembly:** The UI uses the LLM-generated semantic test cases. When `sample_key` is supported by `idem.testcases` (currently `loanint`; an uploaded filename with that stem also matches), it also calls `generate_stress_cases(sample_key)`, which creates deterministic anchors, single-input sweeps, and seeded random cases. Unsupported sample keys are caught and produce no stress cases.
6. **Verification harness:** `idem.verify.verify` compiles the COBOL and Java once for the run, executes both compiled programs for each assembled test case using the same stdin, normalizes their stdout, and creates a `VerificationReport`. This report is displayed in the Verification tab with per-case output and reasons.
7. **Repair loop:** `app.py` selects repairable mismatches, excluding reviewer-accepted cases and cases with a saved `skip` decision. If at least one remains and the repair loop is enabled, `idem.repair.repair` sends the source, Java, and exact failing-case differences to the repair prompt. A successful repair is verified again once. Repair errors are shown as warnings; the original verification report remains available. When the repair toggle is on, the repair call is skipped and the pipeline still completes with the existing report.
8. **Mismatch diagnosis and reviewer decision engine:** For an unmatched case, the Verification tab's **Explain this mismatch** button calls `idem.diagnose.diagnose`, which sends the COBOL source, generated Java, stdin, and both outputs through `idem/prompts/diagnose.txt` and displays the returned explanation. This does not alter verification results. For an unmatched, not-yet-accepted case, the tab also offers **Preserve COBOL behaviour**, **Accept Java behaviour**, and **Skip**. `idem.decisions` validates and persists decisions in `samples/<sample_key>/decisions.json`, including both outputs and a UTC timestamp. Replacing an existing decision requires clearing it first. On a subsequent verification, `_verification_report` loads those decisions: `accept_java` marks the mismatch as reviewer-accepted; `skip` is excluded from repair; `preserve_cobol` remains an unresolved mismatch and can be repaired. The UI reruns the pipeline after saving a decision.

### Command-line runner

`run.py` provides a non-UI pipeline. Its default input is `samples/loanint/loanint.cob`; an optional positional path can select another COBOL file, and `--improve` selects Improve Mode. It runs analysis, generation, verification, and one repair attempt if repairable cases remain, then prints a summary and verification counts. In the current implementation the CLI always generates stress cases for `"loanint"`, regardless of the selected source path; unlike the UI, it has no repair-disable toggle.

## 3. The Verification Engine (The Core)

The public verification entry point is `idem.verify.verify(cobol_src, java_src, test_cases, sample_key=None)`.

### Compilation and subprocess management

- `verify` checks that `java` is available, then `_compile` checks for `cobc`, `javac`, and `java` on `PATH`.
- It creates a temporary working directory with separate COBOL and Java subdirectories. Source text is normalized to LF line endings and written to `program.cob` and `Main.java`.
- COBOL is compiled once with `cobc -x -o <temporary executable> <source>`. Java is compiled once with `javac -d <java directory> <source>`.
- On Windows, `_compiler_environment` adjusts GnuCOBOL environment paths (including short-path handling for install locations with spaces) and runtime DLLs are copied or added to `PATH` when discovered.
- Each test case runs the COBOL executable and `java -cp <java directory> Main`, sequentially, with identical UTF-8-encoded stdin. `_run` uses `subprocess.run` with captured stdout/stderr, `check=False`, and a 30-second timeout for each compiler or program invocation.
- Temporary compiler artifacts are removed automatically by `tempfile.TemporaryDirectory`.

### Output normalization and match rules

`_normalize` operates on output bytes. It changes CRLF (`\r\n`) to LF (`\n`), strips trailing whitespace from each line, joins the lines with LF, and removes trailing LF characters at the end. It preserves leading whitespace and internal line breaks. The normalized COBOL and Java stdout bytes must be identical for a case to match.

Both programs must exit with code zero. A nonzero exit code makes the case fail and is recorded in its reason. A subprocess exceeding 30 seconds is reported as a timeout; compiler timeouts fail all cases, while an execution timeout is recorded for that program and case. Compiler/runtime lookup errors and compilation errors are also represented as failed `CaseResult` entries rather than being silently treated as success.

Stderr from both programs is captured and stored in `CaseResult.stderr` for diagnosis. **Non-empty stderr by itself does not make a case fail**: the match predicate requires no execution reasons (such as nonzero exit or timeout) and equal normalized stdout. Compilation failure diagnostics include compiler stdout and stderr in the reported reason.

`_verification_report` calculates `passed` from matching cases and `failed` as total cases minus passed, enforcing `passed + failed == len(results)`. It then loads reviewer decisions when `sample_key` is supplied and marks mismatches with an `accept_java` decision as accepted. Acceptance does not change the original case's `match` flag or reduce `failed`; the report separately exposes `accepted`.

## 4. Caching Strategy

`idem.llm` uses `samples/cached/` for deterministic, file-based response caching:

- `_cache_key` hashes the concatenation of prompt name, configured model, temperature, and complete rendered input text with SHA-256. The first 16 hexadecimal characters identify the cache file `<key>.json`.
- A cache entry stores the key, prompt name, model, temperature, SHA-256 hash of the input, UTC creation time, raw provider response, and a parsed Pydantic dump when validation succeeds.
- Unless `regenerate=True`, `call_llm` checks the cache before making an API request. A valid parsed payload is validated against the requested schema and returned directly. If that payload is absent or invalid, the raw response is validated instead.
- On a cache miss, `_call_provider` sends an Ollama `/api/chat` request with the selected model, system instruction requiring JSON, a JSON schema in `format`, and temperature `0.0`. Provider calls have a 900-second timeout. Successful or invalid raw responses are cached using a temporary file and atomic `os.replace`.
- Pydantic validation failures are retried once with a corrective instruction appended to the input. The retry input has its own cache key. Provider, cache-write, and final validation failures are returned as explicit error strings; unreadable cache files are logged to stderr and treated as misses.
- Sample mode can therefore demonstrate previously cached analysis and generation without a live model call, provided the matching cache entries exist. Uploaded sources use `regenerate=True`, so those requests bypass cache reads and require the configured local inference service.

## 5. Data Models (Pydantic)

All core schemas are defined in `idem/schemas.py`.

| Schema | Key fields |
|---|---|
| `AnalysisResult` | `summary: str`; `inputs: list[str]`; `outputs: list[str]`; `business_rules: list[BusinessRule]`; `risks: list[str]`. |
| `BusinessRule` | `id: str`; `description: str`; `cobol_lines: str`; `confidence: float`, constrained by `Field` to `0.0 <= confidence <= 1.0`. |
| `GenerationResult` | `java_source: str`; `test_cases: list[TestCase]`; `notes: list[str]`. |
| `TestCase` | `name: str`; `stdin: str`. |
| `VerificationReport` | `results: list[CaseResult]`; `passed: int`; `failed: int`; `accepted: int` defaulting to `0`; `decisions: list[DivergenceDecision]`, defaulting to an empty list. |
| `CaseResult` | `name: str`; `cobol_output: str`; `java_output: str`; `match: bool`; `stderr: str` defaulting to `""`; `reason: str` defaulting to `""`; `accepted_by_reviewer: bool` defaulting to `False`. |
| `DivergenceDecision` | `case_name: str`; `cobol_output: str`; `java_output: str`; `decision: str`; `reason: str` defaulting to `""`; `decided_at: str` defaulting to `""`. Decision values accepted by `idem.decisions` are `preserve_cobol`, `accept_java`, and `skip`. |

The diagnosis feature defines an additional `DiagnosisResult` in `idem/diagnose.py` with a single `explanation: str` field.

## 6. Deployment Strategy

### Current development and demo setup

The project context describes a WSL2 Ubuntu environment for Python, Streamlit, GnuCOBOL, and Java tooling, with Ollama running on the Windows host for GPU access. The app reads `OLLAMA_HOST` and `OLLAMA_MODEL` from the environment (and loads a root `.env` when present). Verification requires `cobc`, `javac`, and `java` to be installed and discoverable on the app process's `PATH`. The source repository does not currently define a Dockerfile, compose file, authentication, or a database.

### Enterprise on-premise packaging recommendation

For an enterprise deployment, package the Streamlit application and Python dependencies in a versioned, non-root container image. Install compatible GnuCOBOL and Java compiler/runtime packages in that image so `cobc`, `javac`, and `java` are available to the verifier. Deploy Ollama and approved model weights inside the customer's network, either as a separate managed service or a separate container; configure `OLLAMA_HOST` and `OLLAMA_MODEL` explicitly and do not expose the inference service publicly.

Mount durable, access-controlled storage for `samples/cached/` and reviewer decision JSON if cache reuse and decision audit trails must survive container replacement. Keep uploaded COBOL, generated Java, and cache data inside the customer's controlled environment; define retention, backup, access, and model-version policies before production use. A production deployment should also add ingress/TLS, user authentication and authorization, resource limits for compiler and model processes, health monitoring, and image/model vulnerability scanning. These are deployment recommendations, not features currently implemented by Idem.
