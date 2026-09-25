"""Task-local inference purpose; independent of provider-specific parameters."""
from contextvars import ContextVar

llm_purpose: ContextVar[str] = ContextVar("llm_purpose", default="answer")
EXTRACTION_PURPOSES = frozenset({"tool_selection", "query_classification", "citation_extraction"})
