"""Strict, reviewable dataset and execution-record contracts."""
import hashlib
import json
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Review(StrictModel):
    status: Literal['draft', 'approved', 'retired'] = 'draft'
    basis: Literal['synthetic_contract', 'official_source']
    reviewer: str = ''
    reviewer_kind: Literal['human', 'contract_author', 'unreviewed'] = 'unreviewed'
    reviewed_on: date | None = None
    notes: str = ''

    @model_validator(mode='after')
    def approval(self):
        if self.status == 'approved':
            if not self.reviewer.strip() or not self.reviewed_on or self.reviewer_kind == 'unreviewed':
                raise ValueError('Approval requires reviewer, kind and date')
            if self.basis == 'official_source' and self.reviewer_kind != 'human':
                raise ValueError('Legal gold labels require human review, not model self-approval')
        return self


class Evidence(StrictModel):
    kind: Literal['law', 'interpretation'] = 'law'
    law: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    version: str = ''
    source_url: str = ''
    quote: str = ''

    def key(self):
        # Keep article branches and paragraph/item distinctions. No substring matching.
        from app.services.law.reference_parser import parse_law_reference
        if self.kind == 'interpretation':
            if not re.fullmatch(r'\d{2}-\d{4}', self.reference):
                raise ValueError('Invalid interpretation identifier')
            reference = 'interpretation:' + self.reference
        else:
            ref = parse_law_reference(self.reference)
            if ref.law_name:
                raise ValueError('Put the law name in law, not reference')
            reference = ref.canonical
        return re.sub(r'\s+', '', self.law), reference, self.version


class Judgment(StrictModel):
    evidence: Evidence
    label: Literal['required', 'supporting', 'irrelevant', 'hard_negative']
    reason: str = Field(min_length=1)
    confusion: Literal['none', 'same_terms', 'wrong_tax', 'wrong_subject', 'wrong_date',
                       'wrong_level', 'branch_vs_paragraph', 'wrong_exception'] = 'none'


class Check(StrictModel):
    path: str = Field(min_length=1)
    op: Literal['equals', 'number', 'min', 'max', 'contains', 'absent'] = 'equals'
    expected: object
    tolerance: float = Field(default=0, ge=0)
    critical: bool = False


class Criterion(StrictModel):
    id: str = Field(min_length=1)
    dimension: Literal['factuality', 'grounding', 'completeness', 'temporal', 'abstention', 'safety']
    instruction: str = Field(min_length=1)
    critical: bool = False


class Counterexample(StrictModel):
    payload: dict
    reason: str = Field(min_length=1)
    confusion: str = Field(min_length=1)


class Case(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9][a-z0-9_.-]+$')
    group: str = Field(min_length=1)
    split: Literal['dev', 'test']
    stage: Literal['source', 'reference', 'relation', 'retrieval', 'context', 'calculator',
                   'tools', 'answer', 'safety', 'performance']
    adapter: Literal['reference', 'relation', 'graph_index', 'progressive_tax', 'calculator', 'retrieval', 'source', 'tool_selection', 'answer_fixed_context', 'recorded']
    review: Review
    input: dict
    checks: list[Check] = Field(default_factory=list)
    judgments: list[Judgment] = Field(default_factory=list)
    rubric: list[Criterion] = Field(default_factory=list)
    counterexamples: list[Counterexample] = Field(default_factory=list)
    # Draft legacy cases may have no confirmed gold yet.
    answerable: bool = True
    k: int = Field(default=5, ge=1, le=50)
    min_recall: float = Field(default=1, ge=0, le=1)
    min_precision: float = Field(default=0.8, ge=0, le=1)
    max_hard_negatives: int = Field(default=0, ge=0)
    source_url: str = ''
    source_quote: str = ''
    as_of: date | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def consistency(self):
        stages = {'reference': 'reference', 'relation': 'relation', 'graph_index': 'relation', 'progressive_tax': 'calculator',
                  'calculator': 'calculator', 'retrieval': 'retrieval', 'source': 'source',
                  'tool_selection': 'tools', 'answer_fixed_context': 'answer'}
        if self.adapter in stages and self.stage != stages[self.adapter]:
            raise ValueError('Adapter/stage mismatch')
        keys = [j.evidence.key() for j in self.judgments]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate or contradictory evidence judgments')
        # Mixing version-specific and version-agnostic labels creates ambiguous matching.
        refs = [key[:2] for key in keys]
        for ref in set(refs):
            versions = [key[2] for key in keys if key[:2] == ref]
            if '' in versions and len(versions) > 1:
                raise ValueError('Do not mix versioned and unversioned judgments for one reference')
        for judgment in self.judgments:
            if judgment.label == 'hard_negative' and judgment.confusion == 'none':
                raise ValueError('Hard negatives require a confusion category')
        if len({r.id for r in self.rubric}) != len(self.rubric):
            raise ValueError('Duplicate rubric IDs')
        if self.review.status == 'approved':
            if self.stage == 'retrieval':
                required = [j for j in self.judgments if j.label == 'required']
                if self.answerable and not required:
                    raise ValueError('Answerable retrieval cases require gold evidence')
                if not self.answerable and required:
                    raise ValueError('Unanswerable cases cannot require evidence')
            elif not self.checks and not self.rubric:
                raise ValueError('Approved cases require explicit assertions/rubrics')
            if self.stage == 'answer' and not self.rubric:
                raise ValueError('Answer correctness cannot be inferred from keywords alone')
            if self.review.basis == 'official_source':
                if not self.source_url or not self.source_quote or not self.as_of:
                    raise ValueError('Legal gold requires source URL, quoted evidence and as_of date')
                if any(not j.evidence.source_url or not j.evidence.quote or not j.evidence.version for j in self.judgments):
                    raise ValueError('Every legal judgment needs source evidence and a version identifier')
        return self


class Dataset(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    name: str
    version: str
    description: str
    cases: list[Case] = Field(min_length=1)

    @model_validator(mode='after')
    def leakage(self):
        ids, groups, queries = set(), {}, {}
        for case in self.cases:
            if case.id in ids:
                raise ValueError('Duplicate case ID: ' + case.id)
            ids.add(case.id)
            previous = groups.setdefault(case.group, case.split)
            if previous != case.split:
                raise ValueError('Group leakage across dev/test: ' + case.group)
            query = re.sub(r'\W+', '', str(case.input.get('query', '')).casefold())
            if query:
                previous = queries.setdefault(query, case.split)
                if previous != case.split:
                    raise ValueError('Exact normalized question leaked across splits')
        return self

    def fingerprint(self):
        return digest(self.model_dump(mode='json'))


class Observation(StrictModel):
    case_id: str
    variant: Literal['base', 'graph', 'system'] = 'system'
    repeat: int = Field(default=1, ge=1)
    payload: dict = Field(default_factory=dict)
    error: str | None = None
    elapsed_seconds: float = Field(default=0, ge=0)


class Run(StrictModel):
    schema_version: Literal['1.0'] = '1.0'
    dataset_hash: str
    split: Literal['dev', 'test', 'all']
    mode: Literal['offline', 'live', 'recorded']
    selected_ids: list[str]
    repeats: int = Field(default=1, ge=1)
    metadata: dict = Field(default_factory=dict)
    observations: list[Observation]


class Verdict(StrictModel):
    passed: bool = Field(strict=True)
    rationale: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class Adjudication(StrictModel):
    case_id: str
    variant: str
    repeat: int
    payload_hash: str
    reviewer: str = Field(min_length=1)
    reviewer_kind: Literal['human'] = 'human'
    reviewed_on: date
    criteria: dict[str, Verdict]

    @model_validator(mode='after')
    def identity(self):
        if not self.reviewer.strip():
            raise ValueError('A named human reviewer is required')
        return self
