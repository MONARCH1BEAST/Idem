# Idem

> **Modernize legacy code. Prove it still works.**

Idem takes a legacy **COBOL** program, explains it in plain English, generates
equivalent **Java 21** code, and then **proves** the new code behaves identically
to the old by running both programs on the same inputs and comparing stdout
**byte-for-byte**.

Many tools can translate code with an LLM. Idem's pitch is **trust**: a human
reviewer sees evidence that the new code behaves like the old code — or sees
exactly where it does not.

---

## Why

Banks, insurers, and governments still run enormous amounts of COBOL. The
engineers who understand it are retiring. Rewrites are slow and risky because
nobody can easily prove the new system behaves like the old one.

Idem does not promise to write better code. It promises to prove the new code
is equivalent — or to show exactly where it diverges, and let a human decide.

---

## What it does

1. **Explain** — reads a COBOL program and produces a plain-English summary,
   inputs, outputs, and a structured list of business rules.
2. **Generate** — produces a single Java 21 class `Main` that reads stdin and
   writes stdout, using `BigDecimal` for every COBOL fixed-point numeric.
3. **Verify** — compiles the COBOL with `cobc`, compiles the Java with `javac`,
   runs both on the same test inputs, and compares stdout byte-for-byte.
4. **Repair** (optional) — if outputs mismatch, feeds the diff back to the LLM
   once and re-verifies.
5. **Review** (optional) — on a mismatch, a human chooses *preserve COBOL
   behaviour*, *accept Java behaviour*, or *skip*. Decisions are stored as an
   audit trail.
6. **Improve** (optional) — a mode where the LLM may deliberately diverge from
   COBOL to fix obvious bugs, documenting every change.

---

## Architecture

```
Streamlit UI (app.py)
    |
    v
[1] analyze(cobol_src)                       -> AnalysisResult
[2] generate(cobol_src, analysis)            -> GenerationResult (Java + tests)
[3] verify(cobol_src, java_src, test_cases)  -> VerificationReport
[4] repair(...) if mismatches, one attempt
    |
    v
Tabs: Explanation | Rules | Java | Tests | Verification
```

### Verification rules

- **Exact byte match** on stdout after normalizing line endings and trailing
  whitespace. No fuzzy matching.
- **Exit code must be zero.** A crash is not a match.
- **Stderr** is captured on every case.
- **Timeout** of 30 seconds per run, reported as a distinct failure.
- **No case is silently skipped.** Failures always carry a reason.
- **Post-condition:** `passed + failed == len(results)`.
- **Deterministic:** same input, same report.

### Test cases

Each run on a curated sample uses ~26 cases:

| Category | Count | Source |
|---|---|---|
| Semantic (typical, zero, rounding boundary, …) | 3–5 | LLM |
| Anchors (all-zero, all-one, all-mid, all-max-safe) | 4 | Deterministic |
| Single-axis sweeps | ~14 | Deterministic |
| Seeded random in safe range | 5 | Deterministic (seed 42) |

Uploaded files (not curated samples) use only the LLM's semantic cases.

---

## Requirements

All required software runs inside **WSL2 Ubuntu** except Ollama, which runs on
Windows for GPU access.

### Windows host

- WSL2 with mirrored networking
  (`C:\Users\<you>\.wslconfig` containing `[wsl2]` and `networkingMode=mirrored`)
- [Ollama](https://ollama.com/download) installed and running
- Model pulled: `ollama pull qwen2.5-coder:7b`

### WSL Ubuntu

- Python 3.11+ with `venv`
- GnuCOBOL 3.2+ (`cobc`)
- OpenJDK 21 (`javac`, `java`)
- Git

Install inside Ubuntu:

```bash
sudo apt update
sudo apt install -y gnucobol openjdk-21-jdk python3 python3-venv python3-pip git
```

Verify:

```bash
cobc --version      # cobc (GnuCOBOL) 3.x
javac --version     # javac 21.x
python3 --version   # Python 3.11+
```

---

## Setup

### 1. Enable mirrored networking (one-time, on Windows)

Create or edit `C:\Users\<you>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
```

Then in Windows PowerShell:

```powershell
wsl --shutdown
```

Wait 15 seconds, then reopen Ubuntu.

Verify inside Ubuntu:

```bash
wslinfo --networking-mode
# Expected: mirrored

curl http://localhost:11434/api/tags
# Expected: JSON listing your models
```

If `curl` fails, Ollama is not running on Windows. Start it from the Start
menu (or ensure the tray app is running).

### 2. Clone or copy the project

```bash
cd ~
git clone <your-repo-url> Idem
cd Idem
```

If you already have the project on Windows and want a fresh Linux copy:

```bash
mkdir ~/Idem
cd /mnt/c/Idem
for item in app.py idem run.py samples tests requirements.txt pytest.ini .env .gitignore; do
  cp -r "$item" ~/Idem/ 2>/dev/null
done
cd ~/Idem
```

### 3. Create the virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure `.env`

Copy `.env.example` to `.env` and confirm:

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
```

With mirrored networking, `localhost` inside WSL reaches Ollama on Windows.
If you are not using mirrored networking, replace `localhost` with the Windows
host IP (`ip route | grep default`).

---

## Running

### CLI pipeline

```bash
cd ~/Idem
source .venv/bin/activate
python run.py
```

Expected output ends with:

```
=== VERIFICATION: 26/26 passed ===
```

With Improve mode:

```bash
python run.py --improve
```

### Streamlit UI

```bash
cd ~/Idem
source .venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Open `http://localhost:8501` in your Windows browser.

The UI has two modes:

- **Sample** — run a curated program from `samples/`. Served from cache by
  default. Fast (seconds).
- **Upload** — upload a `.cob` file. Runs live against Ollama. Takes 1–3
  minutes.

### Tests

```bash
cd ~/Idem
source .venv/bin/activate
python -m pytest tests -q
```

---

## Demo

The hero demo is 90 seconds:

1. Open the UI. Sample mode, `loanint`. Click **Run pipeline**.
2. Wait ~8 seconds. **26 / 26 passed** appears.
3. Verification tab: scroll through the rows. Expand one to show
   byte-identical COBOL and Java output.
4. Switch to Upload mode. Upload `samples/student.cob`. Run.
5. Show the divergence: COBOL prints `Status: FAIL` for an average of 84.33;
   Java prints `Status: PASS`. **The COBOL is buggy. Idem caught it.**
6. Click **Accept Java behaviour**. The case shows a yellow
   ACCEPTED DIVERGENCE banner.
7. Close: *"We don't just translate code. We prove it still works. And when
   it doesn't, we show you exactly where."*

A backup video is in `demo/backup.mp4`.

---

## Project layout

```
Idem/
├── app.py                    Streamlit UI
├── run.py                    CLI pipeline
├── context.md                Full project context
├── README.md                 This file
├── requirements.txt
├── pytest.ini
├── .env.example
├── idem/
│   ├── analyze.py            LLM step 1: explanation + rules
│   ├── generate.py           LLM step 2: Java + tests
│   ├── verify.py             Compile, run, compare
│   ├── repair.py             Single-attempt repair loop
│   ├── testcases.py          Deterministic stress-case generator
│   ├── decisions.py          Reviewer decision persistence
│   ├── llm.py                Ollama wrapper + cache
│   ├── schemas.py            Pydantic models
│   └── prompts/
│       ├── analyze.txt
│       ├── generate.txt
│       ├── generate_improved.txt
│       └── repair.txt
├── samples/
│   ├── loanint/              Hero sample
│   ├── cached/               LLM response cache (gitignored by default)
│   └── <sample>/decisions.json
├── tests/
└── demo/
    ├── script.md
    └── backup.mp4
```

---

## I/O contract for COBOL samples

Both the COBOL program and the generated Java must read from stdin and write
to stdout.

- **Inputs:** one value per line. **Integers only** for `PIC 9(x)V99` fields —
  COBOL implies the decimal position from the PIC clause.
- **Outputs:** one `LABEL=value` pair per line, left-padded to the PIC width.

Example (`loanint`, `PIC 9(7)V99` outputs):

```
stdin:
10000
5
12

stdout:
INTEREST=0000500.00
TOTAL=0010500.00
```

For `PIC 9(N)V99`, the Java format string is `%0(N+3).2f` under
`Locale.ROOT`. Example: `9(7)V99` → `%010.2f`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cobc: command not found` | GnuCOBOL not installed in WSL | `sudo apt install gnucobol` |
| `javac: command not found` | JDK missing | `sudo apt install openjdk-21-jdk` |
| `WinError 10061` / connection refused | Ollama not running | Start Ollama on Windows; verify with `curl http://localhost:11434/api/tags` |
| LLM call hangs 60+ seconds | Model loading into RAM | Wait; subsequent calls are fast |
| Verification shows `<26/26` | Java has an edge case | Check the diff; let repair run; fix prompt |
| COBOL compile error `invalid symbol '0xd'` | CRLF line endings | Verify normalizes line endings; check source file |
| `ModuleNotFoundError` | venv not activated | `source .venv/bin/activate` |
| Port 8501 already in use | Another Streamlit running | `--server.port 8502` |
| VS Code shows 100+ Copilot errors | Microsoft extension validation | Ignore or filter with `!copilot` in the Problems panel |

---

## Environment checklist for demo day

```
[ ] Ollama running:  curl http://localhost:11434/api/tags
[ ] cobc --version   →  GnuCOBOL 3.x
[ ] javac --version  →  javac 21.x
[ ] cd ~/Idem && source .venv/bin/activate
[ ] python run.py    →  26/26 passed
[ ] streamlit run app.py --server.port 8501 --server.address 0.0.0.0
[ ] Browser opens http://localhost:8501
```

If any box fails, play `demo/backup.mp4` instead of the live demo.

---

## Scope

**In scope:** COBOL to Java 21, single self-contained programs, curated samples,
the pipeline above, a Streamlit UI, reviewer decisions, optional improve mode.

**Out of scope:** multi-program analysis, other target languages, a real COBOL
parser, agent frameworks, databases, authentication, cloud deployment,
CICS/DB2/VSAM/JCL.

---

## License

Prototype for PitchFest 2026. Not for production use.
