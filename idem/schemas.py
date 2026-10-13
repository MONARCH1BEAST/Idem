from pydantic import BaseModel, Field


class BusinessRule(BaseModel):
    id: str
    description: str
    cobol_lines: str
    confidence: float = Field(ge=0.0, le=1.0)


class AnalysisResult(BaseModel):
    summary: str
    inputs: list[str]
    outputs: list[str]
    business_rules: list[BusinessRule]
    risks: list[str]


class TestCase(BaseModel):
    name: str
    stdin: str


class GenerationResult(BaseModel):
    java_source: str
    test_cases: list[TestCase]
    notes: list[str]


class CaseResult(BaseModel):
    name: str
    cobol_output: str
    java_output: str
    match: bool
    stderr: str = ""
    reason: str = ""


class VerificationReport(BaseModel):
    results: list[CaseResult]
    passed: int
    failed: int