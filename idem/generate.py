from idem.llm import render_prompt, call_llm
from idem.schemas import AnalysisResult, GenerationResult


def generate(
    cobol_src: str,
    analysis: AnalysisResult,
    regenerate: bool = False,
    improve: bool = False,
):
    prompt_name = "generate_improved" if improve else "generate"
    prompt = render_prompt(
        prompt_name,
        cobol_source=cobol_src,
        analysis_json=analysis.model_dump_json(indent=2),
    )
    return call_llm(prompt_name, prompt, GenerationResult, regenerate=regenerate)