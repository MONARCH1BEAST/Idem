# Idem

**Modernize legacy code. Prove it still works.**

Idem analyzes a COBOL program, generates a Java 21 translation, and compares
the two programs by compiling and running both against the same test inputs.
The Streamlit UI shows the analysis, generated Java, test cases, and any
verification differences so a reviewer can inspect and decide what to do.

> Idem is a prototype, not a production migration tool. Verification gives
> evidence for the tested inputs; it does not prove equivalence for every
> possible input.

## What it does

1. **Analyze:** Ask a local Ollama model for a structured explanation, inputs,
   outputs, business rules, and source-specific risks.
2. **Generate:** Produce a Java `Main` class and semantic test cases. Improve
   Mode allows intentional changes to obvious COBOL bugs and asks the model to
   document those changes.
3. **Verify:** Compile the COBOL with GnuCOBOL and the Java with `javac`, then
   run both with the same stdin and compare normalized stdout.
4. **Repair (optional):** Ask the model for one correction when there are
   repairable mismatches. The UI's **Disable repair loop (faster demo)**
   checkbox is enabled by default.
5. **Review:** Inspect divergent outputs, optionally ask the model to explain
   a mismatch, then record a decision to preserve COBOL behavior, accept Java
   behavior, or skip that case.

## Requirements

- Python 3.11 or newer
- Java Development Kit 21 (`javac` and `java`)
- GnuCOBOL (`cobc`)
- Ollama, with a model available locally (default: `qwen2.5-coder:7b`)

The Python dependencies are listed in [requirements.txt](./requirements.txt):
Pydantic, python-dotenv, Streamlit, and pytest.

### WSL2 setup

The project is commonly run in WSL2 Ubuntu, with Ollama running on the Windows
host. Install Python, Java, GnuCOBOL, and Git using your distribution's
packages. For Ubuntu, for example:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip gnucobol openjdk-21-jdk git
```

Check that the tools are on `PATH`:

```bash
python3 --version
cobc --version
javac --version
java --version
```

Install [Ollama](https://ollama.com/) and pull the default model:

```bash
ollama pull qwen2.5-coder:7b
```

Make sure the Ollama service is running and reachable from the environment
where Idem runs.

## Installation

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

The default `.env` values are:

```dotenv
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

`OLLAMA_HOST` is the Ollama HTTP endpoint and `OLLAMA_MODEL` selects the model.
If Ollama runs on a different host or port, update `OLLAMA_HOST` accordingly.
Do not commit private environment configuration.

## Run the application

### Streamlit UI

```bash
source .venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Open [http://localhost:8501](http://localhost:8501).

In the sidebar, choose **Sample** or **Upload COBOL file**, then select
Improve Mode or the repair-loop setting as needed and click **Run pipeline**.
The UI has five tabs:

- **Explanation:** summary, inputs, outputs, and risks.
- **Rules:** extracted business rules and confidence.
- **Java:** generated Java, notes, and a source download.
- **Tests:** semantic and, for supported samples, deterministic stress cases.
- **Verification:** per-case results and outputs, mismatch diagnosis, and
  reviewer decisions.

Sample runs default to using cached LLM results when matching cache entries
are available. The **Regenerate (ignore cache)** option requests fresh analysis
and generation. Uploaded files run with cache regeneration enabled.

### Command-line pipeline

Run the default `loanint` sample:

```bash
source .venv/bin/activate
python run.py
```

Run another COBOL source file:

```bash
python run.py path/to/program.cob
```

Enable Improve Mode:

```bash
python run.py --improve
```

The CLI prints analysis and verification summaries. It performs one repair
attempt when repairable cases remain. Its stress-case generation is currently
configured for `loanint`.

## Tests

With the virtual environment activated:

```bash
python -m pytest tests -q
```

## Verification behavior

`idem.verify.verify` compiles each source once in a temporary directory, then
executes both programs sequentially for every test case, supplying identical
UTF-8 stdin. Each subprocess has a 30-second timeout. Temporary build files
are removed when verification finishes.

Stdout comparison normalizes CRLF to LF, strips trailing whitespace from each
line, and removes trailing newline characters. Leading whitespace and internal
line breaks are preserved. A case passes only if both executions exit
successfully and their normalized stdout matches. Stderr is captured for
diagnostics, but non-empty stderr alone does not fail a case.

The `loanint` UI run combines model-generated semantic cases with deterministic
stress cases. Other uploads receive model-generated semantic cases only unless
their sample key is supported by `idem.testcases`.

## LLM calls, cache, and privacy

Idem calls Ollama's local `/api/chat` endpoint using a JSON schema derived from
the requested Pydantic model. Responses are validated before use. The model,
temperature, prompt name, and rendered prompt content determine a cache key;
entries are stored as JSON in `samples/cached/`. A matching valid entry can be
reused without an inference call. Regeneration bypasses cache reads.

Analysis, generation, repair, and mismatch diagnosis send source code and
related prompt data to the configured Ollama endpoint. Use only an endpoint
approved for the source data you provide; local execution does not by itself
provide access control, encryption policy, or data-retention guarantees.

## Project layout

```text
.
├── app.py                    Streamlit user interface and pipeline
├── run.py                    Command-line pipeline
├── requirements.txt          Python dependencies
├── .env.example              Ollama configuration example
├── context.md                Project scope and development context
├── TECH_SPEC.md              Detailed technical specification
├── idem/
│   ├── analyze.py            Analysis step
│   ├── generate.py           Java generation step
│   ├── diagnose.py           Mismatch explanation
│   ├── repair.py             One-attempt repair loop
│   ├── verify.py             COBOL/Java compile and comparison harness
│   ├── decisions.py          Reviewer decision persistence
│   ├── testcases.py          Deterministic stress cases
│   ├── llm.py                Ollama HTTP wrapper and response cache
│   ├── schemas.py            Pydantic data models
│   └── prompts/              LLM prompt templates
├── samples/
│   ├── loanint/              Curated sample program and Java
│   └── cached/               LLM response cache
└── tests/                    Pytest suite
```

Reviewer decisions are stored under `samples/<sample_key>/decisions.json`.

## Limitations

- Verification covers only the supplied semantic and stress-test inputs; it is
  not a formal proof of program equivalence.
- The supported examples and deterministic stress-case specifications are
  limited. The current stress-case generator defines `loanint`.
- The app has no built-in user authentication, authorization, database, or
  deployment container configuration.
- Generated Java and Improve Mode output require human review before use.

For implementation details, see [TECH_SPEC.md](./TECH_SPEC.md).
