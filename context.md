# Idem — Project Context

> **Tagline:** Modernize legacy code. Prove it still works.

## 1. Summary
Idem is an AI-assisted tool that takes a legacy COBOL program and:
1. **Explains** it in plain English.
2. **Generates** equivalent Java 21 code.
3. **Verifies** the result by running both programs on the same inputs and comparing outputs byte-for-byte.
4. **Explains** divergences using an LLM and allows a human to accept or reject the fix.

The core differentiator is **trust**. We do not just translate code; we provide mathematical proof of equivalence, or show exactly where the legacy code is broken.

## 2. Architecture & Workflow
Streamlit UI -> Python Pipeline
1. `analyze(cobol_src)`: Extracts business rules, inputs, outputs, and risks.
2. `generate(cobol_src, analysis)`: Generates Java 21 + test cases. 
   - *Ironclad Guardrail*: Python sanitizes the output to enforce `Main.java` naming, inject missing imports, and fix common LLM hallucinations.
3. `verify(cobol_src, java_src, test_cases)`: 
   - Compiles COBOL using `cobc`.
   - Compiles Java using `javac`.
   - Runs both side-by-side via subprocess.
   - Normalizes stdout and compares byte-for-byte.
4. `diagnose(...)`: If there is a mismatch, the LLM explains why the COBOL and Java diverged.
5. *Human-in-the-Loop*: The user clicks "Accept Java behaviour", "Preserve COBOL", or "Skip".

## 3. Tech Stack
- **Language:** Python 3.11+
- **LLM:** Ollama (`qwen2.5-coder:7b`) running locally.
- **COBOL Compiler:** GnuCOBOL 3.2.0 (`cobc`).
- **Java Runtime:** OpenJDK 21 (`javac`, `java`).
- **UI:** Streamlit.
- **Validation:** Pydantic.

## 4. Verification Rules
- **Byte-exact match** on stdout after trailing-whitespace normalization.
- **Exit code must be zero.** A crash is not a match.
- **Timeout:** 30 seconds per run.
- **Padding:** Uses `String.format(Locale.ROOT, ...)` to match COBOL PIC clauses exactly (e.g., `9(7)V99` -> `%010.2f`).
- **Control Flow:** Every `DISPLAY` and `IF/ELSE` must be translated.

## 5. Environment
Runs natively inside WSL2 (Ubuntu). Requires Ollama running on the Windows host (mirrored networking) or locally.

## 6. What works
- 26/26 passing on the clean `loanint.cob` hero sample.
- Catches a 30-year-old string comparison bug in `student.cob`.
- UI displays side-by-side diffs, explains root causes, and logs human decisions.
- Zero API costs (fully local).