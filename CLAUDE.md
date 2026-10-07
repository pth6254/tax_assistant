# Claude Code 프로젝트 지침

문서 기준일: 2026-10-06. 이 프로젝트의 공통 AI 작업 규칙은 [AGENTS.md](AGENTS.md)가 단일 진입점이다.
작업 전 반드시 다음을 읽는다.

1. `AGENTS.md`
2. `docs/ai/PROJECT_CONTEXT.md`
3. `docs/ai/CURRENT_STATUS.md`
4. `docs/ai/DECISIONS.md`
5. 현재 작업과 관련된 README 절·실제 코드·테스트
6. 이어 작업할 때 `docs/ai/HANDOFF.md`의 최신 요약과 남은 작업

Claude 전용 규칙을 이 파일에 중복 작성하지 않는다. 공통 규칙을 변경할 때는 `AGENTS.md` 또는
`docs/ai/`의 원본 문서를 수정하여 Codex와 Claude Code가 같은 맥락을 사용하게 한다.

세션을 마칠 때 작업이 완전히 끝나지 않았거나 다음 작업자가 알아야 할 내용이 있으면
`docs/ai/HANDOFF.md`를 갱신한다.

## 이번 대화의 인수인계

- 목표는 잘못된 결과의 공개를 막으면서 여러 분야의 복합 세무 질문에 유용하고 자연스럽게 답하는 것이다. 답변 구조·반복 안내·부분 유보·계산 요청의 처리 기준은 [AGENTS.md의 품질 목표](AGENTS.md#대화에서-확정한-품질-목표)를 따른다.
- 현행 모델은 OpenRouter `openai/gpt-6-luna` 생성·계획·Judge와 Windows Ollama `qwen3-embedding:4b`/v1 임베딩이다. BM25·벡터·GraphRAG·Fuzzy·Regex·MMR은 구현돼 있고, 전용 Reranker는 후속 제안이다.
- 마지막 구현은 공식 XML 기반 자동 질문·평가 카드와 실제 채팅/Judge/LangSmith 게시다. 기준은 채팅 입력과 분리한다. `auto_validated` 카드를 인간 승인으로 취급하지 않는다.
- **바로 이어서 할 일**: 개인/회사 주체 오인, 날짜만으로 원문 조회를 요구하는 경로, 복합 요청의 공제 조건 누락을 수정하고 고정 카드로 비교한다. 다음으로 전체 유형 확대와 독립 정답·그래프·숫자 검수를 진행한다. 상세 우선순위·미완료 데이터는 [HANDOFF.md](docs/ai/HANDOFF.md)에 있다.
- **마지막 실행 검증은 2026-10-04**다. 백엔드 1,005 passed/2 skipped/5 subtests passed. 동일 저장 답변 3개는 모두 fail이며 평가기 오류는 0이다. 2026-10-06 갱신은 문서 작업이며, 제품 테스트나 실모델 호출을 다시 실행한 결과가 아니다.
- 최종 결과는 Git/Docker 제외인 `evaluation/runs/auto-evaluation-20261004/`에 있다. `rejudge-final/`은 저장 관측 재판정이고 `live-final/`은 별도의 새 실제 실행이다. 결과를 인계받지 못했다면 수치를 새 검증 결과로 보고하지 않는다.

### 작업별 코드 진입점

| 작업 | 먼저 확인할 코드 |
|---|---|
| 주체·쟁점 계획 | [question_planning.py](app/services/question_planning.py) |
| 검색 후보·Graph 확장 | [hybrid_search_service.py](app/services/search/hybrid_search_service.py), [graph_search_service.py](app/services/search/graph_search_service.py) |
| 근거·주장 공개 검사 | [evidence.py](app/services/evidence.py), [claim_verification.py](app/services/claim_verification.py) |
| 참고 계산 | [formula_workflow.py](app/services/calculator/formula_workflow.py) |
| 답변·근거 표시 | [answerSections.js](frontend/src/components/Chat/answerSections.js), [VerificationPanel.jsx](frontend/src/components/Chat/VerificationPanel.jsx) |
| 자동 카드·실제 관측·Judge | [auto_cards.py](evaluation/auto_cards.py), [auto_pipeline.py](evaluation/auto_pipeline.py), [auto_cli.py](evaluation/auto_cli.py) |

공통 실행·검증·게시 규칙은 AGENTS와 연결 문서에서 유지한다. 새 작업에서는 기존 변경을
보존하고 필요한 코드부터 읽는다. 인수인계에 적힌 후속 작업을 문서 갱신만으로 완료 처리하지 않는다.

## 문서 찾기

- 실행 방법·모델 역할·검증 규칙: [AGENTS.md](AGENTS.md), [README.md](README.md).
- 완료 상태·검증 수치: [CURRENT_STATUS.md](docs/ai/CURRENT_STATUS.md). 수치는 기록된 날짜와 범위에 한정한다.
- 다음 작업·결과 파일·복원 자료: [HANDOFF.md](docs/ai/HANDOFF.md).
- Reranker 등 추가 RAG 개선 제안: [RAG_IMPROVEMENT_PLAN.md](docs/ai/RAG_IMPROVEMENT_PLAN.md). 제안 항목을 구현 완료로 표시하지 않는다.
- 자동 질문·평가·LangSmith 게시: [AUTO_EVALUATION.md](evaluation/AUTO_EVALUATION.md). 공개 합성 카드의 자동 진단과 인간 세무 승인을 구분한다.
