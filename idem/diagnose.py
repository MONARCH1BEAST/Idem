from pydantic import BaseModel

from idem.llm import call_llm, render_prompt


class DiagnosisResult(BaseModel):
    explanation: str


def diagnose(
    cobol_src: str,
    java_src: str,
    stdin: str,
    cobol_output: str,
    java_output: str,
) -> tuple[str | None, str | None]:
    prompt = render_prompt(
        "diagnose",
        cobol_source=cobol_src,
        java_source=java_src,
        stdin=stdin,
        cobol_output=cobol_output,
        java_output=java_output,
    )
    result, err = call_llm("diagnose", prompt, DiagnosisResult)
    if err:
        return None, err
    return result.explanation, None
