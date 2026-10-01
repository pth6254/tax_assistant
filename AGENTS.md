# AI 작업 지침

문서 기준일: 2026-10-01. 실행 방법과 모델 역할은 아래의 현행 기준을 따른다.

이 저장소에서 작업하는 Codex 및 호환 에이전트는 작업을 시작하기 전에 다음 문서를 순서대로 읽는다.

1. `docs/ai/PROJECT_CONTEXT.md` — 프로젝트 목적, 구조, 도메인 불변 규칙
2. `docs/ai/CURRENT_STATUS.md` — 현재 구현 상태, 진행 중인 변경, 다음 작업
3. `docs/ai/DECISIONS.md` — 주요 설계 결정과 이유
4. 작업과 관련된 `README.md` 절 및 실제 코드

이어 작업할 때는 `docs/ai/HANDOFF.md`의 최신 인계와 남은 작업을 확인한다. 날짜별 과거 기록에
등장하는 모델·테스트 수·미완료 항목은 해당 시점의 기록이며, 최신 요약과 실제 코드를 우선한다.

## 작업 시작 규칙

- 먼저 `git status --short`로 사용자의 기존 변경을 확인하고 보존한다.
- 문서보다 실제 코드와 테스트가 다르면 코드를 기준으로 판단하되, 작업 완료 시 컨텍스트 문서를 함께 갱신한다.
- `.env`, `.claude/settings.local.json` 등 비밀 또는 로컬 설정의 값을 출력하거나 문서에 복사하지 않는다.
- 법령·세율·운영 상태처럼 변경 가능한 사실은 추측하지 않고 공식 데이터 또는 실행 결과로 검증한다.

## 현행 서비스 기준

- 생성·질문 계획·Judge: OpenRouter `openai/gpt-6-luna`. 임베딩: Windows Ollama `qwen3-embedding:4b`, `v1`, 2,560차원.
- `config.py`의 기본 생성 provider는 `ollama`이므로 실제 실행 환경에는 `LLM_PROVIDER=openrouter`, `CHAT_MODEL=openai/gpt-6-luna`를 명시한다. 사용자 요청 없이 모델 역할이나 벡터 버전을 바꾸지 않는다.
- LLM 작업은 `answer`, `history_answer`, `citation_extraction`, `query_classification`, `tool_selection`, `document_classification`, `question_planning`, `answer_judge`의 8개다. 작업별 설정은 공통 provider/model을 상속한다.
- 공식 현행 쟁점 검색은 BM25·벡터·검증된 GraphRAG와 Fuzzy·Regex·MMR을 사용한다. 사용자 문서 소유권과 과거 법령의 별도 경로를 유지한다.
- 전용 Reranker는 미구현이다. `docs/ai/RAG_IMPROVEMENT_PLAN.md`의 모델·서비스·설정은 제안이며 현재 기능으로 기술하지 않는다.
- 운영자 평가·검수는 LangSmith다. 사용자에게는 SSE 진행 상태와 채팅 근거 패널을 제공한다.
- 공식 출처 ID·버전·해시·원문 인용과 주장 검사를 보존한다. 표시 역할·검색 순위·Judge 판정을 세무 정확성의 독립 입증으로 취급하지 않는다.

## 실행 및 검증

- 현재 서비스의 개발 실행·재빌드는 WSL 가상환경을 활성화한 뒤 `dev/docker-up-wsl.sh`를 사용한다.

```bash
cd '/mnt/c/Users/Laptop PC/Desktop/tax_assistant'
source venv-wsl/bin/activate
bash dev/docker-up-wsl.sh backend frontend
```

- 스크립트는 Windows Ollama 주소·필수 임베딩/로컬 작업 모델을 검사한다. GraphRAG 사용 설정이면 Neo4j를 먼저 준비하고 Compose를 실행한다. 생성 provider는 현재 설정을 따른다.
- `dev/docker-up-llamacpp-wsl.sh`는 명시적으로 llama.cpp를 시험할 때만 사용한다. 기본 서비스 실행에 overlay를 적용하지 않는다.
- 웹은 `http://localhost:3001`, 백엔드는 `http://127.0.0.1:8001`이다. `/api/health/ready`는 DB 준비 상태, `/api/health/dependencies`는 LLM·임베딩·Graph 상태를 구분한다.
- 백엔드 구현 변경의 전체 테스트는 최신 이미지에서 실행한다. 문서만 바꾼 작업은 링크·명령·코드 대조와 diff 검사를 하고 검증 범위를 보고한다.

```bash
docker exec tax_backend pytest -q
```

- 프런트엔드 변경은 `frontend/`에서 `npm test`, `npm run build`로 확인한다. 실제 모델/화면 검증과 독립 세무 정답 검수를 구분한다.
- DB 스키마 변경은 수동 SQL 적용이 아니라 Alembic revision으로 작성한다.
- 데이터 전체 재수집, 삭제, 대규모 백필처럼 기존 상태를 바꾸는 작업은 범위를 확인한 후 실행한다.

## 작업 종료 규칙

- 구현과 관련 테스트를 완료한다.
- `git diff --check`를 실행한다.
- 아키텍처, 실행법, 현재 상태 또는 다음 작업이 달라졌다면 `docs/ai/` 문서를 갱신한다.
- 미완료 작업이나 데이터 보정 필요 사항은 `docs/ai/HANDOFF.md`에 구체적으로 남긴다.
- 완료 결과에는 검증 날짜·범위·결과 파일을 남긴다. 개발용 평가 라벨과 작은 스모크를 전체 세무 정답률로 보고하지 않는다.
