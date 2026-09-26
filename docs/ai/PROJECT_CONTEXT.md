# 프로젝트 공통 컨텍스트

## 버전별 법령 Knowledge Graph (2026-09-25)

- PostgreSQL `law_history`의 보존 XML이 원본이다. Neo4j의 `TaxProvision`은 스냅샷별 조·항·호·목을 식별하고 `CHILD_OF`로 계층을 보존한다.
- 명시적 따옴표 정의와 정식 법령명 조문 인용은 `KnowledgeAssertion` 후보로 추출한다. `reviewed` 관계만 과거 법령 RAG에 연결하며 검색 시 원문 해시와 실제 발췌를 재확인한다. 법적 의미·사건 적용시점의 자동 검증은 아니다.
- 현재 현행 채팅은 기존 CITES GraphRAG, 버전 지정/기준일 과거 채팅은 검수된 Knowledge Graph 보충을 사용한다. 수집 완료된 과거 5,400개 스냅샷의 구조·관계 후보 백필은 끝났지만, 자동 추출 후보는 법적 검수 완료 관계가 아니다. 상세 운영은 `docs/TAX_KNOWLEDGE_GRAPH.md`.

## 생성 모델 작업별 설정 (2026-09-25)

- `app/services/llm_client.py`는 `answer`, `history_answer`, `citation_extraction`, `query_classification`, `tool_selection`, `document_classification`의 고정된 호출 목적별 설정을 선택한다.
- 기본은 6개 모두 `LLM_PROVIDER`/`CHAT_MODEL`을 상속해 OpenRouter `openai/gpt-6-luna`를 사용한다. 작업별 `LLM_TASK_<NAME>_*` 설정으로 provider·모델·endpoint·추론 수준·thinking·timeout·temperature·출력 예산을 분리할 수 있다.
- 로컬 Ollama 작업은 `THINK_ENABLED`로 thinking을 제어하며 원격 모델의 `REASONING_EFFORT`를 Ollama에 적용한다고 주장하지 않는다. 법령·계산 근거 검증은 모델 선택과 독립적으로 유지한다.

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
- 로컬 Ollama 생성·v1 임베딩과 선택형 OpenRouter 원격 생성, 향후 재도입 가능한 llama.cpp provider 코드
- DB 세율표 기반 세금 계산기 tool calling
- 답변의 법령 인용과 계산 금액을 검증하는 citation guard
- JWT httpOnly 쿠키 인증, 대화 관리, 세무 일정, PDF 업로드
- Alembic, Docker Compose healthcheck, pytest 및 RAG 골든셋 평가
- `evaluation/`: 정답·hard negative·검수 상태를 분리한 요소별 평가. 독립 실행기 `scripts/evaluate.py`, 합성 계약과 실제 세무 품질 점수 구분, 인간 루브릭 검수 및 재현 가능한 실행 기록.

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
            ├─ llm_client: Ollama·llama.cpp·OpenRouter 생성 어댑터
            └─ citation_guard: 생성 결과 검증
        → PostgreSQL + pgvector
        → Ollama v1 임베딩 / 생성은 설정에 따라 Ollama·OpenRouter·llama.cpp
```

주요 컨테이너:

| 컨테이너 | 역할 |
|---|---|
| `tax_backend` | FastAPI, Alembic 적용, 서비스 로직 |
| `tax_frontend` | React 빌드 결과를 제공하는 Nginx |
| `tax_pgvector` | PostgreSQL 17 + pgvector |
| `tax_pgadmin` | 개발용 DB 관리 UI |
| `tax_neo4j` | 공식 조문 인용·계열·관측 시점 그래프, 선택형 GraphRAG |
| `tax_law_history_worker` | 선택형 history profile 배치: 미수집 구법 재개 → 전체 무결성 검수 → 종료 |
| `tax_law_history_indexer` | 선택형 history-index 배치: 파생 색인·History* 그래프·중복 제거 임베딩 |
| Windows Ollama | Qwen3 Embedding 4B v1 임베딩 서빙, 로컬 생성 선택 시 Qwen3.5-9B |

`tax_llama_chat`·`tax_llama_embedding`은 선택형 overlay를 실행할 때만 생성되며 현재는 없다.

생성 provider는 `LLMProvider` 규약을 구현하며 Ollama도 `ChatOllama` 없이 직접 HTTP로 연결한다.
현재 OpenRouter 생성은 유료 `openai/gpt-6-luna`를 선택하며 키와 결제 가능 상태가 필요하다.
추출·답변 호출 목적별 추론 정책과 원격 출력 상한(`LLM_REMOTE_MAX_TOKENS`, 기본 8192)을 적용한다.
Compose 실사용 채팅 tracing은 `.env`의 `CHAT_TRACING_ENABLED=true`로 활성화한다. LangSmith 평가 전송과 별개이며 계정 추적 할당량이 필요하다.
외부 생성 경로는 질문·대화 이력·검색 발췌문을 제공자에게 전송한다. 임베딩과 기존 벡터는 로컬에 유지한다.
`langchain-ollama`는 사용하지 않는다. `langchain-core`는 provider 위의 프롬프트·Runnable·Pydantic 출력 검증에 사용한다. 일반 생성·구조화 응답·스트리밍은 공통 facade를 통해 호출하며 생성 길이는 `max_tokens`로 전달한다.

## 4. 코드 책임

```text
app/core/security.py
  JWT 생성·검증 및 인증 쿠키

app/routers/
  HTTP 입력, 인증 dependency, 응답 모델

app/schemas/
  Pydantic 및 서비스 데이터 모델

app/schemas/ai_output.py
  LLM의 세목 분류·인용·계산기 선택 결과 스키마 (법적 사실 검증과 구분)

app/services/ai_pipeline.py
  ChatPromptTemplate, Runnable, PydanticOutputParser를 연결하는 provider 중립 계층

app/services/tools/
  provider 중립 JSON 도구 선택, 허용 목록·인자 검증·시간 제한·서버 사용자 ID 주입
  법령 원문 조회·사용자 문서 검색·계산기 6종을 한 질문당 하나 실행
  SSE tool 이벤트와 일반 응답 tools 배열로 UI 상태 전달, 최종 결과는 chat_logs.message JSON 저장

frontend/src/components/Chat/ToolCallCard.jsx
  도구 상태·결과 발췌문·법령 뷰어·계산기 프리필 연결 (본문은 텍스트 렌더링)

app/services/calculator/engine.py
  계산 실행·결과 포맷만 담당 (LLM 입력 추출은 tools/planner.py)

app/services/law/lookup_service.py
  API·검색·도구 공용 조문 조회와 항·호·목 본문 대조

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

evaluation/
  서비스에서 import하지 않는 평가 전용 cli/schema/scoring/adapters/runner와 버전 데이터셋.
  scripts/evaluate.py는 얇은 진입점이며 명령 처리는 evaluation/cli.py에 둔다.
  정답 파일을 모델 출력으로 덮어쓰지 않는다. 미판정·미수집·오류를 성공으로 처리하지 않는다.
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
- GraphRAG 코드 기본값은 false, 2026-09-25 로컬 배포는 사용자 요청으로 true. 기본 RAG 뒤 검증된 CITES 1-hop으로 고정 개수 제한 없이 추가 본문 합계 4,000자 이내에서 보충한다. 역방향은 동일 계열만, 3초/장애 시 기본 결과 유지. 원문/약칭 정의 버전은 PG와 대조하고 시점 질문·PDF·해석례 seed는 제외한다. 원문 단독 조회 도구는 확장하지 않는다. 과거 법령은 별도 그래프·근거 입력 예산을 사용한다.
- 사용자 PDF는 `user_id`로 격리한다.
- 유사도만으로 법적 권위를 결정하지 않고 법령 위계를 재정렬에 반영한다.
- LLM이 세액을 직접 계산하게 하지 않고 DB 세율표 기반 계산기를 사용한다.
- 내부 검색 결과가 충분할 때는 웹 검색을 실행하지 않는다.
- 정상 인용이 있는 답변에는 불필요한 structured-output 보정 호출을 추가하지 않는다.

## 7. 데이터와 마이그레이션 원칙

- 2026-09-22부터 과거 법령은 별도 `law_history` 스키마에 저장한다. 공식 법령 ID와 `(MST, 시행일)` 버전, 정제 원문 스냅샷·조문·부칙·수집 상태를 관리한다. 현행 law_articles/임베딩/Neo4j와 자동 혼합하지 않는다. 실행·한계: `docs/LAW_HISTORY.md`.
- 2026-09-24 역사 전용 임베딩·History* Neo4j·날짜/버전 채팅 경로 추가. 2026-09-25 수집 범위 전체 벡터 백필 127,838/127,838 완료. 조회 시 버전 단위 준비 상태를 검사한다. 시행일 후보 조회는 사건 적용 법령 확정이 아니다. `docs/HISTORY_RAG.md`.

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

- 평가 UI는 LangSmith 사용: `evaluation/LANGSMITH.md`. 자체 대시보드는 제거했다. `scripts/evaluate.py langsmith prepare/publish`로 선택한 결과만 전송하고 원본 평가 규약은 로컬에 유지한다. 서비스 채팅은 별도 루트 실행으로 LangSmith 추적을 활성화한다. 실제 키를 Git에 커밋하지 않는다.

- 전체 기능·실행·트러블슈팅: `README.md`
- 배치 CLI: `scripts/README.md`
- 현재 진행 상태: `docs/ai/CURRENT_STATUS.md`
- 설계 결정: `docs/ai/DECISIONS.md`
- 세션 인수인계: `docs/ai/HANDOFF.md`
