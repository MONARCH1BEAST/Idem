"""Idem — Streamlit UI.

Run with:
    streamlit run app.py

Two modes:
    - Sample: uses a curated program from samples/. Cached LLM output.
    - Upload: user provides a .cob file. Fresh LLM call. Downloadable Java.

Verification always runs live: compiles COBOL with cobc, compiles the
generated Java with javac, compares stdout byte-for-byte.
"""

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from idem.analyze import analyze
from idem.decisions import clear_decision, save_decision
from idem.generate import generate
from idem.repair import repair
from idem.schemas import DivergenceDecision
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
if "upload_token" not in st.session_state:
    st.session_state.upload_token = None


# ----------------------------------------------------------------- header

st.title("Idem")
st.caption("Modernize legacy code. Prove it still works.")


# ----------------------------------------------------------------- sidebar

with st.sidebar:
    st.header("Run")
    improve_mode = st.checkbox(
        "Improve mode (fix obvious COBOL bugs)",
        value=False,
    )

    source_mode = st.radio(
        "Source",
        ["Sample", "Upload COBOL file"],
        horizontal=False,
        label_visibility="collapsed",
    )

    uploaded_file = None
    sample_name = None

    if source_mode == "Sample":
        sample_name = st.selectbox("Sample program", list(SAMPLES.keys()))
        regenerate = st.checkbox(
            "Regenerate (ignore cache)",
            value=False,
            help="Off by default. Demo runs from cache.",
        )
    else:
        uploaded_file = st.file_uploader(
            "Upload a COBOL source file",
            type=["cob", "cbl", "cobol", "txt"],
            help="One self-contained COBOL program. Reads stdin, writes stdout.",
        )
        regenerate = True
        st.caption("Uploads always run live. Expect 1–3 minutes.")

    run_clicked = st.button(
        "▶  Run pipeline",
        type="primary",
        use_container_width=True,
        disabled=(source_mode == "Upload" and uploaded_file is None),
    )

    st.divider()
    st.markdown(
        "**Pipeline**\n\n"
        "1. Analyze COBOL\n"
        "2. Generate Java\n"
        "3. Verify side-by-side\n"
        "4. Repair once if needed\n\n"
        "**Verification**\n\n"
        "Compiles COBOL with `cobc`, Java with `javac`, runs both on the "
        "same stdin, compares stdout byte-for-byte."
    )


# ----------------------------------------------------------------- pipeline

def _run_pipeline(
    cobol: str,
    sample_key: str | None,
    regenerate: bool,
    improve: bool = False,
) -> dict | None:
    """Run analyze -> generate -> verify -> repair."""

    with st.status("Running pipeline…", expanded=True) as status:
        st.write("**1 / 4**  Analyzing COBOL…")
        analysis, err = analyze(cobol, regenerate=regenerate)
        if err:
            status.update(label="Analyze failed", state="error")
            st.error(f"**analyze:** {err}")
            return None

        st.write("**2 / 4**  Generating Java…")
        generation, err = generate(
            cobol,
            analysis,
            regenerate=regenerate,
            improve=improve,
        )
        if err:
            status.update(label="Generate failed", state="error")
            st.error(f"**generate:** {err}")
            return None

        # Stress cases only exist for curated samples.
        stress = []
        if sample_key:
            try:
                stress = generate_stress_cases(sample_key)
            except KeyError:
                stress = []

        all_cases = list(generation.test_cases) + stress
        st.write(
            f"**3 / 4**  Verifying {len(all_cases)} cases "
            f"({len(generation.test_cases)} semantic + {len(stress)} stress)…"
        )
        report = verify(
            cobol,
            generation.java_source,
            all_cases,
            sample_key=sample_key,
        )

        decisions_by_name = {
            decision.case_name: decision for decision in report.decisions
        }
        repairable = [
            case
            for case in report.results
            if not case.match
            and not case.accepted_by_reviewer
            and not (
                case.name in decisions_by_name
                and decisions_by_name[case.name].decision == "skip"
            )
        ]
        if repairable:
            st.write(f"**4 / 4**  {len(repairable)} mismatch(es) — attempting repair…")
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
                report = verify(
                    cobol,
                    repaired.java_source,
                    all_cases,
                    sample_key=sample_key,
                )

        status.update(
            label=f"Done — {report.passed} / {len(report.results)} passed",
            state="complete",
        )

    return {
        "analysis": analysis,
        "generation": generation,
        "report": report,
        "all_cases": all_cases,
        "cobol": cobol,
        "sample_key": sample_key,
    }


# Clear stale state if the user uploads a different file.
if source_mode == "Upload" and uploaded_file is not None:
    token = f"{uploaded_file.name}:{uploaded_file.size}"
    if token != st.session_state.upload_token:
        st.session_state.upload_token = token
        st.session_state.result = None


if run_clicked:
    if source_mode == "Sample":
        path = SAMPLES[sample_name]
        if not path.exists():
            st.error(f"Sample not found: `{path}`")
        else:
            cobol = path.read_text(encoding="utf-8")
            st.session_state.result = _run_pipeline(
                cobol,
                sample_name,
                regenerate,
                improve=improve_mode,
            )
    else:
        raw = uploaded_file.read()
        cobol = raw.decode("utf-8-sig", errors="replace")
        cobol = cobol.replace("\r\n", "\n").replace("\r", "\n")
        sample_key = Path(uploaded_file.name).stem
        st.session_state.result = _run_pipeline(
            cobol,
            sample_key,
            regenerate=True,
            improve=improve_mode,
        )


# ----------------------------------------------------------------- tabs

result = st.session_state.result

tab_exp, tab_rules, tab_java, tab_tests, tab_verify = st.tabs(
    ["Explanation", "Rules", "Java", "Tests", "Verification"]
)


# --- Explanation ----------------------------------------------------------

with tab_exp:
    if not result:
        st.info("Choose a source in the sidebar, then click **▶ Run pipeline**.")
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

        st.subheader("Risks")
        if not a.risks:
            st.success("No risks flagged for this program.")
        else:
            for r in a.risks:
                st.warning(r)


# --- Rules ----------------------------------------------------------------

with tab_rules:
    if not result:
        st.info("Choose a source in the sidebar, then click **▶ Run pipeline**.")
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
        st.info("Choose a source in the sidebar, then click **▶ Run pipeline**.")
    else:
        g = result["generation"]
        st.code(g.java_source, language="java")

        st.download_button(
            label="⬇  Download Main.java",
            data=g.java_source,
            file_name="Main.java",
            mime="text/x-java-source",
            use_container_width=True,
        )

        if g.notes:
            st.subheader("Notes")
            for n in g.notes:
                st.markdown(f"- {n}")


# --- Tests ----------------------------------------------------------------

with tab_tests:
    if not result:
        st.info("Choose a source in the sidebar, then click **▶ Run pipeline**.")
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
        st.info("Choose a source in the sidebar, then click **▶ Run pipeline**.")
    else:
        report = result["report"]
        all_cases = result["all_cases"]
        stdin_by_name = {tc.name: tc.stdin for tc in all_cases}
        total = len(report.results)

        summary = f"###  {report.passed} / {total} passed"
        if report.accepted:
            summary += f"   ({report.accepted} accepted divergences)"

        unresolved_count = report.failed - report.accepted
        if unresolved_count == 0 and report.accepted == 0:
            st.success(f"###  ✓  {report.passed} / {total} passed")
        elif unresolved_count == 0:
            st.warning(summary)
        elif report.accepted:
            st.error(summary)
        else:
            st.error(
                f"###  {report.passed} / {total} passed  —  {report.failed} failed"
            )

        st.caption(
            "Each case runs the original COBOL and the generated Java on the "
            "same stdin. Stdout must match byte-for-byte."
        )

        # Download the full report as JSON
        st.download_button(
            label="⬇  Download verification report (JSON)",
            data=report.model_dump_json(indent=2),
            file_name="verification_report.json",
            mime="application/json",
        )

        # Compact summary table
        st.dataframe(
            [
                {
                    "Case": c.name,
                    "stdin": stdin_by_name.get(c.name, "")
                        .strip()
                        .replace("\n", " · "),
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
            with st.expander(f"{icon}  {c.name}", expanded=expand_all or not c.match):
                if c.accepted_by_reviewer:
                    st.warning("ACCEPTED DIVERGENCE")

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

                if not c.match and not c.accepted_by_reviewer:
                    existing_decision = next(
                        (
                            decision
                            for decision in report.decisions
                            if decision.case_name == c.name
                        ),
                        None,
                    )
                    if existing_decision:
                        st.caption(
                            f"Saved reviewer decision: {existing_decision.decision}"
                        )

                    decision_columns = st.columns(3)
                    choices = (
                        ("Preserve COBOL behaviour", "preserve_cobol"),
                        ("Accept Java behaviour", "accept_java"),
                        ("Skip", "skip"),
                    )
                    for column, (label, decision_value) in zip(
                        decision_columns,
                        choices,
                    ):
                        if column.button(label, key=f"{c.name}-{decision_value}"):
                            sample_key = result["sample_key"]
                            if sample_key is None:
                                st.error("Reviewer decisions require a sample key.")
                                st.stop()
                            if existing_decision:
                                clear_decision(sample_key, c.name)
                            save_decision(
                                sample_key,
                                DivergenceDecision(
                                    case_name=c.name,
                                    cobol_output=c.cobol_output,
                                    java_output=c.java_output,
                                    decision=decision_value,
                                    decided_at=datetime.now(timezone.utc).isoformat(),
                                ),
                            )
                            st.session_state.result = _run_pipeline(
                                result["cobol"],
                                sample_key,
                                regenerate=False,
                                improve=improve_mode,
                            )
                            st.rerun()