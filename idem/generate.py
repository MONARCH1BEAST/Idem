from idem.llm import render_prompt, call_llm
from idem.schemas import AnalysisResult, GenerationResult


def generate(
    cobol_src: str,
    analysis: AnalysisResult,
    regenerate: bool = False,
    improve: bool = False,
) -> tuple[GenerationResult | None, str | None]:
    """Generate Java code and test cases from COBOL.

    Args:
        cobol_src: The source COBOL program.
        analysis: The parsed AnalysisResult from the analyze step.
        regenerate: If True, bypass the cache and call the LLM.
        improve: If True, use the improve prompt to fix obvious COBOL bugs.
    """
    prompt_name = "generate_improved" if improve else "generate"
    
    prompt = render_prompt(
        prompt_name,
        cobol_source=cobol_src,
        analysis_json=analysis.model_dump_json(indent=2),
    )

    result, err = call_llm(
        prompt_name, 
        prompt, 
        GenerationResult, 
        regenerate=regenerate
    )
    
    if err:
        return None, err

    # IRONCLAD FIX: Force the Java class name to be `Main` and ensure imports exist.
    if result and result.java_source:
        import re

        # 1. Force class name to be Main
        result.java_source = re.sub(
            r'public\s+class\s+\w+',
            'public class Main',
            result.java_source,
        )

        # 2. Inject missing imports if the LLM forgot them
        if "Locale.ROOT" in result.java_source and "import java.util.Locale" not in result.java_source:
            result.java_source = result.java_source.replace(
                "public class Main",
                "import java.util.Locale;\n\npublic class Main",
            )

        if "BigDecimal" in result.java_source and "import java.math.BigDecimal" not in result.java_source:
            result.java_source = result.java_source.replace(
                "public class Main",
                "import java.math.BigDecimal;\n\npublic class Main",
            )

        # 3. Fix System.in.readLine() hallucination
        if "System.in.readLine()" in result.java_source:
            # Add imports if missing
            if "import java.io.BufferedReader" not in result.java_source:
                result.java_source = "import java.io.BufferedReader;\nimport java.io.InputStreamReader;\n" + result.java_source
            # Replace the bad call
            result.java_source = result.java_source.replace(
                "System.in.readLine()",
                "new BufferedReader(new InputStreamReader(System.in)).readLine()",
            )

    return result, None