from dataclasses import dataclass

from pydantic import BaseModel


@dataclass
class LawSummary:
    """법령 검색 결과 단건."""
    mst: str
    law_name: str
    law_type: str
    promulgation_date: str
    ministry: str


@dataclass
class LawArticle:
    """조문 단위 파싱 결과."""
    law_name: str
    law_type: str
    article_no: str
    article_title: str
    article_text: str
    effective_date: str
    amendment_date: str


@dataclass
class HybridSearchResult:
    """하이브리드 검색 결과 단건."""
    content: str
    source: str
    law_name: str
    category: str
    source_type: str
    similarity_score: float
    priority: int


class LawArticleDetail(BaseModel):
    """조문 원문 뷰어 응답."""
    law_name: str
    law_type: str
    tax_type: str
    article_no: str
    article_title: str
    article_text: str
    effective_date: str
    amendment_date: str
    source_url: str
