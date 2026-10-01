"""Versioned contracts shared by retrieval, generation, checks and evaluation."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


def strict_schema(model):
    """Providers using strict JSON schema require every object key in required."""
    schema = model.model_json_schema()
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    return schema


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issue(Contract):
    id: str
    request_quote: str
    subject: str = ""
    law: str = "ALL"
    kind: Literal["analysis", "exact_lookup", "document_search", "calculation"] = "analysis"
    question: str
    depends_on: list[str] = Field(default_factory=list)


class QuestionPlan(Contract):
    issues: list[Issue] = Field(min_length=1, max_length=12)
    dates: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    status: Literal["planned", "fallback"] = "planned"


class EvidenceRecord(Contract):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    origin: Literal["official_law", "user_document", "unknown"]
    source_id: str = ""
    source: str = ""
    law_name: str = ""
    category: str = ""
    reference: str = ""
    version_id: str = ""
    effective_from: str = ""
    effective_to: str = ""
    content_hash: str
    original_hash: str = ""
    text: str
    location: str = ""
    integrity: Literal["verified", "unavailable", "mismatch"] = "unavailable"
    graph_evidence: str = ""
    completeness: Literal["not_assessed", "missing_items"] = "not_assessed"


class ClaimCitation(Contract):
    evidence_id: str
    quote: str = Field(min_length=1)


class AnswerClaim(Contract):
    id: str
    issue_id: str
    text: str = Field(min_length=1, max_length=3000)
    kind: Literal["legal", "source_summary", "document", "fact", "guidance"]
    citations: list[ClaimCitation] = Field(default_factory=list, max_length=8)
    conditions: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    question_part: str = Field(default="", description="이 주장이 답하는 요청의 사용자 질문 연속 원문. 표시 순서에만 사용.")
    presentation_role: Literal["conclusion", "explanation", "procedure", "checklist"] = Field(
        default="explanation", description="공개 승인 이후의 배치 용도. 근거·판정·승인 여부에는 영향을 주지 않음.")


class AnswerDraft(Contract):
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=32)


class ClaimJudgment(Contract):
    claim_id: str
    support: Literal["supported", "contradicted", "insufficient"]
    applicability: Literal["supported", "contradicted", "insufficient"]
    evidence_ids: list[str]
    reason: str


class JudgeReport(Contract):
    claims: list[ClaimJudgment]
    missing_issue_ids: list[str] = Field(default_factory=list)
