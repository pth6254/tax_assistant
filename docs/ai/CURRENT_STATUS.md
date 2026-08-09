# 현재 구현 상태

기준일: 2026-08-10

이 문서는 세션 간 작업 맥락을 전달하는 상태판이다. 완료 여부가 의심되면 실제 코드,
`git status`, 테스트 결과를 우선 확인한다.

## 1. 구현 완료

- FastAPI·React 기반 세무 상담 UI와 SSE 스트리밍
- JWT httpOnly 쿠키 인증과 사용자·대화 관리
- 국가법령정보 법률·시행령·시행규칙 수집
- 법령해석례 수집 및 법령 검색 경로 통합
- 조문 단위 저장, 개정 해시 감지, 현재 버전 필터링
- pgvector와 키워드 검색을 결합한 하이브리드 검색
- 법령 위계 기반 우선순위 재정렬
- 조문번호 직접 조회 fast path
- 조·항·호·목 및 조/호 가지번호 구조화
- 실제 조문 본문에서 항·호·목 존재 여부와 본문 추출
- 긴 조문의 항 단위 보조 임베딩
- PDF 업로드, 법령형 청킹, 사용자별 문서 격리
- 조건부 Tavily 웹 검색
- 세금 계산기 6종과 tool calling
- 조문 인용·계산 수치 citation guard
- 세무 신고 일정
- Ollama 로컬 모델 연동 및 WSL 호스트 자동 탐지
- liveness·readiness·dependency healthcheck
- Alembic legacy baseline과 Docker 시작 시 `upgrade head`
- 수집·동기화·백필·RAG 평가 CLI
- 채팅 실행 전 `conversation_id`와 로그인 사용자의 소유권 검증
- AI Markdown 응답을 DOMPurify로 정화한 뒤 렌더링
- Docker 빌드 컨텍스트에서 `.env`와 `.env.*` 제외

## 2. 최근 구현 및 검증 상태

최근 작업은 법령 참조 구조화와 다중 사용자 보안 보강이다.

- `reference_parser.py`: 법률·시행령·시행규칙의 조·항·호·목 참조 파싱
- `structure_parser.py`: 요청한 항·호·목의 실제 본문 추출과 실존 여부 반환
- `parser_service.py`: 국가법령정보 XML의 `<항>`, `<호>`, `<목>` 보존
- `LawArticleDetail`: 구조화된 `reference`와 본문 대조 `target` 응답
- 실제 국가법령정보 XML에서 `소득세법 제59조의4 제9항 제2호 가목` 추출 확인
- `require_conversation_owner`: 일반·SSE 채팅 모두 응답 시작 전에 대화 소유권 확인, 타인 소유·잘못된 UUID는 동일한 404 반환
- `MessageBubble.jsx`: `marked` 변환 결과를 DOMPurify로 정화하여 저장형 XSS 차단
- `.dockerignore`: `.env`, `.env.*` 제외 및 `.env.example`만 예외 허용
- `dev/docker-up-wsl.sh`로 backend·frontend 재빌드 및 DB·Alembic·Ollama dependency `ready` 확인
- 현재 backend 이미지의 `/app/.env` 부재 확인
- 마지막 보고된 전체 테스트: `278 passed`

검증 명령은 항상 현재 코드로 다시 실행한다. 위 숫자는 영구 기준이 아니라 마지막 확인 기록이다.

## 3. 현재 작업 트리 주의

2026-08-10 확인 시 보안 보강 관련 변경이 아직 작업 트리에 존재했다. 새 세션은 반드시
`git status --short`와 `git diff`를 먼저 확인하고 사용자 변경을 덮어쓰지 않는다.

주요 변경 가능 파일:

- `.dockerignore`
- `app/services/conversation_service.py`
- `app/routers/chat.py`
- `app/routers/conversations.py`
- `frontend/src/components/Chat/MessageBubble.jsx`
- `frontend/package.json`, `frontend/package-lock.json`
- `tests/test_api_chat.py`

## 4. 남은 우선순위

1. 추출된 `target.text`를 직접 조문 RAG 컨텍스트에 우선 반영
2. 기존 법령 데이터 재수집 및 임베딩 갱신
3. citation guard를 조 번호에서 항·호·목 검증까지 확장
4. 프런트엔드 조문 뷰어에서 대상 항·호·목 강조 및 자동 스크롤
5. 한 질문에 포함된 복수 법령 참조 동시 추출·조회
6. 실제 법률·시행령·시행규칙 XML fixture 회귀 테스트 확충
7. 장기적으로 항·호·목을 별도 구조화 테이블 또는 JSONB로 저장
8. 전체 데이터 갱신 후 RAG 골든셋 재평가

## 5. 알려진 제한과 데이터 보정

- 새 XML 파서는 호·목을 보존하지만 과거 파서로 수집한 기존 DB 행에는 호·목이 빠져 있을 수 있다.
- 전체 반영에는 `python scripts/sync_laws.py --embed`가 필요하다.
- 전체 동기화는 DB와 임베딩을 변경하는 장시간 작업이므로 사용자 동의와 Ollama 상태 확인 후 실행한다.
- 현재 citation guard는 조문번호 중심이며 구조화된 항·호·목 검증은 다음 단계다.
- API의 `target` 응답이 프런트엔드 강조 UI에 완전히 연결됐는지 별도 확인이 필요하다.

## 6. 다음 작업 시작 체크리스트

```text
[ ] git status --short 확인
[ ] AGENTS.md와 docs/ai 문서 확인
[ ] 관련 코드와 테스트 확인
[ ] 필요 시 dev/docker-up-wsl.sh로 최신 이미지 빌드
[ ] 변경 범위 테스트 후 전체 pytest
[ ] git diff --check
[ ] CURRENT_STATUS/HANDOFF 갱신
```
