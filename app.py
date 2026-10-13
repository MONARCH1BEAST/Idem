from pathlib import Path

import streamlit as st

from idem.analyze import analyze
from idem.generate import generate

st.set_page_config(page_title="Idem", layout="wide")

st.title("Idem")
st.caption("Modernize legacy code. Prove it still works.")

SAMPLES = {
    "loanint": Path("samples/loanint/loanint.cob"),
    "latefee": Path("samples/latefee/latefee.cob"),
}

with st.sidebar:
    st.header("Run")
    sample_name = st.selectbox("Sample", list(SAMPLES.keys()))
    regenerate = st.checkbox("Regenerate (ignore cache)", value=False)
    run_clicked = st.button("Run pipeline", type="primary")


def _init_state():
    for k in ("analysis", "generation", "report", "error"):
        if k not in st.session_state:
            st.session_state[k] = None


_init_state()


if run_clicked:
    path = SAMPLES[sample_name]
    if not path.exists():
        st.error(f"Sample not found: {path}")
    else:
        cobol = path.read_text(encoding="utf-8")

        st.session_state.analysis = None
        st.session_state.generation = None
        st.session_state.report = None
        st.session_state.error = None

        with st.spinner("Analyzing..."):
            analysis, err = analyze(cobol, regenerate=regenerate)
        if err:
            st.session_state.error = f"analyze: {err}"
        else:
            st.session_state.analysis = analysis

            with st.spinner("Generating Java..."):
                generation, err = generate(cobol, analysis, regenerate=regenerate)
            if err:
                st.session_state.error = f"generate: {err}"
            else:
                st.session_state.generation = generation

                try:
                    from idem.verify import verify
                    with st.spinner("Verifying..."):
                        st.session_state.report = verify(
                            cobol,
                            generation.java_source,
                            generation.test_cases,
                        )
                except ImportError:
                    st.session_state.report = None


if st.session_state.error:
    st.error(st.session_state.error)

tab_explain, tab_rules, tab_java, tab_tests, tab_verify = st.tabs(
    ["Explanation", "Rules", "Java", "Tests", "Verification"]
)

analysis = st.session_state.analysis
generation = st.session_state.generation
report = st.session_state.report

with tab_explain:
    if not analysis:
        st.info("Run the pipeline to see the explanation.")
    else:
        st.subheader("Summary")
        st.write(analysis.summary)
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Inputs")
            for i in analysis.inputs:
                st.write(f"- {i}")
        with col2:
            st.subheader("Outputs")
            for o in analysis.outputs:
                st.write(f"- {o}")
        if analysis.risks:
            st.subheader("Risks")
            for r in analysis.risks:
                st.warning(r)

with tab_rules:
    if not analysis:
        st.info("Run the pipeline to see the business rules.")
    else:
        st.table([
            {
                "ID": r.id,
                "Description": r.description,
                "Lines": r.cobol_lines,
                "Confidence": f"{r.confidence:.2f}",
            }
            for r in analysis.business_rules
        ])

with tab_java:
    if not generation:
        st.info("Run the pipeline to see the generated Java.")
    else:
        st.code(generation.java_source, language="java")
        if generation.notes:
            st.subheader("Notes")
            for n in generation.notes:
                st.write(f"- {n}")

with tab_tests:
    if not generation:
        st.info("Run the pipeline to see the test cases.")
    else:
        for tc in generation.test_cases:
            with st.expander(tc.name):
                st.code(tc.stdin, language="text")

with tab_verify:
    if not report:
        st.info("Verification not available yet (verify.py missing or not run).")
    else:
        st.subheader(f"{report.passed} / {len(report.results)} passed")
        for result in report.results:
            with st.container():
                status_col, name_col = st.columns([1, 5])
                with status_col:
                    if result.match:
                        st.success("✅ Match")
                    else:
                        st.error("❌ Mismatch")
                with name_col:
                    st.subheader(result.name)

                cobol_col, java_col = st.columns(2)
                with cobol_col:
                    st.markdown("**COBOL stdout**")
                    st.code(result.cobol_output or "(empty)", language="text")
                with java_col:
                    st.markdown("**Java stdout**")
                    st.code(result.java_output or "(empty)", language="text")

                if result.reason:
                    st.warning(f"Reason: {result.reason}")
                if result.stderr:
                    with st.expander("stderr"):
                        st.code(result.stderr, language="text")