# 문서 목록

프로젝트 소개는 [저장소 README](../README.md)에 있습니다. 여기서는 문서를 독자별로 묶습니다.
날짜가 붙은 문서는 그 시점의 기록이며, 지금 상태는 [현재 상태](ai/CURRENT_STATUS.md)가 원본입니다.

## 처음 보는 사람

| 문서 | 내용 |
|---|---|
| [기능 상세](FEATURES.md) | 기능별 동작, 계산기 지원 범위와 검증 사례, 사용 예시, 한계 |
| [구조와 핵심 구현](ARCHITECTURE.md) | 시스템 구성, 데이터 흐름, 기술 스택, 코드 구조, 보안 설계 |
| [설치·실행·테스트](SETUP.md) | 설치, 환경 변수, 테스트, 문제 해결 |
| [API](API.md) | HTTP API 목록 |
| [발표 자료](portfolio/README.md) | 면접용 HTML 슬라이드와 화면 캡처 스크립트 |

## 상태·결정·계획 (개발 문서)

| 문서 | 내용 |
|---|---|
| [현재 상태](ai/CURRENT_STATUS.md) | 구현 범위와 검증 수치의 원본(날짜·범위 포함) |
| [설계 결정](ai/DECISIONS.md) | 결정, 이유, 바꾸는 조건(ADR) |
| [인수인계](ai/HANDOFF.md) | 다음 작업과 결과 위치, 날짜별 작업 기록 |
| [로드맵](ai/ROADMAP.md) | 평가 지표·성능 개선·배포의 단계별 계획 |
| [데이터 구조 전략](ai/DATA_STRATEGY.md) | 법령 원문 한 원본에서 파생 데이터를 만드는 계획 |
| [프로젝트 공통 컨텍스트](ai/PROJECT_CONTEXT.md) | 목적, 코드 책임, 도메인 불변 규칙 |
| [검증 흐름](ai/RELIABILITY_WORKFLOW.md) | 질문·도구·근거·주장 검증의 단계 |
| [추가 RAG 개선 제안](ai/RAG_IMPROVEMENT_PLAN.md) | 아직 구현하지 않은 제안(재정렬 모델 등) |

## 기능별 설계

| 문서 | 내용 |
|---|---|
| [과거 법령 수집과 버전 관리](LAW_HISTORY.md) | 시행본 보관소 수집·검수 |
| [과거 법령 임베딩·GraphRAG](HISTORY_RAG.md) | 과거 버전 검색 경로 |
| [현행 GraphRAG](GRAPH_RAG.md) | 조문 인용 관계로 검색을 보충하는 경로 |
| [버전별 세무 법령 Knowledge Graph](TAX_KNOWLEDGE_GRAPH.md) | 버전별 조·항·호 관계 적재·검수 |

## 평가

| 문서 | 내용 |
|---|---|
| [평가 도구와 판정 규약](../evaluation/README.md) | 평가셋 목록, 판정 규약, 실행 방법 |
| [조문 검색 평가셋](../evaluation/EMBEDDING_RETRIEVAL_SET.md) | 임베딩·검색 비교용 평가셋 카드 |
| [자동 질문·평가 카드](../evaluation/AUTO_EVALUATION.md) | 공식 원문에서 질문과 평가 카드를 만드는 도구 |
| [세무 답변 품질 기준](../evaluation/QUALITY_CRITERIA.md) | 답변 품질 판정 기준 v0.1 |
| [LangSmith 연동](../evaluation/LANGSMITH.md) | 평가 결과 게시와 검수 |
| [Knowledge Graph 관계 검수](../evaluation/KG_RELATION_REVIEW.md) | 과거 법령 관계 검수 절차 |

## 날짜별 검증·검토 기록

| 날짜 | 문서 |
|---|---|
| 2026-09-13 | [법령 그래프 최초 저장·검수](GRAPH_AUDIT_2026-09-13.md) |
| 2026-09-19 | [GraphRAG 구현·실행 검증](GRAPH_RAG_VALIDATION_2026-09-19.md), [평가 파이프라인 구현 검증](../evaluation/VALIDATION_2026-09-19.md) |
| 2026-09-22 | [판례 기반 채팅 품질 실험](evaluation/2026-09-22-precedent-pilot.md) |
| 2026-09-23~25 | [과거 법령 데이터 검수](evaluation/2026-09-23-law-history-audit.md), [수집 복구](evaluation/2026-09-24-law-history-recovery.md), [임베딩 검증](evaluation/2026-09-25-history-embedding-validation.md), [런타임 점검](evaluation/2026-09-25-history-runtime-review.md), [결함 수정](evaluation/2026-09-25-history-runtime-fixes.md), [국제세무 자료 수집](evaluation/international-tax-pilot-2026-09-25.md) |
| 2026-09-27 | [프로젝트 분석·개선 제안](ai/PROJECT_REVIEW_2026-09-27.md), [도구·근거 신뢰성 개선안](ai/TOOL_AND_EVIDENCE_RELIABILITY_PLAN_2026-09-27.md), [LLM Judge 세무 정확성 연구](ai/LLM_JUDGE_TAX_VALIDATION_RESEARCH_2026-09-27.md), [세무 정확성 검증 설계 초안](ai/TAX_ACCURACY_GATE.md) |

## 운영 도구

- [운영·데이터 작업 CLI](../scripts/README.md): 법령 수집·동기화·감사·재색인 스크립트

## 작업 규칙

- [AGENTS.md](../AGENTS.md): 문서 역할, 작업 시작·종료 규칙, 품질 목표(AI 코딩 도구와 사람 모두 따름)
- [CLAUDE.md](../CLAUDE.md): Claude Code의 진입점과 작업별 코드 위치
