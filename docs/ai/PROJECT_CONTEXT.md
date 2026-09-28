# 프로젝트 공통 컨텍스트

## 과거 연도가 있는 일반 상담의 답변 범위 (2026-09-28)

- 사건 연도만으로 시행 중이던 법령 버전을 하나로 확정하지 않는다. 현행 공식 원문은 당시 적용 법령으로 승격하지 않는다.
- 확보한 원문 자체의 일반 기준은 `source_summary`로 출처 시행 시점과 당시 적용 미확정을 명시해 설명할 수 있다. 개별 사건에 대한 법적 적용 주장은 확인된 역사적 버전이 없으면 계속 차단한다. 단일 주체·세목의 요건과 예외는 한 쟁점으로 묶고 미답변 문구는 중복하지 않는다.

## 2026-09-28 일반 질문 보류 문제 수정

- 일반 설명을 계산·원문·개인 문서 도구로 오분류하는 조건을 축소했다. 금융소득 세액 요청은 지원하지 않는 사업소득 계산으로 처리하지 않고 구체적 조건·기능 범위를 안내한다.
- 생성·의미 검증은 쟁점별로 실행하며, 짧은 원문 구간 ID를 실제 출처/인용문으로 서버에서 연결한다. 독립 쟁점의 오류 및 인용 ID 오류가 다른 정상 주장까지 차단하지 않도록 격리한다.
- 누락된 현행 조문은 동일 MST·법령명·시행일의 보관 XML 해시와 메타데이터를 확인한 뒤 읽기 전용으로 복구한다. 검색·원문 뷰어가 이 경로를 공유한다. 공식 아카이브에서 최신 버전을 임의 선택하거나 전체 DB를 재수집하지 않는다.

## 2026-09-28 질문·근거·주장 검증

- 일반 분석/복합 채팅은 `QuestionPlan` → 쟁점별 검색/도구 정책 → `EvidenceRecord` → `AnswerClaim` → 검사/조립을 사용한다. 기존 Ollama 임베딩과 OpenRouter GPT-6 Luna를 유지한다.

## 2026-09-28 복합 질문의 쟁점별 근거 검색

- 기존 주체×세목 분해, 명시적 원문 조회·계산·사용자 문서 도구 구분을 유지한다. 분석 쟁점마다 원래 범위를 보존한 두 검색 질의와 공식 조문 키워드 검색을 수행하고, 벡터·키워드 후보를 원본 조문 식별자로 합친다. 직접 조문 조회와 검증된 GraphRAG 확장도 유지한다.
- 쟁점별 공식 자료의 관련성과 필요한 법적 요건을 별도 구조화 Judge로 잠정 판정한다. 부족한 쟁점만 부족 요건으로 한 번 더 검색한다. Judge 오류나 위조된 근거 ID는 `unverified`로 처리하며 법적 주장 공개를 막는다. 쟁점 전체가 `missing`이어도 개별 주장에 검증된 공식 근거가 있고 별도 의미 Judge가 지지하면 그 부분만 공개한다. 이 판정은 세무 정확성의 독립 입증이 아니다.
- 답변 입력은 근거 단위 전체를 쟁점별 순환 순서로 배분한다. 충분하다고 판정한 쟁점의 관련 근거가 예산 때문에 모두 빠지면 해당 쟁점을 `missing`으로 낮춘다.
- 공식 법령 원본 ID·시행일·해시를 보존하며 사용자 문서 본문 표식으로 공식 출처를 만들지 않는다. 코드 검사에 실패한 주장과 의존 결론은 전송 전에 제외한다. 근거 패널은 당시 사용한 스냅샷을 표시한다.
- Judge는 기본 비교 평가(shadow)이며, enforce 운영 승격에는 독립 전문가 골드 교정이 필요하다. 기존 과거법령 경로는 별도로 유지한다. 구현·설정·검증 범위: `RELIABILITY_WORKFLOW.md`.

## 2026-09-28 GraphRAG 실행 의존성

- 현행 CITES와 과거 법령 그래프는 같은 Neo4j 서비스에 의존한다. 활성화 설정만으로 실제 확장을 보장하지 않으며, 그래프 장애 시 기본 검색 결과를 유지한다.
- WSL 백엔드 기동 스크립트는 GraphRAG가 활성화되면 Neo4j를 먼저 준비시키고, `/api/health/dependencies`는 그래프 연결 여부를 별도로 보고한다. `/api/health/ready`는 핵심 PostgreSQL 준비 상태를 유지한다.

## 2026-09-27 호스트 접속 포트

- Docker 공개 접속은 프런트엔드 `localhost:3001`, 백엔드 `127.0.0.1:8001`이다. 컨테이너 내부 백엔드 포트 `8000`과 Nginx의 `backend:8000` 프록시는 유지한다. 선택형 llama.cpp 생성 서버의 호스트 포트는 충돌을 피하도록 `8004`, 내부는 `8080`이다.

## 2026-09-26 문서 업로드 프런트엔드

- 내 문서 화면은 PDF·DOCX·HWPX·PPTX·HTML/HTM을 선택 또는 끌어놓기로 한 파일씩 업로드한다. 브라우저에서 확장자·빈 파일·50MB 제한을 먼저 확인하지만 서버 검증은 유지한다.
- 업로드 결과에 청크 수·OCR 쪽 수를 표시한다. 새 청크는 `chunking_version=2`로 표시하며 이전 문서는 재업로드 전까지 기존 청킹이라고 알린다. 이 표시는 검색 정확도나 문서 값 검증을 뜻하지 않는다.

## 2026-09-26 사용자 문서 구조화 청킹

- 형식별 추출기는 `DocumentBlock`에 원문·종류·페이지/슬라이드/구역·제목·표/행·OCR 여부를 기록한다. `structured_chunker.py`는 확인된 구조 경계를 우선하고 긴 단위만 토큰 상한으로 분리한다. 명시적 법령 조/항/호는 업로드 문서의 검색 단위이지 공식 법령 DB의 권위를 대체하지 않는다.
- 새 업로드 청크는 기존 `documents.metadata` JSONB에 위치 정보를 저장하며, 사용자 소유 필터와 Qwen3 임베딩 경로는 유지한다. 도구·RAG 컨텍스트는 확인된 위치만 표시한다. 스키마 변경은 없고 기존 업로드는 재업로드 전까지 자동 재청킹되지 않는다.
- PDF 및 스캔 OCR의 표 셀 인식, 숫자 정확도, HWPX 스타일 제목 판별은 보장하지 않는다. 문서 RAG 검색 품질은 형식별 골든셋으로 별도 검증해야 한다.

## 2026-09-26 다중 형식 문서 RAG

- 업로드는 PDF(텍스트·스캔 OCR), DOCX, HWPX, PPTX, HTML/HTM으로 제한한다. 형식별 추출을 `app/services/document/extractors.py`에 분리하고 기존 청킹·임베딩·사용자별 검색에 연결한다. ZIP/XML 해제와 OCR에 처리 한도를 둔다.
- PDF OCR은 텍스트가 부족한 페이지에만 한국어·영어 Tesseract로 수행한다. 추출 결과와 문서 형식을 청크 메타데이터에 기록하며, 파일명·사용자 소유권 필터가 작동하도록 JSONB 객체로 저장한다. 원본 HTML은 브라우저에서 실행되지 않도록 첨부 다운로드한다.
- OCR 결과는 검색 후보이지 금액·날짜 검증이 아니다. 구형 바이너리 HWP 및 오피스 문서 내부 이미지 OCR은 지원하지 않는다. 이전에 원본을 보관하지 않은 문서는 재업로드해야 한다.

## 2026-09-26 상담 이후 업무 확장

- 사용자별 상담 보고서는 저장된 입력·서류 상태·참고 계산을 요청 시 PDF로 생성한다. 신고서나 법적 적합성 보증서가 아니다.
- 새 사용자 문서 업로드는 원본을 `user_document_files`에 저장한다. PDF 검토 화면의 금액·날짜 추출은 후보 제시만 하고, 사용자 확인 금액만 원본 SHA-256과 함께 저장해 연결된 상담에 명시적으로 적용한다. PDF의 검색용 OCR과 검토값 확정은 별개이며 과거 업로드 원본은 소급 복원하지 않는다.
- 상담 계산 시나리오는 당시 입력·조회 기준일·계산 결과의 불변 스냅샷이다. 법령 탐색은 수집된 과거 버전과 검수된 원문 인용 관계만 보여주며 미수집 버전을 현행법으로 대체하지 않는다.
- 개인 세무일정은 공식 게시 항목을 사용자가 선택하여 준비 상태를 기록한다. 화면의 다가오는 목록은 알림 발송이나 신고 완료 확인이 아니다.

## 세목별 상담 확장 (2026-09-26)

- `app/services/consultation_catalog.py`가 6개 지원 세목의 추가 질문·권장 서류 목록을 정의한다. `consultation_cases.kind`와 `reference_date`는 Alembic `20260926_0007`로 확장했다. 종합소득세 기존 상담은 유지한다.
- 지원 세목: 종합소득세, 양도소득세, 상속세, 증여세, 부가가치세, 가산세. 각 세목은 기존 결정적 계산기를 호출하며 조회 기준일 이전 최신 DB 세율·공제 자료를 사용한다. 코드에 고정된 계산 상수는 시점별 버전 관리되지 않으므로 과거 사건의 법적 적용 보장이 아니다.
- 프런트엔드는 세목 선택 → 유형별 질문(금액·인원·선택·예/아니요) → 유형별 서류 체크리스트 → 계산 결과·자료 시행일·근거 문의를 제공한다. 문서 내용의 금액·적격 여부, 법적 사건 시점은 자동 검증하지 않는다.

## 종합소득세 상담 작업 공간 (2026-09-26)

- `/api/consultation-cases`와 React `CasesScreen`이 로그인 사용자 소유의 상담을 관리한다. 상담에는 귀속연도·원 질문·대화 ID·추가 질문 답변·서류 체크리스트·계산 스냅샷을 보관한다.
- 추가 질문 4개는 계산기에 필요한 총수입, 필요경비, 기본공제 인원, 기타 소득공제이다. 0과 미입력을 구분하며, 입력 수정 시 이전 계산을 무효화한다. 향후 다른 상담 유형의 질문·서류 규칙을 그대로 재사용하지 않는다.
- PDF는 기존 사용자 문서 라이브러리의 파일명으로 연결한다. 원문에서 숫자나 자격을 자동 추출·확정하지 않는다. 연결 문서가 삭제되거나 변경되면 재확인 상태로 표시한다.
- 계산은 귀속연도 말일 기준으로 DB 세율·공제 자료를 조회하고 실제 사용한 시행일을 보여준다. 단순 참고 계산이며 법적 적용 시점, 경과규정, 신고세액을 확정하지 않는다. 채팅의 근거 설명 역시 별도 법령 검증이 필요하다.

## 관계 평가 배치 (2026-09-26)

- `evaluation/kg_relation_review.py --auto`는 법률·시행령·시행규칙과 과거·최근 버전에서 관계 카드를 결정론적으로 추출한다. `--as-of` 이후 시행 버전은 제외한다. 교란 대상 카드는 미검수 후보이며 인간 정답이 아니다.
- `evaluation/kg_relation_judge.py`는 `KG_JUDGE_*` 전용 설정으로 평가 모델을 선택하고 카드별 진행을 원자적으로 저장해 같은 입력·설정으로 재개한다. 제공자가 돌려준 사용량만 기록하며 없으면 비용을 알 수 없다고 표시한다. `kg_relation_score.py`의 품질 점수에는 독립적인 인간 골드가 필요하다.
- `evaluation/kg_relation_human_review.py`는 Judge 판정과 후보 생성 유형을 숨긴 블라인드 양식을 만든다. 인간이 명시적 관계 문구 라벨과 대상 버전 시점 상태를 별도 기록한 후에만 골드 형식으로 변환한다. 평가 결과는 Neo4j 승인과 실서비스 RAG 설정을 자동 변경하지 않는다.

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
- JWT httpOnly 쿠키 인증, 대화 관리, 세무 일정, 다중 형식 사용자 문서 업로드
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
