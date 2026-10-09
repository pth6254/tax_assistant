# Claude Code 프로젝트 지침

이 파일은 Claude Code의 **얇은 진입점**이다. 공통 작업 규칙·문서 역할·작성 형식은 [AGENTS.md](AGENTS.md)가
단일 원본이며, 상태·검증 수치·다음 작업은 이 파일에 적지 않는다. Claude 전용 규칙을 여기에 중복 작성하지 않고,
공통 규칙을 바꿀 때는 `AGENTS.md` 또는 `docs/ai/`의 원본 문서를 수정해 Codex와 Claude Code가 같은 맥락을 쓴다.

## 작업 전에 읽을 것

1. [AGENTS.md](AGENTS.md) — 규칙, 품질 목표, 서비스 기준, 문서 역할과 작성 형식
2. [PROJECT_CONTEXT.md](docs/ai/PROJECT_CONTEXT.md) — 목적, 코드 책임, 도메인 불변 규칙
3. [CURRENT_STATUS.md](docs/ai/CURRENT_STATUS.md) — 현재 상태와 검증 수치
4. [DECISIONS.md](docs/ai/DECISIONS.md) — 설계 결정과 이유
5. 현재 작업과 관련된 README 절·실제 코드·테스트
6. 이어 작업할 때 [HANDOFF.md](docs/ai/HANDOFF.md) 맨 위의 "현재 인계"

세션을 마칠 때는 AGENTS.md의 "작업 종료 규칙"에 따라 해당 문서를 갱신한다. 인수인계에 적힌 후속 작업을 문서
갱신만으로 완료 처리하지 않는다. 새 작업에서는 기존 변경을 보존하고 필요한 코드부터 읽는다.

## 작업별 코드 진입점

| 작업 | 먼저 확인할 코드 |
|---|---|
| 주체·쟁점 계획·세법 선택 | [question_planning.py](app/services/question_planning.py), [tax_laws.py](app/services/tax_laws.py) |
| 재검색·교차 법령 조회 | [reliable_workflow.py](app/services/reliable_workflow.py), [hybrid_search_service.py](app/services/search/hybrid_search_service.py) |
| 쟁점별 근거 충족 판정 | [issue_coverage.py](app/services/issue_coverage.py) |
| 질문 경로(과거 법령·도구) | [history_context.py](app/services/law/history_context.py), [policy.py](app/services/tools/policy.py), [planner.py](app/services/tools/planner.py) |
| 검색 후보·Graph 확장 | [hybrid_search_service.py](app/services/search/hybrid_search_service.py), [graph_search_service.py](app/services/search/graph_search_service.py) |
| 근거·주장 공개 검사 | [evidence.py](app/services/evidence.py), [claim_verification.py](app/services/claim_verification.py) (검사 등록표 `CHECKS`) |
| 사건일과 시행본 비교·사건 당시 조문 | [temporal_scope.py](app/services/temporal_scope.py), [historical_evidence.py](app/services/historical_evidence.py) |
| 참고 계산 | [formula_workflow.py](app/services/calculator/formula_workflow.py) |
| 금융소득 종합과세 계산기·채팅 입력 해석 | [financial_income_tax.py](app/services/calculator/financial_income_tax.py), [financial_inputs.py](app/services/calculator/financial_inputs.py) |
| 답변·근거 표시 | [answerSections.js](frontend/src/components/Chat/answerSections.js), [VerificationPanel.jsx](frontend/src/components/Chat/VerificationPanel.jsx) |
| 자동 카드·실제 관측·Judge | [auto_cards.py](evaluation/auto_cards.py), [auto_pipeline.py](evaluation/auto_pipeline.py), [auto_cli.py](evaluation/auto_cli.py) |
| 차단 집계·검사 가치 측정 | [block_report.py](evaluation/block_report.py), [filter_value.py](evaluation/filter_value.py) |

## 실행 환경 주의

- 이 환경의 셸은 Windows(PowerShell/Git Bash)다. 프로젝트 가상환경과 Docker는 **WSL**에서 쓴다. 테스트·서비스 재빌드는 `wsl -e bash -lc "cd '/mnt/c/Users/Laptop PC/Desktop/tax_assistant' && source venv-wsl/bin/activate && ..."` 형태로 실행한다. Windows 쪽 Python에는 프로젝트 의존성이 없다.
- 셸 heredoc으로 파이썬 코드를 쓸 때 `\n`·`\\` 같은 이스케이프가 변형될 수 있다. 이스케이프가 필요한 코드는 파일로 작성해 실행한다.
- 실제 모델(OpenRouter)을 호출하는 평가는 유료다. 호출 수와 서로 다른 질문 수를 밝히고 코드·테스트·저장 결과로 먼저 확인한다.

## 문서 찾기

- 규칙·문서 작성 형식: [AGENTS.md](AGENTS.md). 설치·실행·설정·API: [README.md](README.md).
- 상태·검증 수치: [CURRENT_STATUS.md](docs/ai/CURRENT_STATUS.md). 다음 작업·결과 위치: [HANDOFF.md](docs/ai/HANDOFF.md).
- 검증 흐름: [RELIABILITY_WORKFLOW.md](docs/ai/RELIABILITY_WORKFLOW.md). Reranker 등 미구현 제안: [RAG_IMPROVEMENT_PLAN.md](docs/ai/RAG_IMPROVEMENT_PLAN.md)(제안을 구현 완료로 표시하지 않는다).
- 자동 질문·평가·LangSmith 게시, 차단 집계·오류 주입 측정: [AUTO_EVALUATION.md](evaluation/AUTO_EVALUATION.md). 합성 카드의 자동 진단과 인간 세무 승인을 구분한다.
