"""Source-bound automatic evaluation cards. Human approvals remain separate."""
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from evaluation.schema import StrictModel, digest

TAXES = ('corporate', 'vat', 'income', 'capital_gains', 'inheritance', 'gift')
TYPES = ('general', 'exception', 'missing_information', 'compound', 'temporal')


class Source(StrictModel):
    id: str
    law: str
    reference: str
    version: str
    effective_from: date
    source_url: str
    text: str = Field(min_length=1)
    text_hash: str
    snapshot_id: int
    snapshot_hash: str
    snapshot_file: str
    law_id: str
    mst: str
    promulgation_date: date | None = None


class SourcePackage(StrictModel):
    id: str
    tax: Literal['corporate', 'vat', 'income', 'capital_gains', 'inheritance', 'gift']
    case_type: Literal['general', 'exception', 'missing_information', 'compound', 'temporal']
    as_of: date
    sources: list[Source] = Field(min_length=1, max_length=24)
    unresolved: list[str] = Field(default_factory=list)
    scope: Literal['archived_official_versions'] = 'archived_official_versions'
    latest_verified: Literal[False] = False

    @model_validator(mode='after')
    def source_identity(self):
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError('duplicate_source_id')
        if any(s.effective_from > self.as_of for s in self.sources):
            raise ValueError('future_source_version')
        return self


class Citation(StrictModel):
    source_id: str
    quote: str = Field(min_length=8)


class Rule(StrictModel):
    id: str
    subject: str = Field(min_length=1)
    conditions: list[str]
    effect: str = Field(min_length=1)
    exceptions: list[str]
    needed_facts: list[str]
    citations: list[Citation] = Field(min_length=1)


class RuleBook(StrictModel):
    rules: list[Rule] = Field(min_length=1, max_length=8)
    unresolved: list[str]


class Fact(StrictModel):
    id: str
    text: str = Field(min_length=1, description='Exact continuous quotation of a fact in question')


class Expectation(StrictModel):
    id: str
    statement: str = Field(min_length=1)
    conditions: list[str]
    pass_if: str = Field(min_length=1)
    fail_if: str = Field(min_length=1)
    citations: list[Citation] = Field(min_length=1)


class CardIssue(StrictModel):
    id: str
    subject: str
    tax: Literal['corporate', 'vat', 'income', 'capital_gains', 'inheritance', 'gift']
    request_quote: str = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    expected_behavior: Literal['answer', 'partial', 'clarify', 'unknown']
    missing_inputs: list[str]
    required: list[Expectation] = Field(min_length=1, max_length=6)
    forbidden: list[Expectation] = Field(default_factory=list, max_length=4)


class CardDraft(StrictModel):
    question: str = Field(min_length=12, max_length=4000)
    facts: list[Fact] = Field(min_length=1, max_length=16)
    event_dates: list[date]
    issues: list[CardIssue] = Field(min_length=1, max_length=6)


REVIEW_DIMENSIONS = ('source_support', 'fact_fidelity', 'issue_coverage', 'answerability', 'temporal_scope')


class ReviewItem(StrictModel):
    dimension: Literal['source_support', 'fact_fidelity', 'issue_coverage', 'answerability', 'temporal_scope']
    verdict: Literal['pass', 'fail', 'unknown']
    reason: str = Field(min_length=1)
    citations: list[Citation]


class CardReview(StrictModel):
    items: list[ReviewItem]

    @model_validator(mode='after')
    def coverage(self):
        if len(self.items) != len(REVIEW_DIMENSIONS) or {i.dimension for i in self.items} != set(REVIEW_DIMENSIONS):
            raise ValueError('card_review_coverage')
        return self


class FrozenCard(StrictModel):
    id: str
    group: str
    split: Literal['dev', 'test']
    package_id: str
    package_hash: str
    rules: RuleBook
    draft: CardDraft
    review: CardReview
    status: Literal['auto_validated'] = 'auto_validated'
    human_approved: Literal[False] = False
    origin: Literal['synthetic_official_source'] = 'synthetic_official_source'
    builder_version: str
    model: str
    prompt_hash: str


class CardDataset(StrictModel):
    schema_version: Literal['auto-cards-1'] = 'auto-cards-1'
    packages: list[SourcePackage]
    cards: list[FrozenCard]
    failures: list[dict]
    metadata: dict

    @model_validator(mode='after')
    def integrity(self):
        packages = {p.id: p for p in self.packages}
        if len(packages) != len(self.packages):
            raise ValueError('duplicate_package_id')
        groups, questions, identities = {}, {}, set()
        source_splits = {}
        for card in self.cards:
            if card.id in identities or card.package_id not in packages:
                raise ValueError('duplicate_or_unknown_card')
            identities.add(card.id)
            if card.package_hash != digest(packages[card.package_id].model_dump(mode='json')):
                raise ValueError('card_package_hash')
            if groups.setdefault(card.group, card.split) != card.split:
                raise ValueError('card_group_leakage')
            for source in packages[card.package_id].sources:
                if source_splits.setdefault(source.id, card.split) != card.split:
                    raise ValueError('card_source_leakage')
            query = ''.join(c for c in card.draft.question.casefold() if c.isalnum())
            if query in questions:
                raise ValueError('duplicate_question')
            questions[query] = card.id
            if any(i.verdict != 'pass' for i in card.review.items):
                raise ValueError('unpassed_card_review')
        return self

    def fingerprint(self):
        return digest(self.model_dump(mode='json'))
