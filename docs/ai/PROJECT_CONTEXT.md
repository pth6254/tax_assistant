# 프로젝트 공통 컨텍스트

마지막 구조 검토: 2026-08-01

## 1. 프로젝트 목적

대한민국 세무 법령에 특화된 Agentic RAG 기반 AI 어시스턴트다. 일반적인 답변 생성보다
공식 법령 근거의 정확성, 법령 위계, 계산의 결정성, 민감 데이터의 로컬 처리를 우선한다.

초기 n8n 프로토타입에서 이미지형 PDF 처리, 조문 단위 검색, 법령 위계 반영, 인용 검증의
한계를 확인한 뒤 FastAPI 기반 코드 구조로 전면 재설계했다.

## 2. 핵심 기능

- 국가법령정보 API에서 법률·시행령·시행규칙·법령해석례 수집
- 법령 XML을 조문 단위로 파싱하고 SHA-256 해시로 개정 감지
- 조·항·호·목 및 가지번호 구조화와 실제 본문 대조
- PostgreSQL·pgvector 기반 법령 및 사용자 PDF 하이브리드 검색
- 법률 → 시행령 → 시행규칙 → 유권해석 → 사용자 문서 순의 근거 우선순위
- 내부 검색 품질이 부족할 때만 공공기관 중심 웹 검색
- 현재 Ollama 기반 로컬 생성·v1 임베딩, 향후 재도입 가능한 llama.cpp provider 코드
- DB 세율표 기반 세금 계산기 tool calling
- 답변의 법령 인용과 계산 금액을 검증하는 citation guard
- JWT httpOnly 쿠키 인증, 대화 관리, 세무 일정, PDF 업로드
- Alembic, Docker Compose healthcheck, pytest 및 RAG 골든셋 평가

## 3. 런타임 구조

```text
React + Nginx
    → FastAPI routers
        → services
            ├─ law: 수집·XML 파싱·법령 참조/본문 구조화
            ├─ search: 법령·PDF 검색과 조건부 웹 검색
            ├─ calculator: 결정론적 세금 계산
            ├─ document: PDF 추출·청킹
            ├─ chat_service: RAG 오케스트레이션
            ├─ llm_client: llama.cpp OpenAI 호환 API·Ollama 어댑터
            └─ citation_guard: 생성 결과 검증
        → PostgreSQL + pgvector
        → 현재 Ollama 생성·v1 임베딩 / 선택형 llama.cpp 생성·v2 임베딩
```

주요 컨테이너:

| 컨테이너 | 역할 |
|---|---|
| `tax_backend` | FastAPI, Alembic 적용, 서비스 로직 |
| `tax_frontend` | React 빌드 결과를 제공하는 Nginx |
| `tax_pgvector` | PostgreSQL 17 + pgvector |
| `tax_pgadmin` | 개발용 DB 관리 UI |
| Windows Ollama | 현재 Qwen3.5-9B 생성·Qwen3 Embedding 4B v1 임베딩 서빙 |

`tax_llama_chat`·`tax_llama_embedding`은 선택형 overlay를 실행할 때만 생성되며 현재는 없다.

## 4. 코드 책임

```text
app/core/security.py
  JWT 생성·검증 및 인증 쿠키

app/routers/
  HTTP 입력, 인증 dependency, 응답 모델

app/schemas/
  Pydantic 및 서비스 데이터 모델

app/services/law/reference_parser.py
  사용자 입력의 법령명·조·항·호·목 참조 파싱과 표준화

app/services/law/structure_parser.py
  저장된 조문 본문에서 요청한 항·호·목의 존재 여부와 본문 추출

app/services/law/parser_service.py
  국가법령정보 XML을 LawArticle로 변환하고 항·호·목 원문 보존

app/services/law/clause_splitter.py
  긴 조문의 항 단위 보조 임베딩용 분할

app/services/search/hybrid_search_service.py
  법령·PDF 검색, 조문 직접 조회, 법령 위계 재정렬

scripts/
  수집·동기화·백필·평가 CLI 진입점. 핵심 로직은 services에 둔다.
```

## 5. 법령 도메인 불변 규칙

- `제59조의4`는 제59조의 가지번호 4이며 `제59조 제4항`이 아니다.
- 조 가지번호는 `article_branch`, 항은 `paragraph`로 반드시 분리한다.
- `제1호의2`의 가지번호는 `item_branch`에 저장한다.
- 원문 항 기호 `①`~`㉟`은 숫자 항과 상호 변환한다.
- 법률·시행령·시행규칙에도 동일한 조·항·호·목 구조를 적용한다.
- 사용자의 참조 파싱과 실제 본문 존재 검증은 별도 단계다.
- 조문이 존재해도 요청한 항·호·목이 없을 수 있다. 이 경우 조 전체 404가 아니라
  `target.exists=false`와 실패한 `level`을 반환한다.
- 법령 인용은 생성 모델의 문장이 아니라 공식 데이터와 대조해야 한다.

## 6. 검색 및 생성 원칙

- 질문에 법령명과 조문번호가 있으면 벡터 검색보다 직접 조회 fast path를 우선한다.
- 사용자 PDF는 `user_id`로 격리한다.
- 유사도만으로 법적 권위를 결정하지 않고 법령 위계를 재정렬에 반영한다.
- LLM이 세액을 직접 계산하게 하지 않고 DB 세율표 기반 계산기를 사용한다.
- 내부 검색 결과가 충분할 때는 웹 검색을 실행하지 않는다.
- 정상 인용이 있는 답변에는 불필요한 structured-output 보정 호출을 추가하지 않는다.

## 7. 데이터와 마이그레이션 원칙

- DB 스키마의 기준은 Alembic이다.
- `db/init.sql`과 `db/migrations/`는 최초 legacy baseline이 채택하는 자료이며 신규 변경을
  직접 추가·실행하는 표준 경로가 아니다.
- 신규 스키마 변경은 새 Alembic revision으로 작성한다.
- 법령 개정은 `(법령명, 조문번호)` 그룹의 콘텐츠 해시 집합으로 판단한다.
- 전체 재수집이나 임베딩 백필은 시간이 오래 걸리고 DB 상태를 바꾸므로 명시적으로 실행한다.

## 8. 개발환경 주의사항

- Windows Ollama는 WSL2 재시작 시 주소가 바뀔 수 있다.
- IP를 코드나 Compose에 하드코딩하지 않는다.
- `dev/docker-up-wsl.sh`가 Windows 게이트웨이를 탐지해 `OLLAMA_WINDOWS_IP`를 설정하고
  필수 모델을 확인한 뒤 Compose를 실행한다.
- 운영 환경에서는 Docker 서비스명 또는 사설 DNS 기반 Ollama endpoint를 사용한다.
- `.env`의 실제 값은 문서, 로그, 답변에 노출하지 않는다.

## 9. 더 자세한 문서

- 전체 기능·실행·트러블슈팅: `README.md`
- 배치 CLI: `scripts/README.md`
- 현재 진행 상태: `docs/ai/CURRENT_STATUS.md`
- 설계 결정: `docs/ai/DECISIONS.md`
- 세션 인수인계: `docs/ai/HANDOFF.md`
