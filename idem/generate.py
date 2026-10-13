from idem.llm import render_prompt, call_llm
from idem.schemas import AnalysisResult, GenerationResult


def generate(
    cobol_src: str,
    analysis: AnalysisResult,
    regenerate: bool = False,
):
    prompt = render_prompt(
        "generate",
        cobol_source=cobol_src,
        analysis_json=analysis.model_dump_json(indent=2),
    )
    return call_llm("generate", prompt, GenerationResult, regenerate=regenerate)