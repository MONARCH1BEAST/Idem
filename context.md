# Idem — Person B Context

> **Role:** Intelligence & Interface
> **Owns:** the LLM layer, the prompts, the pipeline steps (`analyze`, `generate`), the UI, and the demo artifacts.
> **Does not own:** the COBOL/Java runtime harness, the samples, `verify.py`, `repair.py`, Docker.

This file is your single source of truth. Read `context.md` first, then this. If they conflict, `context.md` wins for project-wide rules; this file wins for your scope.

---

## 1. Your mission in one sentence

> Turn a COBOL program into **validated JSON** (analysis, then generation), then show it to a human — reliably, from cache, without crashing the UI.

You are not responsible for whether the generated Java *runs correctly*. That is Person A's job in `verify.py`. You are responsible for making sure the LLM returns **well-formed, Pydantic-valid, schema-correct output every time**, and that the human can see and trust it.

---

## 2. The frozen contract (lock this on Day 1 with Person A)

You and A must agree on these three things before either of you writes code. Do not skip this.

### 2.1 The stdin/stdout contract

Both the COBOL program and the generated Java must obey this exactly.

**Input:** one value per line, in the order documented in each sample's `notes.md`.

**Output:** one `LABEL=value` pair per line.

- `LABEL` is uppercase, no spaces, matches `notes.md`.
- `value` has a **fixed number of decimal places**, matching the `PIC` clause.
- No extra text. No blank lines. No headers.

**Example (`loanint`):**
```
PRINCIPAL=10000.00
RATE=5.25
TERM=36
---
INTEREST=165.63
TOTAL=10165.63
```

**Comparison rule:** exact string match after trimming trailing whitespace on each line and trailing newlines at the end.

You must encode this contract into your **generation prompt** so the LLM produces Java that obeys it.

### 2.2 `idem/schemas.py` — frozen Day 1

Copy verbatim from `context.md` §9. You own the file. Once frozen, **you do not change it without telling A**, because A's `verify.py` and `repair.py` depend on these shapes.

```python
from pydantic import BaseModel, Field

class BusinessRule(BaseModel):
    id: str
    description: str
    cobol_lines: str
    confidence: float = Field(ge=0.0, le=1.0)

class AnalysisResult(BaseModel):
    summary: str
    inputs: list[str]
    outputs: list[str]
    business_rules: list[BusinessRule]
    risks: list[str]

class TestCase(BaseModel):
    name: str
    stdin: str

class GenerationResult(BaseModel):
    java_source: str
    test_cases: list[TestCase]
    notes: list[str]

class CaseResult(BaseModel):
    name: str
    cobol_output: str
    java_output: str
    match: bool

class VerificationReport(BaseModel):
    results: list[CaseResult]
    passed: int
    failed: int
```

### 2.3 The cache format

Every LLM call is cached to `samples/cached/`. A depends on this being deterministic so the live demo runs offline. You define the format; A reads it indirectly through your `llm.py`.

**Cache key:** `sha256(prompt_template_name + model + str(temperature) + input_text)` → first 16 hex chars.

**File name:** `samples/cached/{key}.json`

**File contents:**
```json
{
  "key": "a1b2c3d4e5f6a7b8",
  "prompt_name": "analyze",
  "model": "claude-sonnet-4-5",
  "temperature": 0.0,
  "input_hash": "sha256-of-input-text",
  "created_at": "2026-10-12T14:33:00Z",
  "raw_response": "...",
  "parsed": { ... }
}
```

`parsed` is the Pydantic `.model_dump()` if parsing succeeded, else `null`. This lets you replay a cache entry even if the raw response was malformed.

---

## 3. Repository structure — your files marked

```
idem/
├── context.md                       # shared, read-only for you
├── B_CONTEXT.md                     # this file
├── README.md                        # A writes setup, you write usage
├── requirements.txt                 # you own
├── .env.example                     # you own (never commit .env)
├── .gitignore                       # you own (.env, __pycache__, samples/cached/*.tmp)
├── app.py                           # YOU — Streamlit UI
├── run.py                           # YOU — plain pipeline runner (no UI)
├── idem/
│   ├── __init__.py                  # you
│   ├── schemas.py                   # YOU — frozen Day 1
│   ├── llm.py                       # YOU — API wrapper + cache
│   ├── analyze.py                   # YOU
│   ├── generate.py                  # YOU
│   ├── verify.py                    # A (read only)
│   ├── repair.py                    # A (read only; you write its prompt)
│   └── prompts/
│       ├── analyze.txt              # YOU
│       ├── generate.txt             # YOU
│       └── repair.txt               # YOU (prompt only; A wires it)
├── samples/
│   ├── loanint/
│   │   ├── loanint.cob              # A
│   │   └── notes.md                 # A (you read it for the prompt)
│   ├── latefee/                     # A (optional)
│   └── cached/                      # YOU manage
│       └── *.json
├── tests/
│   ├── test_llm_cache.py            # YOU
│   ├── test_schemas.py              # YOU
│   └── test_pipeline.py             # YOU (integration, no verify)
├── scripts/
│   └── setup.sh                     # A
└── demo/
    ├── script.md                    # YOU
    └── backup.mp4                   # YOU
```

**Files you must never edit:** `verify.py`, `repair.py`, `samples/*.cob`, `scripts/setup.sh`, `Dockerfile`.
If you need a change in those, ask A.

---

## 4. File-by-file specification

### 4.1 `requirements.txt`

```
pydantic>=2.6
python-dotenv>=1.0
streamlit>=1.35
httpx>=0.27
# plus your chosen LLM SDK, e.g.:
anthropic>=0.40
# or openai>=1.40
# or google-generativeai>=0.8
pytest>=8.0
```

Pin nothing else. Keep it lean.

### 4.2 `.env.example`

```
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-...
LLM_MODEL=claude-sonnet-4-5
LLM_TEMPERATURE=0.0
```

`.env` is gitignored. `.env.example` is committed.

### 4.3 `idem/schemas.py`

Exactly as in §2.2. Nothing else in this file. No helper functions, no imports beyond `pydantic`.

### 4.4 `idem/llm.py`

The thin wrapper. This is the most important file you own, because everything flows through it.

**Responsibilities:**
1. Load `.env` once.
2. Accept a `prompt_name`, an `input_text`, and optional overrides.
3. Compute the cache key.
4. If `samples/cached/{key}.json` exists and `regenerate=False`, return the parsed result.
5. Otherwise call the provider, store the response, return the parsed result.
6. Never raise on parse failure in a way that crashes the UI — return a clear error object.

**Public API:**

```python
def call_llm(
    prompt_name: str,          # "analyze" | "generate" | "repair"
    input_text: str,           # the full rendered prompt body
    schema: type[BaseModel],   # AnalysisResult | GenerationResult | ...
    regenerate: bool = False,
    retries: int = 1,
) -> tuple[BaseModel | None, str | None]:
    """
    Returns (parsed_result, error_message).
    On success: (model_instance, None).
    On failure after retries: (None, "human-readable error").
    """
```

**Internals:**

- Load `prompts/{prompt_name}.txt` as the system prompt. The `input_text` is the user message.
- Use JSON mode / structured output if the provider supports it. Otherwise ask for JSON only and extract the first `{...}` block.
- Validate with `schema.model_validate_json(raw)`.
- On `ValidationError`, retry once with a corrective message appended: `"Your previous response failed validation: {error}. Return only valid JSON matching the schema."`
- Write the cache file **before** returning, so even a retry attempt is cached under its own key.
- Log to stderr, not stdout (stdout is for the UI/pipeline).

**Cache key function:**

```python
def _cache_key(prompt_name: str, model: str, temperature: float, input_text: str) -> str:
    h = hashlib.sha256()
    h.update(prompt_name.encode())
    h.update(model.encode())
    h.update(str(temperature).encode())
    h.update(input_text.encode())
    return h.hexdigest()[:16]
```

**Provider abstraction:** keep it to one `_call_provider(system, user)` function. Do not build a plugin system. One provider, decided by team credits.

### 4.5 `idem/analyze.py`

```python
def analyze(cobol_src: str, regenerate: bool = False) -> tuple[AnalysisResult | None, str | None]:
    prompt = render_prompt("analyze", cobol_src)
    return call_llm("analyze", prompt, AnalysisResult, regenerate=regenerate)
```

`render_prompt` is a tiny helper in `llm.py` that substitutes `{COBOL_SOURCE}` into the template. Nothing more.

### 4.6 `idem/generate.py`

```python
def generate(
    cobol_src: str,
    analysis: AnalysisResult,
    regenerate: bool = False,
) -> tuple[GenerationResult | None, str | None]:
    prompt = render_prompt(
        "generate",
        cobol_src,
        analysis_json=analysis.model_dump_json(indent=2),
    )
    return call_llm("generate", prompt, GenerationResult, regenerate=regenerate)
```

### 4.7 `idem/prompts/analyze.txt`

Draft — tune it, don't rewrite from scratch:

```
You are a senior engineer analyzing legacy COBOL for a modernization project.

Read the COBOL program below and return a single JSON object with these fields:

- "summary": 2-4 sentences in plain English. What does this program do?
- "inputs": list of input fields, in the order the program reads them.
- "outputs": list of output labels, exactly as printed.
- "business_rules": list of objects, each with:
    - "id": "R1", "R2", ...
    - "description": one plain-English sentence.
    - "cobol_lines": the line range, e.g. "42-48".
    - "confidence": float 0.0-1.0.
- "risks": list of strings. Flag any of:
    - COMP-3 packed decimal fields
    - implicit rounding (COMPUTE or MOVE without ROUNDED)
    - signed fields (PIC S9...)
    - potential overflow (missing ON SIZE ERROR)
    - any construct whose Java equivalent is non-obvious

Rules:
- Output JSON only. No prose before or after.
- Do not invent behavior. If something is ambiguous, say so in "risks".
- Do not include the COBOL source in your response.

COBOL program:
---
{COBOL_SOURCE}
---
```

### 4.8 `idem/prompts/generate.txt`

Draft:

```
You are a senior Java engineer. Translate the COBOL program below into a single
Java 21 class named `Main` that behaves identically.

I/O CONTRACT (must be obeyed exactly):
- Read input from stdin, one value per line, in this order: {input_order}
- Print output to stdout, one `LABEL=value` pair per line.
- Labels and decimal places must match exactly: {output_format}
- No extra text, no blank lines, no headers.

ARITHMETIC RULES (must be obeyed exactly):
- Every numeric field that is a COBOL fixed-point type (PIC 9..., COMP-3)
  MUST be a `java.math.BigDecimal`. Never use double or float.
- COBOL ROUNDED maps to RoundingMode.HALF_UP.
- A COMPUTE or MOVE without ROUNDED truncates: use RoundingMode.DOWN.
- Set scale explicitly to match the PIC clause.
- Preserve signed fields (PIC S9...); handle negative inputs.
- Note: COBOL silently truncates high-order digits on overflow unless
  ON SIZE ERROR is present. Match that behavior.

ALSO RETURN:
- "test_cases": list of objects with "name" and "stdin". Include at least:
    - one typical case
    - zero
    - a negative value (if signed fields exist)
    - a maximum-value boundary
    - a rounding boundary (e.g. x.xx5)
- "notes": list of strings. Anything a human reviewer should know.

Use this analysis as your guide:
---
{ANALYSIS_JSON}
---

COBOL program:
---
{COBOL_SOURCE}
---

Output JSON only. No prose before or after.
```

### 4.9 `idem/prompts/repair.txt`

You write it, A consumes it. Draft:

```
The generated Java does not match the COBOL output for one or more test cases.

COBOL program:
---
{COBOL_SOURCE}
---

Current Java:
---
{JAVA_SOURCE}
---

Mismatches:
---
{DIFF_JSON}
---

Return a corrected Java source (single class `Main`, same I/O contract and
arithmetic rules as before) plus updated test cases and notes. Output JSON only.
```

### 4.10 `run.py`

The no-UI pipeline. This is what you demo if Streamlit is cut.

```python
def run_pipeline(sample_dir: Path, regenerate: bool = False) -> dict:
    cobol = (sample_dir / "loanint.cob").read_text()
    analysis, err = analyze(cobol, regenerate=regenerate)
    if err:
        return {"stage": "analyze", "error": err}
    generation, err = generate(cobol, analysis, regenerate=regenerate)
    if err:
        return {"stage": "generate", "error": err}
    # hand off to A's verify.py
    from idem.verify import verify
    report = verify(cobol, generation.java_source, generation.test_cases)
    return {"analysis": analysis, "generation": generation, "report": report}
```

`verify.py` is A's API. Agree on its signature on Day 1:

```python
def verify(
    cobol_src: str,
    java_src: str,
    test_cases: list[TestCase],
) -> VerificationReport: ...
```

### 4.11 `app.py` (Streamlit)

**Layout:**

```
┌─────────────────────────────────────────────────────┐
│ Idem — Modernize legacy code. Prove it still works. │
├─────────────────────────────────────────────────────┤
│ Sidebar:  [ Sample ▼ ]  [ ] Regenerate  [ Run ]     │
├─────────────────────────────────────────────────────┤
│ Tabs:                                               │
│  Explanation | Rules | Java | Tests | Verification  │
└─────────────────────────────────────────────────────┘
```

**Behavior:**

- Default sample: `loanint`.
- Default `Regenerate` = **off**. The demo runs from cache.
- `Run` triggers the pipeline. Show a spinner per stage.
- **Explanation tab:** summary, inputs, outputs, risks.
- **Rules tab:** table of `BusinessRule` — id, description, lines, confidence.
- **Java tab:** syntax-highlighted `java_source` in a code block. Copy button.
- **Tests tab:** expandable list of test cases, showing `name` and `stdin`.
- **Verification tab:** table of `CaseResult` — name, match (✅/❌), COBOL output, Java output. Header shows `passed / total`.
- **Error handling:** if any stage returns an error, show a red `st.error` with the message. Never let an exception reach Streamlit's default handler.

**Session state:** store the last `analysis`, `generation`, `report` in `st.session_state` so tab switches don't re-run the pipeline.

### 4.12 `tests/`

Three files, fast, no network:

- `test_schemas.py` — construct each model from a known-good dict, assert fields.
- `test_llm_cache.py` — call `call_llm` twice with the same input; assert the second call does not hit the provider (mock the provider and assert call count == 1).
- `test_pipeline.py` — run `analyze` + `generate` against a **fake** cached response; assert the objects parse. Do not touch `verify`.

---

## 5. Day-by-day plan for Person B

| Day | Task |
|---|---|
| **Fri 9 Oct** | Install Python 3.11+, create venv, `pip install -r requirements.txt`. Get API key + credits. Send A a test message on the provider. |
| **Sat 10 Oct** | **With A:** freeze §2 contract and `schemas.py`. Commit. |
| **Sun 11 Oct** | Write `llm.py`. Get one `call_llm("analyze", ...)` call to succeed and write a cache file. |
| **Mon 12 Oct** | Write `analyze.txt`. Tune until `AnalysisResult` parses cleanly on `loanint.cob`. |
| **Tue 13 Oct** | Write `generate.txt`. Tune until `GenerationResult` parses cleanly. |
| **Wed 14 Oct** | Write `run.py`. Wire `analyze` → `generate`. Hand the Java to A's `verify.py`. |
| **Thu 15 Oct** | First end-to-end run with A. Fix integration bugs. Cache the hero output. |
| **Fri 16 – Mon 19 Oct** | Tune prompts against real mismatches A finds. Write `repair.txt`. Get one repair-loop success into the cache. |
| **Tue 20 Oct** | **Feature freeze.** Build `app.py`. |
| **Wed 21 Oct** | Polish UI. Cache all demo outputs. Write `demo/script.md`. |
| **Thu 22 Oct** | Record `demo/backup.mp4`. Rehearse twice. |
| **Fri 23 Oct** | Final rehearsal. Q&A prep on the product/market side. |
| **Sat 24 Oct** | PitchFest. |

---

## 6. Rules you must follow (from `context.md` §10, filtered to your scope)

1. **Validate every LLM response with Pydantic.** Retry once. Never crash the UI.
2. **Cache every LLM response.** The live demo runs from cache by default.
3. **Prompts live in `idem/prompts/`.** Never inline them in `.py` files.
4. **Temperature 0.0–0.2.** Determinism matters.
5. **Never send real client code to the LLM.** Only the synthetic samples.
6. **Keep functions small and plain.** No LangChain, no agent frameworks, no ORMs.

---

## 7. What "done" looks like for you (Oct 20)

- [ ] `schemas.py` frozen and unchanged since Day 1.
- [ ] `llm.py` caches every call to `samples/cached/` with the format in §2.3.
- [ ] `analyze` returns a valid `AnalysisResult` for `loanint` from cache in under 1 second.
- [ ] `generate` returns a valid `GenerationResult` for `loanint` from cache in under 1 second.
- [ ] `run.py` executes analyze → generate → verify end to end from cache with **no internet**.
- [ ] `app.py` shows all five tabs and renders the cached hero run without errors.
- [ ] `pytest` passes offline.
- [ ] `demo/script.md` written, `demo/backup.mp4` recorded.

---

## 8. Do's and don'ts

**Do:**
- Ask A to change `verify.py`'s signature *before* you build against it.
- Keep the cache directory clean — one JSON per call, no temp files left behind.
- Test the "no internet" path at least once a week.
- Log errors to stderr, not stdout.

**Don't:**
- Don't edit `verify.py`, `repair.py`, or any `.cob` file.
- Don't change `schemas.py` without telling A.
- Don't add a second LLM provider "just in case."
- Don't build a settings page, auth, or a database.
- Don't let the demo depend on a live API call.

---

## 9. The one thing that matters most

> **The cache.** If every demo output is cached and the pipeline can run offline, you can survive almost any failure on pitch day. If it can't, one bad Wi-Fi connection kills the demo.

Build the cache first. Trust it completely. Everything else is secondary.