from idem.llm import render_prompt, call_llm
from idem.schemas import AnalysisResult


def analyze(cobol_src: str, regenerate: bool = False):
    prompt = render_prompt("analyze", cobol_source=cobol_src)
    return call_llm("analyze", prompt, AnalysisResult, regenerate=regenerate)