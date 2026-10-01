# Claude Code 프로젝트 지침

문서 기준일: 2026-10-01. 이 프로젝트의 공통 AI 작업 규칙은 [AGENTS.md](AGENTS.md)가 단일 진입점이다.
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

## 문서 찾기

- 실행 방법·모델 역할·검증 규칙: [AGENTS.md](AGENTS.md), [README.md](README.md).
- 완료 상태·검증 수치: [CURRENT_STATUS.md](docs/ai/CURRENT_STATUS.md). 수치는 기록된 날짜와 범위에 한정한다.
- 다음 작업·결과 파일·복원 자료: [HANDOFF.md](docs/ai/HANDOFF.md).
- Reranker 등 추가 RAG 개선 제안: [RAG_IMPROVEMENT_PLAN.md](docs/ai/RAG_IMPROVEMENT_PLAN.md). 제안 항목을 구현 완료로 표시하지 않는다.
