# AI 작업 지침

이 저장소에서 작업하는 Codex 및 호환 에이전트는 작업을 시작하기 전에 다음 문서를 순서대로 읽는다.

1. `docs/ai/PROJECT_CONTEXT.md` — 프로젝트 목적, 구조, 도메인 불변 규칙
2. `docs/ai/CURRENT_STATUS.md` — 현재 구현 상태, 진행 중인 변경, 다음 작업
3. `docs/ai/DECISIONS.md` — 주요 설계 결정과 이유
4. 작업과 관련된 `README.md` 절 및 실제 코드

## 작업 시작 규칙

- 먼저 `git status --short`로 사용자의 기존 변경을 확인하고 보존한다.
- 문서보다 실제 코드와 테스트가 다르면 코드를 기준으로 판단하되, 작업 완료 시 컨텍스트 문서를 함께 갱신한다.
- `.env`, `.claude/settings.local.json` 등 비밀 또는 로컬 설정의 값을 출력하거나 문서에 복사하지 않는다.
- 법령·세율·운영 상태처럼 변경 가능한 사실은 추측하지 않고 공식 데이터 또는 실행 결과로 검증한다.

## 실행 및 검증

- 표준 생성 LLM 개발 실행은 WSL 가상환경을 활성화한 뒤 `dev/docker-up-llamacpp-wsl.sh`를 사용한다.

```bash
cd '/mnt/c/Users/Laptop PC/Desktop/tax_assistant'
source venv-wsl/bin/activate
bash dev/docker-up-llamacpp-wsl.sh
```

- 스크립트는 Windows Ollama 임베딩 주소와 Docker GPU runtime을 검사하고 llama.cpp Compose overlay를 적용한다.
- Ollama 생성 LLM로 되돌릴 때만 `dev/docker-up-wsl.sh`를 사용한다.
- 전체 백엔드 테스트는 최신 이미지에서 실행한다.

```bash
docker exec tax_backend pytest -q
```

- DB 스키마 변경은 수동 SQL 적용이 아니라 Alembic revision으로 작성한다.
- 데이터 전체 재수집, 삭제, 대규모 백필처럼 기존 상태를 바꾸는 작업은 범위를 확인한 후 실행한다.

## 작업 종료 규칙

- 구현과 관련 테스트를 완료한다.
- `git diff --check`를 실행한다.
- 아키텍처, 실행법, 현재 상태 또는 다음 작업이 달라졌다면 `docs/ai/` 문서를 갱신한다.
- 미완료 작업이나 데이터 보정 필요 사항은 `docs/ai/HANDOFF.md`에 구체적으로 남긴다.
