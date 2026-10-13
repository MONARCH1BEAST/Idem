"""Idem — Streamlit UI.

Run with:
    streamlit run app.py

Flow:
    analyze -> generate -> verify -> (optional repair)

By default, LLM calls are served from cache (samples/cached/). The demo is
fast and offline-capable. Tick "Regenerate" to force fresh LLM calls.

Verification always runs live: it compiles the COBOL with cobc, compiles
the generated Java with javac, and compares stdout byte-for-byte.
"""

from pathlib import Path

import streamlit as st

from idem.analyze import analyze
from idem.generate import generate
from idem.repair import repair
from idem.testcases import generate_stress_cases
from idem.verify import verify


# ----------------------------------------------------------------- config

st.set_page_config(page_title="Idem", page_icon="✓", layout="wide")

SAMPLES: dict[str, Path] = {
    "loanint": Path("samples/loanint/loanint.cob"),
}


# ----------------------------------------------------------------- state

if "result" not in st.session_state:
    st.session_state.result = None


# ----------------------------------------------------------------- header

st.title("Idem")
st.caption("Modernize legacy code. Prove it still works.")


# ----------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Run")
    sample_name = st.selectbox("Sample program", list(SAMPLES.keys()))
    regenerate = st.checkbox(
        "Regenerate (ignore cache)",
        value=False,
        help="Off by default. The demo runs from cache for speed and offline use.",
    )
    run_clicked = st.button(
        "▶  Run pipeline", type="primary", use_container_width=True
    )

    st.divider()
    st.markdown(
        "**Pipeline**\n\n"
        "1. Analyze COBOL\n"
        "2. Generate Java\n"
        "3. Verify side-by-side\n"
        "4. Repair once if needed\n\n"
        "**Verification**\n\n"
        "Compiles COBOL with `cobc`, Java with `javac`, runs both on the same "
        "stdin, compares stdout byte-for-byte."
    )


# ----------------------------------------------------------------- run

def _run_pipeline(sample_path: Path, regenerate: bool) -> dict | None:
    """Run analyze -> generate -> verify -> repair. Return a result dict."""
    if not sample_path.exists():
        st.error(f"Sample not found: `{sample_path}`")
        return None

    cobol = sample_path.read_text(encoding="utf-8")

    with st.status("Running pipeline…", expanded=True) as status:
        st.write("**1 / 4**  Analyzing COBOL…")
        analysis, err = analyze(cobol, regenerate=regenerate)
        if err:
            status.update(label="Analyze failed", state="error")
            st.error(f"**analyze:** {err}")
            return None

        st.write("**2 / 4**  Generating Java…")
        generation, err = generate(cobol, analysis, regenerate=regenerate)
        if err:
            status.update(label="Generate failed", state="error")
            st.error(f"**generate:** {err}")
            return None

        stress = generate_stress_cases(sample_path.stem)
        all_cases = list(generation.test_cases) + stress
        st.write(
            f"**3 / 4**  Verifying {len(all_cases)} cases "
            f"({len(generation.test_cases)} semantic + {len(stress)} stress)…"
        )
        report = verify(cobol, generation.java_source, all_cases)

        if report.failed > 0:
            st.write(f"**4 / 4**  {report.failed} mismatch(es) — attempting repair…")
            repaired, rerr = repair(
                cobol,
                generation.java_source,
                all_cases,
                report,
                regenerate=regenerate,
            )
            if rerr:
                st.warning(f"Repair failed: {rerr}")
            elif repaired:
                generation = repaired
                st.write("Re-verifying after repair…")
                report = verify(cobol, repaired.java_source, all_cases)

        status.update(
            label=f"Done — {report.passed} / {len(report.results)} passed",
            state="complete",
        )

    return {
        "analysis": analysis,
        "generation": generation,
        "report": report,
        "all_cases": all_cases,
    }


if run_clicked:
    st.session_state.result = _run_pipeline(SAMPLES[sample_name], regenerate)


# ----------------------------------------------------------------- tabs

result = st.session_state.result

tab_exp, tab_rules, tab_java, tab_tests, tab_verify = st.tabs(
    ["Explanation", "Rules", "Java", "Tests", "Verification"]
)


# --- Explanation ----------------------------------------------------------

with tab_exp:
    if not result:
        st.info("Click **▶ Run pipeline** in the sidebar to start.")
    else:
        a = result["analysis"]
        st.subheader("Summary")
        st.write(a.summary)

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Inputs")
            for i in a.inputs:
                st.markdown(f"- {i}")
        with col2:
            st.subheader("Outputs")
            for o in a.outputs:
                st.markdown(f"- {o}")

        if a.risks:
            st.subheader("Risks")
            for r in a.risks:
                st.warning(r)


# --- Rules ----------------------------------------------------------------

with tab_rules:
    if not result:
        st.info("Click **▶ Run pipeline** in the sidebar to start.")
    else:
        rules = result["analysis"].business_rules
        if not rules:
            st.write("No business rules extracted.")
        else:
            st.dataframe(
                [
                    {
                        "ID": r.id,
                        "Description": r.description,
                        "COBOL lines": r.cobol_lines,
                        "Confidence": round(r.confidence, 2),
                    }
                    for r in rules
                ],
                use_container_width=True,
                hide_index=True,
            )


# --- Java -----------------------------------------------------------------

with tab_java:
    if not result:
        st.info("Click **▶ Run pipeline** in the sidebar to start.")
    else:
        g = result["generation"]
        st.code(g.java_source, language="java")
        if g.notes:
            st.subheader("Notes")
            for n in g.notes:
                st.markdown(f"- {n}")


# --- Tests ----------------------------------------------------------------

with tab_tests:
    if not result:
        st.info("Click **▶ Run pipeline** in the sidebar to start.")
    else:
        all_cases = result["all_cases"]
        n_semantic = len(result["generation"].test_cases)
        n_stress = len(all_cases) - n_semantic
        st.caption(
            f"{n_semantic} semantic (LLM-generated) + "
            f"{n_stress} stress (deterministic) = "
            f"{len(all_cases)} total"
        )
        for tc in all_cases:
            with st.expander(tc.name):
                st.code(tc.stdin, language="text")


# --- Verification ---------------------------------------------------------

with tab_verify:
    if not result:
        st.info("Click **▶ Run pipeline** in the sidebar to start.")
    else:
        report = result["report"]
        all_cases = result["all_cases"]
        stdin_by_name = {tc.name: tc.stdin for tc in all_cases}
        total = len(report.results)

        if report.failed == 0:
            st.success(f"###  ✓  {report.passed} / {total} passed")
        else:
            st.error(
                f"###  {report.passed} / {total} passed  —  {report.failed} failed"
            )

        st.caption(
            "Each case runs the original COBOL and the generated Java on the "
            "same stdin. Stdout must match byte-for-byte."
        )

        # Compact summary table
        st.dataframe(
            [
                {
                    "Case": c.name,
                    "stdin": stdin_by_name.get(c.name, "").strip().replace("\n", " · "),
                    "Match": "✓" if c.match else "✗",
                    "Reason": c.reason or "",
                }
                for c in report.results
            ],
            use_container_width=True,
            hide_index=True,
        )

        # Side-by-side detail per case
        st.subheader("Case details")
        expand_all = st.checkbox("Expand all outputs", value=False)

        for c in report.results:
            icon = "✓" if c.match else "✗"
            label = f"{icon}  {c.name}"
            with st.expander(label, expanded=expand_all or not c.match):
                col1, col2 = st.columns(2)
                with col1:
                    st.caption("COBOL output")
                    st.code(c.cobol_output, language="text")
                with col2:
                    st.caption("Java output")
                    st.code(c.java_output, language="text")

                stdin = stdin_by_name.get(c.name, "")
                st.caption("stdin:  `" + stdin.strip().replace("\n", " | ") + "`")

                if c.stderr:
                    st.caption(f"stderr: {c.stderr}")
                if not c.match and c.reason:
                    st.error(f"Reason: {c.reason}")