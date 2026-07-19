# 세무 AI 어시스턴트

> 대한민국 세무 법령에 특화된 **Agentic RAG 기반 AI 어시스턴트**  
> 공식 법령 조문 DB + PDF 업로드 + 웹검색을 결합하여 법적 근거가 포함된 세무 답변을 제공합니다.

---

## 목차

1. [프로젝트 소개](#1-프로젝트-소개)
2. [주요 기능](#2-주요-기능)
3. [데모](#3-데모)
4. [시스템 아키텍처](#4-시스템-아키텍처)
5. [Agentic RAG 파이프라인](#5-agentic-rag-파이프라인)
6. [기술 스택](#6-기술-스택)
7. [프로젝트 구조](#7-프로젝트-구조)
8. [시작하기](#8-시작하기)
9. [테스트](#9-테스트)
10. [환경 변수](#10-환경-변수)
11. [API 엔드포인트](#11-api-엔드포인트)
12. [사용 예시](#12-사용-예시)
13. [핵심 구현 포인트](#13-핵심-구현-포인트)
14. [보안 설계](#14-보안-설계)
15. [트러블슈팅](#15-트러블슈팅)
16. [한계 및 개선 과제](#16-한계-및-개선-과제)
17. [라이선스](#17-라이선스)

---

## 1. 프로젝트 소개

### 해결하려는 문제

일반 LLM에 세무 질문을 하면 세 가지 문제가 발생합니다.

| 문제 | 설명 |
|------|------|
| **환각(Hallucination)** | 존재하지 않는 조문을 생성하거나 조문 번호를 틀리게 인용 |
| **근거 부족** | "~일 수 있습니다" 수준의 모호한 답변, 법령 조문 미인용 |
| **최신성 부족** | 학습 데이터 기준 이후의 개정 세법, 최신 예규·유권해석 미반영 |

### 해결 방법

```
공식 법령 조문 DB (국가법령정보 API, 법령 + 유권해석)
        +
사용자 업로드 PDF (시행령·집행기준 등)
        +
Tavily 웹검색 (최신 예규·판례)
        +
DB 세율표 기반 세금 계산기
        ↓
Agentic RAG 파이프라인 (검색 → 계산 → 합성 → 인용 검증)
        ↓
법령 조문 번호까지 명시하고 자동 검증까지 거친 근거 기반 답변
```

- **RAG**: 법령 벡터 DB를 먼저 검색하여 근거 없는 생성 차단
- **법령 위계 반영**: 법률 → 시행령 → 시행규칙 → 유권해석 → 집행기준 우선순위 적용
- **Agentic**: 세목 분류·검색 범위 축소를 스스로 판단하고, 계산 의도가 있으면 계산기를 직접 실행하며, 검색 유사도가 부족하면 웹검색으로 보완
- **인용 검증**: 답변 생성 후 조문 인용과 계산 수치를 실제 근거와 자동 대조하는 후처리 단계
- **로컬 LLM**: 세무 데이터를 외부 API에 전송하지 않고 온프레미스에서 처리

---

## 2. 주요 기능

### 법령 데이터 수집 및 검색

- **공식 법령 자동 수집**: 국가법령정보 Open API로 세법 관련 법령 전체 탐색·수집
  - 소득세법, 법인세법, 부가가치세법 등 22개+ 세목 분류
  - 법률·대통령령·총리령·부령 구분 저장
  - 조문 단위 임베딩으로 세밀한 검색 가능
- **PDF 업로드**: 집행기준, 세무 실무자료 등 직접 업로드
  - 파일명 패턴으로 법령 위계 자동 분류 (AI 호출 없이)
  - 800 토큰 청크 분할 + 100 토큰 오버랩
- **법령해석례(유권해석) 수집**: 국가법령정보 Open API(`target=expc`)로 기획재정부·국세청 등의 유권해석을 수집해 `law_articles`에 `law_type='법령해석례'`로 저장 (법령과 동일한 검색 경로 재사용). 세법 키워드 20개 전수 수집 기준 207건 확보
- **법령 개정 자동 동기화**: 이미 수집된 법령을 재수집해 조문 내용 변경(SHA-256 해시 비교)을 감지하고 구버전을 `is_current=FALSE`로 폐기, 최신 버전만 검색에 노출

### 하이브리드 검색

- `law_articles`(공식 법령 조문 + 유권해석)와 `documents`(업로드 PDF)를 동시 검색
- 법령 위계 기반 우선순위 정렬: 법률 → 시행령 → 시행규칙 → 유권해석 → PDF 문서
- 세목 필터링으로 관련 법령만 검색하여 정확도 향상
- 키워드로 세목이 명확히 확정되면 분류 LLM 호출 자체를 생략 (지연시간 단축)

### Agentic RAG 채팅

- **RAG 파이프라인**: 세목 분류 + 멀티쿼리 생성 → 하이브리드 벡터 검색(RRF 병합) → 리랭킹 → 조건부 웹검색 → 세금 계산기(조건부) → 최종 합성 → 인용 검증
- **비교 질문 처리**: "리스 vs 장기렌트"처럼 A vs B를 묻는 질문에 대해 각 항목별 법령 조문을 근거로 비교표 + 명확한 결론 제시
- **세금 계산기 tool calling**: 질문에서 계산 의도를 감지하면 LLM이 계산기 종류·입력값을 추출해 DB 세율표 기반 계산기를 실행, 계산 과정과 근거 조문을 답변에 반영
- **인용 검증(citation guard)**: 답변 생성 후 인용된 조문이 실제 검색 근거에 존재하는지, 계산기 결과 금액과 서술이 일치하는지 자동 대조해 근거 없는 인용에는 경고 각주 추가
- **인용 누락 자동 보정(structured output)**: 답변에 법령 인용이 하나도 없는 경우(temperature 샘플링에 따른 형식 이탈)에만 JSON Schema로 출력을 강제하는 별도 LLM 호출을 실행해 근거 조문을 추출·검증 후 답변에 덧붙임 — 정상 답변(대다수)에는 추가 지연 없음
- **SSE 스트리밍**: 토큰 단위 실시간 응답(LangChain `ChatOllama` 경유), DB 저장은 백그라운드 처리
- **대화 메모리**: 최근 3턴 컨텍스트 유지, 대화별 독립 세션(conversations 테이블)
- **Tavily 웹검색**: 국세청·법제처·기획재정부 도메인 중심 최신 자료 보완 (DB 상위 3개 평균 유사도 0.55 미만인 경우에만 실행)

### 세금 계산기

- 종합소득세·양도소득세·상속세·증여세·부가가치세·가산세(무신고·과소신고·납부지연) 6종, DB 세율표(`tax_brackets`/`tax_deductions`) 기반 계산
- 계산 단계·근거 조문을 함께 반환, 프론트 계산기 화면과 챗봇 tool calling 양쪽에서 재사용
- **계산기 ↔ 챗봇 왕복 연결**: 챗봇이 계산기를 실행하면 답변에 "계산기에서 조건 바꿔보기" 버튼(입력값 프리필), 계산기 결과에서 "이 결과에 대해 챗봇에게 질문하기" 버튼으로 상호 이동

### 세무 일정 관리

- 사업자 유형(법인/개인 일반과세/개인 간이과세)에 따른 부가가치세·종합소득세·원천세 신고 기한을 규칙 기반으로 계산 (LLM 미사용)
- 프로필 화면에서 사업자 유형 설정 시 다가오는 신고 기한이 D-day와 함께 표시

### 조문 원문 뷰어

- 답변에 인용된 "[법률] 소득세법 제55조" 등의 조문을 클릭하면 사이드패널에 DB의 조문 원문이 열림
- 검증된 인용을 눈으로 직접 확인할 수 있는 UX로 "근거 기반 답변"을 체감 가능하게 함

### RAG 품질 평가 도구

- `scripts/eval_rag.py`: 골든 평가셋 기반으로 검색 hit-rate·MRR·세목 분류 정확도·인용 정확도를 측정하고 이전 실행과 자동 비교(회귀 감지)
- 파라미터(임계값, 프롬프트 등) 변경 시 효과를 수치로 검증 가능
- `--repeat N` 옵션으로 동일 평가를 반복 실행해 생성 품질 지표의 샘플링 편차와 실행마다 결과가 바뀌는 비결정적 항목을 확인 가능

### 기타

- JWT httpOnly 쿠키 기반 인증
- React 채팅 UI (마크다운 렌더링)

---

## 3. 데모

| 화면 | 설명 |
|------|------|
| ![로그인](./assets/demo_login.png) | 이메일·비밀번호 로그인 |
| ![업로드](./assets/demo_upload.png) | PDF 업로드 및 자동 분류 결과 |
| ![채팅](./assets/demo_chat.png) | 법령 근거 포함 세무 답변 |

> 이미지는 추후 추가 예정입니다.

---

## 4. 시스템 아키텍처

```mermaid
graph TD
    A[React Frontend<br/>Vite + React 18] -->|HTTP / SSE| B[FastAPI Backend]

    B --> C[routers/]
    C --> D[services/]
    D --> E[utils/]
    D --> F[(PostgreSQL<br/>+ pgvector)]

    D -->|Ollama REST API| G[Ollama<br/>qwen3.5:9b<br/>qwen3-embedding:4b]
    D -->|Tavily API| H[Tavily Search]
    D -->|국가법령정보 API| I[법령정보 Open API<br/>law + expc]

    F --> F1[documents<br/>PDF 청크 벡터]
    F --> F2[law_articles<br/>법령 조문 + 유권해석 벡터]
    F --> F3[chat_logs<br/>대화 메모리]
    F --> F4[users<br/>인증 + 사업자 유형]
    F --> F5[tax_brackets / tax_deductions<br/>세율표·공제 시드]
    F --> F6[conversations<br/>대화 세션]
```

### 계층 구조

```
HTTP 요청
  → routers/     입력 검증, 인증 확인, 응답 포맷
  → services/    비즈니스 로직, RAG 파이프라인
  → utils/       공통 기능 (JWT, 임베딩, PDF)
  → database.py  asyncpg 커넥션 풀 (싱글턴)
```

각 계층은 단방향으로만 호출됩니다.

---

## 5. Agentic RAG 파이프라인

### 법령 수집 흐름

```
국가법령정보 API 키워드 검색 (세법, 조세, 국세 등 20개 키워드)
  → 소관부처 필터링 (기획재정부, 행정안전부, 관세청 등)
  → MST 기반 중복 제거
  → 법령 원문 XML 조회
  → 조문 단위 파싱 (조문번호, 제목, 본문)
  → SHA-256 해시로 중복/개정 감지
  → law_articles 테이블 저장 (embedding = NULL)
  → qwen3-embedding:4b 임베딩 생성 (배치 50개)
  → 벡터 저장 완료
```

### 법령 개정 자동 동기화 흐름 (`scripts/sync_laws.py`)

```
law_articles에 이미 수집된 법령 목록 조회 (법령해석례 제외)
  → 각 법령 재수집 (법령 수집 흐름과 동일한 API 재호출)
  → 조문번호(article_no) 단위로 이번 수집분의 content_hash 집합 계산
  → 기존 is_current=TRUE 행 중 이번 수집분 해시 집합에 없는 것만 개정으로 판단해 폐기
     (같은 조문번호 아래 여러 콘텐츠가 공존할 수 있어 조문 단위가 아닌 그룹 단위로 비교)
  → 신규/변경분만 임베딩 (--embed 옵션)
```
cron·Windows 작업 스케줄러에 등록해 주기 실행하는 것을 전제로 하며, 실패 시 non-zero exit code를 반환합니다.

### 법령해석례(유권해석) 수집 흐름 (`scripts/ingest_interpretations.py`)

```
국가법령정보 API 키워드 검색 (target=expc)
  → 법령해석례 일련번호(case_id) 목록 확보
  → 건별 본문 조회 (질의요지·회답·이유)
  → 안건명의 「법령명」에서 관련 법령 추출 → 세목 추론
  → law_articles 테이블 저장 (law_type='법령해석례')
  → qwen3-embedding:4b 임베딩 생성
```

### 세금 계산기 tool calling 흐름

```
질문 입력
  → 계산 의도 키워드 게이트 (금액 표현 + "얼마"/"계산"/"세액" 등, LLM 호출 없음)
  → [계산 의도 있음] LLM 1회 호출로 {tool, params} 추출
     tool: income_tax | capital_gains | inheritance | gift
  → pydantic 스키마 검증
  → 계산기 실행 (DB 세율표 조회 → 단계별 계산 → 근거 조문)
  → 계산 결과를 RAG 컨텍스트에 병합해 최종 답변에 반영
  → (프론트) 답변에 "계산기에서 조건 바꿔보기" 버튼 노출 → 계산기 화면 프리필
```
RAG 검색과 병렬로 실행되어 지연시간을 추가하지 않으며, 실패 시 조용히 RAG-only로 진행합니다.

### PDF 업로드 흐름

```
PDF 업로드
  → PyPDF2 텍스트 추출
  → 파일명 패턴 분석 → (법률) / (대통령령) / (부령) 감지
  → AI 분류 (파일명으로 못 잡은 경우만 Ollama 호출)
     law_name: 소득세법, 부가가치세법 등
     category: 법령, 시행령, 시행규칙, 집행기준
  → 800 토큰 청크 분할 (100 토큰 오버랩)
  → qwen3-embedding:4b 임베딩 (배치 100개)
  → documents 테이블 저장
```

### 채팅 흐름

```
질문 입력
  │
  ├─ [병렬] 세목 분류 + 멀티쿼리 생성
  │    키워드로 세목이 하나로 확정 → LLM 호출 없이 원본 쿼리로 바로 검색
  │    키워드 미확정(0개 또는 다중 매칭) → LLM 1회 호출로 세목 분류 + 멀티쿼리 3개 생성
  │    (비교 질문이면 각 옵션별 쿼리 별도 생성)
  ├─ [병렬] 대화 메모리 조회 (최근 3턴, conversation_id 기준)
  └─ [병렬] 세금 계산기 실행 (계산 의도 감지 시에만 — 아래 "세금 계산기 tool calling" 참고)
  │
  → [fast path] 질문에 "법령명 제N조" 직접 언급 시 해당 조문 DB 직접 조회 → 최상위 배치
  → 멀티쿼리 임베딩 (qwen3-embedding:4b)
  → 하이브리드 벡터 검색 (law_articles 조문·항 벡터 + documents 동시 검색)
  → RRF(Reciprocal Rank Fusion) 병합 (복수 쿼리 결과 통합)
  → 법령 위계 정렬
     0순위: 법률    (law_articles, law_type=법률)
     1순위: 시행령  (law_articles, law_type=대통령령)
     2순위: 시행규칙 (law_articles, law_type=총리령/부령)
     3순위: 유권해석 (law_articles, law_type=법령해석례) / 법령 PDF
     4~7순위: 시행령·시행규칙 PDF, 집행기준, 기타 PDF (category 기준)
  → 리랭킹 (RERANK_MODEL 설정 시 Ollama /api/rerank 호출)
  │
  ├─ [조건부] 웹검색 (DB 상위 3개 평균 유사도 < 0.55인 경우만)
  │    Tavily 검색 (nts.go.kr, law.go.kr, moef.go.kr)
  │
  ├─ 최종 답변 합성 (SSE 스트리밍)
  │    내부 DB 법령 + 웹검색 결과 + 계산기 결과 통합
  │    → 토큰 단위 스트리밍 출력
  │
  ├─ 인용 검증(citation guard)
  │    답변 속 [법률]/[시행령]/[시행규칙] 인용이 검색 근거에 실존하는지 대조
  │    계산기 실행 시 답변 속 금액이 계산 결과와 일치하는지 대조
  │    불일치 시 답변 하단에 경고 각주 추가
  │
  └─ 대화 메모리 저장 (백그라운드 비동기 처리)
```

### 법령 위계 원칙

| 우선순위 | 구분 | 역할 |
|----------|------|------|
| 1 | 법률 | 최상위 근거, 반드시 인용 |
| 2 | 시행령 (대통령령) | 법령의 위임 사항, 구체적 기준 |
| 3 | 시행규칙 (총리령·부령) | 시행령의 위임 사항, 세부 절차 |
| 4 | 유권해석 (법령해석례) | 기획재정부·국세청 등 행정 해석, 법령과 충돌 시 법령 우선 |
| 5 | 집행기준·실무자료 | 참고용 (법적 구속력 없음) |

세법 일반 원칙도 프롬프트에 반영합니다.
- **특별법 우선**: 조세특례제한법이 일반 세법보다 우선 적용
- **신법 우선**: 같은 위계의 법령은 최신 개정령이 우선
- **엄격 해석**: 비과세·감면 요건은 명확한 조문 근거 필수

---

## 6. 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python 3.12, FastAPI, asyncpg |
| 프론트엔드 | React 18, Vite |
| 데이터베이스 | PostgreSQL 17 + pgvector |
| 인증 | JWT, httpOnly 쿠키, bcrypt |
| LLM | Ollama qwen3.5:9b (로컬), LangChain(`langchain-ollama`) 경유 — provider 교체 시 어댑터 계층만 교체 |
| 임베딩 | Ollama qwen3-embedding:4b (2560차원, 로컬) |
| 웹검색 | Tavily Search API |
| 법령 API | 국가법령정보 Open API |
| 컨테이너 | Docker Compose (pgvector/pgvector:pg17) |

> **로컬 모델 선택 이유**: OpenAI API 대신 Ollama를 사용하여 세무 데이터를 외부에 전송하지 않고, API 비용 없이 운영합니다.

---

## 7. 프로젝트 구조

```
tax-assistant/
│
├── main.py                      # 앱 진입점, 라우터 등록, DB 풀 생명주기
├── config.py                    # 환경변수 중앙 관리 (dotenv)
│
├── scripts/
│   ├── ingest_laws.py            # 법령 수집 CLI (수집/임베딩/재수집)
│   ├── ingest_interpretations.py # 법령해석례(유권해석) 수집 CLI
│   ├── sync_laws.py              # 법령 개정 자동 동기화 CLI (cron 등록 대상)
│   ├── backfill_law_type.py      # law_type 일괄 보정 (일회성 데이터 보정)
│   ├── embed_clauses.py          # 긴 조문 항(項) 단위 보조 임베딩 백필
│   └── eval_rag.py               # RAG 품질 평가 CLI (골든셋 기반 hit-rate/MRR 측정)
│
├── db/
│   ├── init.sql                  # Alembic 최초 baseline이 사용하는 레거시 기본 스키마
│   └── migrations/               # Alembic 최초 baseline이 채택하는 기존 SQL 마이그레이션
│
├── alembic/                      # DB 스키마 버전 관리 및 revision 파일
├── alembic.ini                   # Alembic 설정
│
├── tests/
│   ├── test_*.py                 # 단위·API 테스트 (pytest)
│   └── eval/
│       ├── golden_qa.json        # RAG 품질 평가용 골든 질문셋
│       └── results/              # eval_rag.py 실행 결과 이력 (회귀 비교용)
│
├── frontend/                    # React 프론트엔드 (Vite)
│   └── src/
│       ├── api/                  # FastAPI 호출 함수 (chatApi, calculatorApi, lawApi, taxScheduleApi 등)
│       ├── hooks/                # 상태 관리 커스텀 훅 (useChat, useAuth, useConversations)
│       └── components/
│           ├── Chat/             # 채팅 UI (ChatArea, ChatInput, MessageBubble, ArticleViewer)
│           ├── Calculator/       # 세금 계산기 화면 (CalculatorScreen, ResultCard)
│           ├── Profile/          # 프로필 + 세무 일정 위젯 (ProfileScreen)
│           ├── Sidebar/          # 화면 전환, PDF 업로드, 파일 목록
│           └── Auth/             # 로그인/회원가입
│
└── app/
    ├── routers/                  # HTTP 수신, 입력 검증, 인증 확인
    │   ├── auth.py               # POST /api/auth/signup, /login, /logout
    │   ├── users.py              # GET·PATCH·DELETE /api/users/me
    │   ├── conversations.py      # 대화 세션 CRUD
    │   ├── chat.py               # POST /api/chat, /api/chat/stream
    │   ├── upload.py             # POST /api/upload, 문서 목록/삭제
    │   ├── calculator.py         # POST /api/calculator/{income-tax,capital-gains,inheritance,gift,vat,penalty-tax}
    │   ├── law.py                # GET /api/law-articles/lookup (조문 원문 뷰어)
    │   └── tax_schedule.py       # GET /api/tax-schedule
    │
    ├── services/                 # 비즈니스 로직
    │   ├── auth_service.py       # 이메일 중복, bcrypt 해싱, JWT 발급, 프로필 조회/수정
    │   ├── chat_service.py       # Agentic RAG 파이프라인, 스트리밍, 세목 키워드 매칭
    │   ├── citation_guard.py     # 답변 인용·계산 수치 검증 후처리
    │   ├── llm_client.py         # LangChain ChatOllama 어댑터 (call_llm/stream_llm/call_llm_structured)
    │   ├── tax_schedule_service.py  # 사업자 유형별 신고 기한 규칙 기반 계산
    │   ├── upload_service.py     # PDF 파싱 → 분류 → 청크 → 임베딩 → 저장
    │   ├── calculator/
    │   │   ├── income_tax.py / capital_gains.py / inheritance.py / gift_tax.py / vat.py / penalty_tax.py  # 세목별 계산 로직
    │   │   ├── engine.py         # 챗봇 tool calling — 계산 의도 감지·파라미터 추출·실행
    │   │   ├── repository.py    # tax_brackets/tax_deductions 조회
    │   │   └── updater.py       # 법령 개정 감지 시 세율표 자동 갱신 (LLM 추출)
    │   ├── search/
    │   │   ├── hybrid_search_service.py  # law_articles + documents 하이브리드 검색, 조문 원문 조회
    │   │   └── web_search.py     # Tavily 웹검색 클라이언트
    │   └── law/
    │       ├── api_service.py         # 국가법령정보 API 클라이언트 (법령 + 법령해석례)
    │       ├── parser_service.py      # 법령 XML 조문 파싱 (절/관 표제·삭제 조문 필터링)
    │       ├── clause_splitter.py     # 긴 조문의 항(項) 단위 분할 (보조 임베딩용)
    │       ├── ingestion_service.py   # 법령 수집·저장·임베딩·개정 감지 파이프라인
    │       └── interpretation_service.py  # 법령해석례(유권해석) 수집·저장 파이프라인
    │
    ├── schemas/                  # pydantic 요청/응답 모델
    ├── utils/                    # 공통 유틸
    │   ├── jwt.py                # JWT 생성·검증, httpOnly 쿠키 설정
    │   ├── embeddings.py         # Ollama 임베딩 API 호출 (싱글턴 클라이언트)
    │   └── pdf.py                # PDF 텍스트 추출, tiktoken 청크 분할
    │
    └── database.py               # asyncpg 커넥션 풀 싱글턴
```

---

## 8. 시작하기

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (PostgreSQL + pgvector 포함)
- [Ollama](https://ollama.com) 설치
- [Tavily API Key](https://tavily.com) (선택, 웹검색 보완 기능)
- [국가법령정보 Open API Key](https://www.law.go.kr/LSO/openApi/openApiIntroPage.do) (법령 자동 수집 시 필요)

### 1단계: 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
# Database (Docker Compose 기준 호스트 포트 5433)
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/tax_db

# JWT
JWT_SECRET=your-long-random-secret-here
JWT_EXPIRE_MIN=1440

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
CHAT_MODEL=qwen3.5:9b
EMBED_MODEL=qwen3-embedding:4b
# 모든 chat 호출에서 동일해야 함 — 값이 다르면 Ollama가 호출마다 모델을 리로드함
OLLAMA_NUM_CTX=6144
# 유휴 시 모델 언로드 방지 (-1 = 무제한 유지, 콜드 스타트 방지)
OLLAMA_KEEP_ALIVE_SEC=-1

# 외부 API (선택)
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx
LAW_API_KEY=your-law-api-key-here
```

> JWT_SECRET 생성: `python -c "import secrets; print(secrets.token_hex(32))"`

### 2단계: Ollama 모델 설치

```bash
ollama pull qwen3.5:9b
ollama pull qwen3-embedding:4b
```

### 3단계: DB 실행 및 자동 마이그레이션

```bash
# 전체 서비스 빌드 및 실행
docker compose up -d --build
```

백엔드는 시작 전에 자동으로 `alembic upgrade head`를 실행합니다. 새 DB에는 전체 스키마와
세율 시드가 생성되고, 기존 DB에는 적용되지 않은 revision만 반영됩니다. 마이그레이션이
실패하면 API 서버는 시작하지 않으므로 불완전한 스키마로 서비스되는 것을 방지합니다.

```bash
# 현재 적용된 revision 확인
docker exec tax_backend alembic current

# 새 DB 변경 revision 생성
docker exec tax_backend alembic revision -m "add new field"
```

> 앞으로의 DB 변경은 `db/migrations/*.sql`을 직접 실행하지 않고 새 Alembic revision의
> `upgrade()`에 작성합니다.

### 4단계: 법령 데이터 수집 (선택)

```bash
# 세법 전체 자동 탐색 + 저장 (임베딩 없이 먼저 확인)
python scripts/ingest_laws.py

# 임베딩까지 함께 생성
python scripts/ingest_laws.py --embed

# 특정 법령 1개만 테스트
python scripts/ingest_laws.py --law 소득세법 --embed

# 법령해석례(유권해석) 수집 — 세무 관련 키워드 지정
python scripts/ingest_interpretations.py --query 소득세 --embed
python scripts/ingest_interpretations.py --all-tax-keywords --embed

# 법령 개정 자동 동기화 (cron·작업 스케줄러 등록 권장)
python scripts/sync_laws.py --embed
```

### 5단계: 백엔드 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 6단계: 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

---

## 9. 테스트

> pytest·pytest-asyncio는 `requirements.txt`에 포함되어 있어 별도 설치가 필요 없습니다.
> `.github/workflows/ci.yml`이 push/PR마다 컴파일 검사(`compileall`)와 전체 테스트를 자동 실행합니다.

### 전체 테스트 실행

```bash
pytest
```

### 상세 출력

```bash
pytest -v
```

```
tests/test_parser.py::test_normalize_text_strips_whitespace PASSED
tests/test_parser.py::test_parse_articles_skips_deleted PASSED
tests/test_ingestion.py::test_make_hash_is_deterministic PASSED
tests/test_jwt.py::test_create_access_token_sub_claim PASSED
tests/test_api_auth.py::test_signup_duplicate_email_returns_409 PASSED
...
```

### 특정 파일만 실행

```bash
pytest tests/test_parser.py -v              # XML 파싱 로직
pytest tests/test_ingestion.py -v           # 수집·개정 감지 유틸
pytest tests/test_api_service.py -v         # 국가법령정보 API XML 파싱 (법령 + 법령해석례)
pytest tests/test_interpretation_service.py -v  # 유권해석 수집 파이프라인
pytest tests/test_hybrid_search_priority.py -v  # 법령 위계 우선순위 분류
pytest tests/test_calculator.py -v          # 세금 계산기 6종 (소득세·양도세·상속세·증여세·부가세·가산세)
pytest tests/test_calculator_engine.py -v   # 계산기 tool calling 엔진
pytest tests/test_citation_guard.py -v      # 답변 인용·수치 검증 후처리
pytest tests/test_tax_schedule.py -v        # 세무 일정 계산
pytest tests/test_jwt.py -v                 # JWT 토큰
pytest tests/test_api_auth.py -v            # 인증 API
pytest tests/test_api_upload.py -v          # 업로드 API
pytest tests/test_api_chat.py -v            # 채팅 API
pytest tests/test_api_law.py -v             # 조문 원문 뷰어 API
pytest tests/test_api_tax_schedule.py -v    # 세무 일정 API
```

### 실패한 테스트만 재실행

```bash
pytest --lf
```

### 테스트 구성

| 파일 | 테스트 대상 | 비고 |
|------|-------------|------|
| `test_parser.py` | XML 파싱, 조문번호 포맷, law_type 태그(법종구분) 파싱 | DB·외부 의존 없음 |
| `test_ingestion.py` | SHA-256 해시, 세목 추론, 개정 감지(`_supersede_stale_versions`) | DB·외부 의존 없음 |
| `test_api_service.py` | 법령/법령해석례 검색·본문조회 XML 파싱 | DB·외부 의존 없음 |
| `test_interpretation_service.py` | 유권해석 수집·세목 추론·본문 조합 | DB·외부 의존 없음 (API/DB mock) |
| `test_hybrid_search_priority.py` | law_type → (우선순위, source_type) 분류 | DB·외부 의존 없음 |
| `test_calculator.py` | 세금 계산기 6종 세율 구간·공제 로직 | 시드 데이터 mock |
| `test_calculator_engine.py` | 계산 의도 게이트, LLM 추출 파싱, 도구 디스패치 | LLM mock |
| `test_citation_guard.py` | 조문 인용 실존 검증, 계산 금액 일치 검증 | DB·외부 의존 없음 |
| `test_tax_schedule.py` | 사업자 유형별 신고 기한 계산 | DB·외부 의존 없음 |
| `test_jwt.py` | JWT 토큰 생성 및 클레임 검증 | DB·외부 의존 없음 |
| `test_api_auth.py` | 회원가입·로그인 유효성 검사 및 응답 코드 | 서비스 레이어 mock |
| `test_api_upload.py` | 인증 확인(401), 파일 형식 검사(400), 정상 업로드 | 서비스 레이어 mock |
| `test_api_calculator.py` | 인증 확인(401), 유효성 검사(422), 부가세·가산세 계산 응답 | DB mock |
| `test_api_chat.py` | 인증 확인(401), 유효성 검사(422), 계산기 메타데이터·스트리밍 이벤트 | 서비스 레이어 mock |
| `test_api_law.py` | 조문 원문 뷰어 조회(200)·404 | 서비스 레이어 mock |
| `test_api_tax_schedule.py` | 인증 확인(401), 사업자 유형별 일정 응답 | 서비스 레이어 mock |

| `test_chat_service.py` | 세목 키워드 매칭(겹침 억제), 최종 프롬프트 조립, 계산기 메타, 인용 누락 답변 structured output 보정 | LLM mock |
| `test_hybrid_search.py` | 컨텍스트 포맷, 우선순위 정렬, 조문번호 fast path | DB·임베딩 mock |
| `test_clause_splitter.py` | 조문 항(項) 분할, 분할 대상 판정 | DB·외부 의존 없음 |
| `test_pdf_chunking.py` | PDF 조문 경계 인식 청킹 | DB·외부 의존 없음 |

> API 테스트는 실제 DB·Ollama 없이 실행됩니다. 서비스 레이어를 mock으로 대체하여 HTTP 계층의 동작을 검증합니다.

### RAG 품질 평가 (골든셋 기반)

```bash
# 골든셋 각 질문의 실제 검색 후보 채우기 (정답 확정 전 단계)
python scripts/eval_rag.py --build

# 검색 hit-rate·MRR·세목 분류 정확도 측정 (이전 실행과 자동 비교)
python scripts/eval_rag.py --eval

# + 실제 답변 생성 후 인용 정확도까지 확인 (느림)
python scripts/eval_rag.py --eval --with-answer

# temperature 샘플링 편차 검증: N회 반복해 citation_accuracy 평균/편차와
# 실행마다 결과가 바뀌는 비결정적 항목을 확인
python scripts/eval_rag.py --eval --with-answer --repeat 3
```
결과는 `tests/eval/results/`에 타임스탬프 파일로 누적되어 파라미터 변경(임계값, 프롬프트 등) 전후 효과를 수치로 비교할 수 있습니다.
생성 품질에 영향을 주는 변경(프롬프트, `temperature` 등)은 `temperature=0.3` 샘플링 편차 때문에 1회 실행 비교가 신뢰할 수 없다는 게 실측으로 확인되어(같은 코드로 재평가해도 73.7~84.2% 사이를 오갔음), `--repeat`으로 여러 번 돌린 평균으로 판단합니다. 검색 단계 변경(청킹·임베딩 등)은 결정론적이라 1회 비교로 충분합니다.

---

## 10. 환경 변수

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `DATABASE_URL` | ✅ | `postgresql://postgres:postgres@localhost:5432/tax_db` | PostgreSQL 연결 URL |
| `JWT_SECRET` | ✅ | — | JWT 서명 비밀키 (32바이트 이상 권장) |
| `JWT_EXPIRE_MIN` | — | `1440` | JWT 만료 시간 (분, 기본 24시간) |
| `COOKIE_SECURE` | — | `false` | `true` 설정 시 HTTPS 전용 쿠키 (운영 환경에서 활성화) |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | Ollama 서버 URL |
| `CHAT_MODEL` | — | `qwen3.5:9b` | 답변 생성 LLM 모델명 |
| `EMBED_MODEL` | — | `qwen3-embedding:4b` | 임베딩 모델명 |
| `RERANK_MODEL` | — | — | 리랭킹 모델명 (예: `bge-reranker-v2-m3`, 비워두면 리랭킹 비활성화) |
| `THINK_ENABLED` | — | `false` | Qwen3 계열 모델의 Think 모드 활성화 |
| `OLLAMA_NUM_CTX` | — | `6144` | 모든 chat 호출의 컨텍스트 길이 — 호출마다 값이 다르면 Ollama가 매번 모델을 리로드함 |
| `OLLAMA_KEEP_ALIVE_SEC` | — | `-1` | 유휴 시 모델 언로드까지 대기시간(초). `-1`은 무제한 유지(콜드 스타트 방지) |
| `EMBED_DIM` | — | `2560` | 임베딩 차원 수 (모델과 DB 일치 필수) |
| `SIMILARITY_THRESHOLD` | — | `0.4` | 검색 결과 최소 유사도 (0~1, 낮출수록 더 많은 결과 반환) |
| `MAX_UPLOAD_MB` | — | `50` | PDF 업로드 최대 크기 (MB) |
| `TAVILY_API_KEY` | — | — | Tavily 검색 API 키 (없으면 웹검색 생략) |
| `LAW_API_KEY` | — | — | 국가법령정보 Open API 키 (법령 수집 시 필요) |

---

## 11. API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/auth/signup` | 회원가입 | 불필요 |
| POST | `/api/auth/login` | 로그인 (httpOnly 쿠키 발급) | 불필요 |
| POST | `/api/auth/logout` | 로그아웃 (쿠키 삭제) | 불필요 |
| GET | `/api/users/me` | 내 프로필 조회 (사업자 유형 포함) | ✅ 필요 |
| PATCH | `/api/users/me` | 프로필 수정 (이름·전화번호·사업자 유형) | ✅ 필요 |
| PATCH | `/api/users/me/password` | 비밀번호 변경 | ✅ 필요 |
| DELETE | `/api/users/me` | 회원 탈퇴 | ✅ 필요 |
| GET | `/api/conversations` | 대화 목록 조회 (최근 50개) | ✅ 필요 |
| POST | `/api/conversations` | 새 대화 생성 | ✅ 필요 |
| GET | `/api/conversations/{id}/messages` | 대화 메시지 전체 조회 | ✅ 필요 |
| PATCH | `/api/conversations/{id}` | 대화 제목 변경 | ✅ 필요 |
| DELETE | `/api/conversations/{id}` | 대화 삭제 | ✅ 필요 |
| POST | `/api/upload` | PDF 업로드 및 벡터 저장 | ✅ 필요 |
| GET | `/api/documents` | 내가 업로드한 파일 목록 | ✅ 필요 |
| DELETE | `/api/documents/{filename}` | 파일 삭제 (전체 청크 제거) | ✅ 필요 |
| POST | `/api/chat` | 채팅 질문 (일반 응답, 계산기 메타데이터 포함) | ✅ 필요 |
| POST | `/api/chat/stream` | 채팅 질문 (SSE 스트리밍, `chunk`/`calc` 이벤트) | ✅ 필요 |
| POST | `/api/calculator/income-tax` | 종합소득세 계산 | ✅ 필요 |
| POST | `/api/calculator/capital-gains` | 양도소득세 계산 | ✅ 필요 |
| POST | `/api/calculator/inheritance` | 상속세 계산 | ✅ 필요 |
| POST | `/api/calculator/gift` | 증여세 계산 | ✅ 필요 |
| GET | `/api/law-articles/lookup` | 법령명·조문번호로 조문 원문 조회 (조문 뷰어) | ✅ 필요 |
| GET | `/api/tax-schedule` | 사업자 유형 기준 다가오는 신고·납부 기한 | ✅ 필요 |
| GET | `/api/health` | 서버·DB 상태 확인 | 불필요 |

> 자동 생성 API 문서: `http://localhost:8000/docs`

---

## 12. 사용 예시

### 세무 질문 예시

```
# 부가가치세
"간이과세자의 부가가치세 신고 기준은 어떻게 되나요?"
"매입세액 불공제 대상을 알려주세요."

# 소득세
"근로소득공제는 어떤 기준으로 적용되나요?"
"소득세법상 필요경비 인정 기준을 알려줘."
"프리랜서의 원천징수 세율이 궁금합니다."

# 법인세
"법인의 접대비 한도는 어떻게 계산하나요?"
"결손금 소급공제 신청 방법을 알려주세요."

# 세무 절차
"경정청구 기한은 얼마나 되나요?"
"세금계산서 발급 의무가 없는 경우는 어떤 경우인가요?"

# 계산 질문 (세금 계산기 tool calling 자동 실행)
"연소득 5천만원 프리랜서인데 종합소득세 얼마나 내야 해?"
"아버지한테 3억 증여받으면 증여세 얼마야?"
"10년 보유한 아파트를 12억에 팔고 취득가는 7억이면 양도세 계산해줘"
```

### 답변 구조

```markdown
## 1. 💡 결론
핵심 답변 요약 (계산 질문이면 결정세액 포함)

## 2. 📖 상세 설명
법령 조문에 근거한 상세 설명 (계산 질문이면 계산 단계 표 포함)

## 3. ⚖️ 법적 근거
[법률] 소득세법 제20조 - 근로소득
[시행령] 소득세법 시행령 제47조
[유권해석] 10-0075 - 부당해고기간 임금 상당액의 근로소득 해당 여부

## 4. ⚡ 실무 주의사항
실무에서 주의할 점

## 📋 근거 출처 목록
내부 DB와 웹검색 결과 출처 목록

---
⚠️ 자동 검증 결과 (인용 검증 실패 시에만 표시)
검색 자료에서 확인되지 않은 인용이 있으면 여기에 경고가 추가됩니다.
```

---

## 13. 핵심 구현 포인트

### 하이브리드 검색 (법령 조문 + PDF)

`law_articles`와 `documents` 두 테이블을 동시에 벡터 검색한 뒤 법령 위계 기반 우선순위로 병합합니다.
법률 조문이 집행기준 PDF보다 항상 상위에 배치됩니다.

### 세목 자동 분류로 검색 범위 축소

질문에서 세목 키워드를 먼저 감지하고 해당 세목 문서만 검색합니다.
소득세법(연말정산·퇴직소득 등), 부가가치세법(세금계산서·영세율 등), 법인세법(손금·결손금·업무용승용차 등), 조세특례제한법(투자세액공제·고용증대 등), 국세기본법(심판청구·기한후신고 등) 등 22개 세목에 걸쳐 실무 용어까지 포괄합니다.
같은 위치에서 여러 세목 키워드가 겹치면(예: "체납" vs "지방세 체납") 더 긴(구체적인) 키워드만 채택해 불필요한 다중 매칭을 줄입니다.
키워드로 세목이 하나로 확정되면 분류 LLM 호출 자체를 생략하고, 매칭 실패(0개 또는 다중 매칭) 시에만 LLM을 호출(세목 분류 + 멀티쿼리 생성 1회 통합 호출)합니다.

### 비교 질문(A vs B) 처리

"리스와 장기렌트 중 어느 쪽이 유리한가"처럼 두 옵션을 비교하는 질문에서 각 옵션별 검색 쿼리를 별도 생성합니다.
단일 비교 조문이 없어도 각 항목에 적용되는 법령 조문을 각각 근거로 삼아 비교표와 명확한 결론을 제시합니다.

### 파일명 패턴 기반 빠른 문서 분류

법제처 표준 파일명 패턴(`(법률)`, `(대통령령)`, `(부령)`)을 감지하면 AI 없이 즉시 분류합니다.
AI 호출은 파일명으로 분류가 불가능한 경우에만 실행됩니다.

### 유사도 기반 조건부 웹검색

하이브리드 검색 결과의 상위 3개 평균 유사도가 임계값(`_WEB_SEARCH_THRESHOLD`, 기본 0.55) 미만인 경우에만 Tavily 웹검색을 실행합니다.
DB 검색만으로 충분한 질문에서는 불필요한 외부 요청과 지연을 방지합니다.

### 비동기 병렬 처리

세목 분류/멀티쿼리 생성, 대화 메모리 조회, 세금 계산기 실행은 `asyncio.gather`/`asyncio.create_task`로 병렬 실행합니다.
하이브리드 검색에서 `law_articles`와 `documents` 두 테이블도 동시에 쿼리합니다.
Tavily 다중 쿼리도 병렬로 처리하여 대기 시간을 줄입니다.

### SSE 스트리밍

최종 답변은 LangChain `ChatOllama.astream()`으로 토큰 단위 실시간 전송합니다.
`<think>` 태그는 스트리밍 중 버퍼 최소화 방식으로 실시간 필터링합니다(TTFT 개선).
스트리밍 이벤트는 `{"type": "chunk", "text": ...}` / `{"type": "calc", "tool": ..., "params": ...}` 형태로 구분되어, 텍스트와 계산기 메타데이터(프론트 프리필용)를 함께 전달합니다.
스트리밍 완료 후 DB 저장(`_save_history`)은 `asyncio.create_task`로 백그라운드 처리하여 클라이언트 연결을 즉시 종료합니다.

### 세금 계산기 tool calling

질문에서 계산 의도를 감지(금액 표현 + "얼마"/"계산" 등 키워드 게이트, LLM 호출 없음)하면 LLM 1회 호출로 계산기 종류와 입력값을 JSON으로 추출합니다.
pydantic 스키마로 검증 후 DB 세율표 기반 계산기를 실행하며, RAG 검색과 병렬로 처리되어 지연시간을 추가하지 않습니다.
계산 결과(단계별 금액, 근거 조문)는 최종 답변 프롬프트에 병합되고, 프론트에는 계산기 화면 프리필용 메타데이터가 별도로 전달됩니다.

### 인용 검증(citation guard) 후처리

LLM은 법조문 번호나 계산 수치를 프롬프트 지시만으로 완벽히 지키지 않습니다.
답변 생성 후 `[법률]`/`[시행령]`/`[시행규칙]` 인용을 정규식으로 추출해 실제 검색 컨텍스트(+계산기 결과)에 존재하는지 대조하고, 계산기 실행 시 답변 속 금액이 계산 결과의 최종 금액과 일치하는지도 확인합니다.
불일치가 있으면 답변을 임의로 고치지 않고 하단에 경고 각주만 추가해 사용자가 직접 판단하게 합니다.

**인용이 아예 없는 답변 자동 보정**: `temperature` 샘플링에 따라 모델이 가끔 인용 브래킷 자체를 생략하는데(정규식 검증만으로는 잡을 수 없는 사각지대), 검색 컨텍스트에 법령 자료가 실제로 있었는데도 답변에 인용이 0건이면 `call_llm_structured()`로 "근거 조문만 JSON Schema로 뽑아내는" 짧은 보정 호출을 1회 추가 실행합니다. 스키마의 `pattern` 제약(`^제[0-9]{1,4}조(의[0-9]{1,3})?$`)이 디코딩 단계에서 조문번호 표기를 강제해, 프롬프트 지시로는 못 막던 형식 이탈(공백 변형·마크다운·URL 혼입)을 원천 차단합니다. 추출된 조문도 검색 컨텍스트에 실존하는 것만 채택해(환각 인용 차단) 답변 끝에 "근거 출처 목록" 섹션으로 덧붙입니다. 인용이 이미 있는 답변(대다수)에는 이 보정 호출이 아예 실행되지 않아 지연 비용이 없습니다.

### LLM provider 추상화 (LangChain)

`chat_service.py`는 Ollama의 HTTP 요청 스키마를 직접 알지 못합니다 — `app/services/llm_client.py`가 LangChain의 `ChatOllama`를 감싸 `call_llm()`/`stream_llm()`/`call_llm_structured()`라는 provider 중립 인터페이스만 노출합니다.
`num_ctx`/`num_predict`가 top-level이 아닌 `options` 안으로, `think`/`keep_alive`가 top-level로 가는 배치(과거 실측으로 확인된 버그 지점)를 LangChain 내부 소스로 직접 검증한 뒤 적용했습니다.
향후 vLLM(OpenAI 호환 서버)이나 다른 모델로 전환할 때는 `llm_client.py`의 클라이언트 생성 부분만 교체하면 되고, RAG·계산기·citation_guard 등 나머지 로직은 변경이 필요 없습니다.

### 법령 개정 자동 동기화

조문 텍스트의 SHA-256 해시를 `content_hash`로 저장합니다.
`scripts/sync_laws.py`가 이미 수집된 법령을 재수집해 (법령명, 조문번호) 그룹 단위로 이번 수집분의 해시 집합을 계산하고, 그 집합에 없는 기존 `is_current=TRUE` 행만 개정으로 판단해 폐기합니다.
그룹 단위로 비교하는 이유는, 국가법령정보 API가 절/관 표제를 조문번호 없이 다음 조문과 같은 번호로 내려주는 경우가 있어 한 건씩 비교하면 정상 콘텐츠끼리 서로를 잘못 폐기시키기 때문입니다.

### 법령해석례(유권해석) 수집

국가법령정보 Open API의 `target=expc`(법령해석례 검색/본문조회) 엔드포인트로 기획재정부·국세청 등의 유권해석을 수집합니다.
안건명에 포함된 「법령명」에서 관련 법령을 추출해 세목을 추론하고, `law_articles`에 `law_type='법령해석례'`로 저장해 기존 하이브리드 검색·우선순위 로직을 그대로 재사용합니다.

### RAG 성능 최적화

Ollama는 `num_ctx`가 요청마다 다르면 모델을 리로드하고(호출당 수 초), 유휴 상태가 지속되면 모델을 언로드합니다(콜드 스타트 시 수십 초).
모든 chat 호출에서 `num_ctx`를 동일한 값으로 고정하고 `keep_alive=-1`을 요청 최상위 필드로 전달해 모델이 항상 상주하도록 합니다.
키워드로 세목이 하나로 확정되는 질문은 분류 LLM 호출 자체를 생략하고 원본 쿼리로 바로 검색합니다.

---

## 14. 보안 설계

| 항목 | 구현 방식 |
|------|-----------|
| 인증 토큰 저장 | JWT를 httpOnly 쿠키에 저장 (XSS로 탈취 불가) |
| API 보호 | 인증 필요 엔드포인트는 `Depends(verify_token)` 적용 |
| 비밀번호 저장 | bcrypt 해싱 (평문 저장 없음) |
| 쿠키 보안 | `COOKIE_SECURE=true` 설정 시 HTTPS 전용 쿠키 활성화 |
| 세무 데이터 보호 | 로컬 Ollama 사용으로 세무 데이터 외부 LLM 전송 없음 |
| 대화 데이터 | `conversation_id` 기준으로 대화별 분리 저장, `user_id`로 소유자 격리 |
| 문서 격리 | `documents` 테이블 조회 시 `user_id` 필터링 적용 (타인 문서 접근 불가) |

---

## 15. 트러블슈팅

### Ollama 연결 실패
```
httpx.ConnectError: [Errno 111] Connection refused
```
```bash
# Ollama 서버 실행 확인
ollama serve

# 모델 목록 확인
ollama list
```

### pgvector 확장 오류
```
could not open extension control file ... vector.control
```
```bash
# pgvector가 포함된 이미지로 실행 (docker-compose.yml 기준)
docker compose up -d
# pgvector/pgvector:pg17 이미지 사용 확인
```

### PostgreSQL 연결 오류 (포트 확인)
```
ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)
```
```
# docker-compose.yml에서 호스트 포트는 5433
# .env의 DATABASE_URL 포트를 5433으로 설정
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/tax_db
```

### 임베딩 차원 불일치
```
ValueError: 임베딩 차원 불일치: 예상 2560, 실제 768
```
```bash
# .env의 EMBED_MODEL과 DB VECTOR(2560)이 일치하는지 확인
# 모델 변경 시 DB를 재초기화하거나 EMBED_DIM을 맞춰야 함
```

### 응답이 느리고 가끔 비어서 옴 (모델 리로드·콜드스타트·think 옵션 무시)
```
증상: 질문할 때마다 몇 초씩 걸리고, 5분 정도 쉬었다 물어보면 특히 오래 걸림.
      가끔은 아예 빈 답변이 돌아옴.
```
**원인 1 — `num_ctx` 호출마다 불일치**: Ollama는 `num_ctx`(컨텍스트 길이)가 이전 요청과
다르면 모델을 통째로 다시 로드한다. 기존 코드는 세목분류/멀티쿼리 2048, 비스트리밍 4096,
스트리밍 6144로 용도별로 다른 값을 썼는데, 질문 1개 처리 중 분류→최종답변으로 넘어갈 때마다
이 리로드가 발생했다.

**원인 2 — `keep_alive`가 무시되는 위치에 있었음**: Ollama에서 `keep_alive`(유휴 언로드
방지)와 `think`(사고 모드)는 요청의 **최상위 필드**인데, 기존 코드는 이 둘을 `options{}`
안에 넣고 있어 조용히 무시됐다. 그 결과 5분 유휴 후 모델이 언로드되어 콜드스타트가
발생했고, `think`가 항상 켜진 상태로 남아 모델이 사고만 하고 실제 답변(`content`)을
전혀 출력하지 않은 채 스트림이 끝나는 경우가 있었다(빈 답변의 원인).

**실측(Ollama에 직접 호출해 측정)**:

| 상황 | 소요시간 |
|------|---------|
| 콜드 상태 첫 호출 | 48.3s (모델 로드 27.1s) |
| 동일 설정 재호출(웜) | 0.3s |
| `num_ctx` 2048→6144 변경 | 4.8s (리로드 4.7s) |
| `num_ctx` 6144→2048 복귀 | 4.5s (또 리로드) |
| 임베딩 모델 전환(스왑) | 10.0s |
| 스왑 후 chat 모델 복귀 | 9.7s (재로드 9.5s) |

**해결**: 모든 chat 호출에서 `OLLAMA_NUM_CTX`를 동일한 값으로 통일하고,
`keep_alive`·`think`를 `options{}`가 아닌 요청 최상위 필드로 이동했다.
```env
OLLAMA_NUM_CTX=6144
OLLAMA_KEEP_ALIVE_SEC=-1
```
```bash
# 모델이 실제로 상주 중인지, chat·임베딩 모델이 둘 다 VRAM에 공존하는지 확인
ollama ps
```
적용 후 동일 설정 재호출이 4.5s→**0.4s**로, 두 모델(chat 5.8GB + 임베딩 4.4GB)이
VRAM에 동시 상주해(expires 값이 사실상 무제한) 스왑이 사라졌다. 콜드스타트도 재발하지 않았다.

### 세목이 명확한 질문도 매번 분류 LLM을 거쳐 느림
```
증상: "소득세 신고 방법 알려줘"처럼 세목이 명백한 질문도 답변까지 오래 걸림
```
**원인**: 세목이 키워드로 이미 하나로 확정되는 질문도 매번 LLM 1회 호출(세목 분류 +
멀티쿼리 생성)을 거쳤다 — 확정된 결과를 다시 LLM에게 확인받는 불필요한 과정.

**해결**: 키워드 매칭으로 세목이 정확히 하나로 확정되면(`_match_laws_by_keyword` 결과 1개)
분류 LLM 호출 자체를 생략하고 원본 질문으로 바로 검색한다. 0개(미매칭) 또는 2개 이상
(다중 매칭 — 세목 교차 질문) 일 때만 LLM을 호출한다.

**실측(골든셋 재실행으로 회귀 여부까지 검증)**: 단일 세목 확정 질문의 처리 시간이
2.5s대 → **0.1s**로 감소. 검색 hit_rate@5·MRR은 그대로였고(회귀 없음), 오히려
세목 분류 정확도가 90.9%→100%로 개선되었다(LLM이 가끔 틀리게 판단하던 사례가
애초에 LLM을 안 거치게 되며 사라짐).

### DB 검색만으로 충분한데도 웹검색이 거의 매번 실행됨
```
증상: 정답을 이미 top-1으로 정확히 찾은 질문에서도 Tavily 웹검색이 추가로 실행되어 지연 발생
```
**원인**: 웹검색 실행 임계값(상위 3개 평균 유사도)이 0.7로 설정되어 있었는데, 실제
임베딩 모델의 유사도 점수 분포상 정답을 정확히 찾은 경우도 0.47~0.58 수준에 머물러
거의 항상 임계값 미만으로 판정되어 웹검색이 실행됐다.

**해결**: 임계값을 0.7 → **0.55**로 하향(`_WEB_SEARCH_THRESHOLD`). DB 검색이 실제로
불충분한 경우에만 웹검색이 실행되도록 실제 점수 분포에 맞춰 조정했다.

### 긴 조문의 특정 항 내용이 검색에 안 걸림 (임베딩 희석)
```
증상: "표준세액공제 금액은?" 질문에 정답 조문(소득세법 제59조의4)이 top-5에 없음
```
**원인**: 법령 조문은 조(條) 단위로 통째 임베딩되는데, 여러 항(①~⑨)을 가진 긴 조문에서
정답이 한 항에만 있으면 조문 전체 벡터에서 그 항의 의미가 희석되어 유사도가 낮아진다.
(제59조의4는 의료비·교육비 등 특별세액공제 내용이 지배적이라 ⑨항의 표준세액공제가 묻힘)

**해결**: `CLAUSE_SPLIT_MIN_CHARS`(문자 수) 이상 + 항 2개 이상인 조문은 항 단위 보조 임베딩을
`law_article_clauses` 테이블에 추가로 생성한다 (조문 벡터와 항 벡터를 함께 검색해 최고
유사도만 채택, 히트 시 컨텍스트는 항이 아닌 조문 전체 제공). 신규 수집분은 자동 생성되며,
기존 데이터는 백필 스크립트로 생성한다:
```bash
# Alembic 마이그레이션 적용 후 1회
docker exec tax_backend alembic upgrade head
python scripts/embed_clauses.py --run
```

**임계값 실험(1,000자 vs 300자)**: 300~1,000자 사이의 다항목 조문 10개로 "핵심 주제가
아닌 특정 항"을 겨냥한 질문을 만들어 비교한 결과, 짧은 조문도 항끼리 서로 다른 내용을
다루면 분할이 순위를 개선했다(예: 법인세법 제19조의2 HIT@2→HIT@1, 관세법 제118조의4
HIT@3→HIT@1, hit_rate 회귀 없음). `CLAUSE_SPLIT_MIN_CHARS`를 1,000→300으로 낮추고
전체 재백필한 결과 골든셋(38문항) MRR이 0.909→0.926으로 개선되었다.

**"조문 벡터를 없애고 항 벡터만 쓰면 더 낫지 않을까?" 도 실험**: 조문 벡터만 사용 시
hit_rate 97.9%(긴 조문 희석 문제 재현), 항 벡터만 사용 시에도 97.9%(조문 전체를 묻는
질문에서 실패 — "조문 자체를 대표하는 벡터"가 사라지기 때문). **둘 다 함께 검색하는
현재 방식만 100%를 달성** — 택일이 아니라 병행이 정답이었다.
적용 결과: 평가셋 hit_rate@5 97.4% → 100%, 관련 질문이 MISS → HIT@1.

### 조문번호를 콕 집어 물어봐도 못 찾음
```
증상: "부가가치세법 제39조 내용이 궁금해" 질문에 제39조가 검색되지 않음
```
**원인**: 조문번호("제39조") 같은 숫자 식별자는 임베딩 유사도에 거의 반영되지 않아
벡터 검색만으로는 직접 질의를 안정적으로 찾지 못한다.

**해결**: `hybrid_search`에 조문번호 직접 질의 fast path를 추가했다 — 질문에서
`법령명 + 제N조` 패턴을 감지하면 벡터 검색을 거치지 않고 해당 조문을 DB에서 직접
조회해 검색 결과 최상위에 배치한다 (법령명이 없으면 세목 필터로 보완).

### 업로드한 법령 PDF의 조문이 청크 중간에서 잘림
```
증상: 법령·시행령 PDF 업로드 시 "제39조 ①…" 본문이 청크 경계에서 절단되어 검색 품질 저하
```
**원인**: PDF 청킹이 tiktoken 800토큰 슬라이딩 윈도우로 기계적으로 분할해
조문 경계를 무시했다. 잘린 반쪽 청크는 임베딩 품질이 떨어진다.

**해결**: `split_into_chunks`가 조문 시작 패턴(`제N조(`)이 5회 이상 감지되면 법령류
문서로 판단해 조문 경계 기준으로 분할한다 — 연속 조문을 청크 한도 내로 묶고, 단일
조문이 한도를 넘는 경우에만 그 조문만 토큰 분할로 폴백한다. 일반 문서는 기존 토큰
분할을 그대로 사용한다. (이미 업로드된 문서는 삭제 후 재업로드해야 새 청킹이 적용됨)

### `num_predict` 잘림으로 인용 섹션이 통째로 사라짐 (생성 품질 측정)
```
증상: 골든셋(38문항) 생성 품질 측정 시 citation_accuracy 18.4% — 답변에 인용이 거의 없음
```
**원인**: 처음엔 인용 정규식이 "제 50 조"처럼 qwen 토크나이저가 조문번호 사이에 공백을
섞어 출력하는 경우를 못 잡는 파싱 버그였다(정규식 `제\d+조` → `제\s*\d+\s*조(?:\s*의\s*\d+)?`로
수정, `citation_guard.py`/`eval_rag.py`/`hybrid_search_service.py`/프론트엔드
`MessageBubble.jsx` 4곳 동시 수정 필요). 이걸 고치고도 52.6%에서 정체됐는데, 원인은
비스트리밍 호출(`_call_ollama`)의 `num_predict=500`이 답변을 약 850~950자에서 강제
절단해 프롬프트가 마지막에 요구하는 "근거 출처 목록" 섹션이 아예 생성되지 못했기
때문이었다 (스트리밍 경로는 처음부터 `-1`이라 문제 없었음).

**해결**: `num_predict`를 스트리밍과 동일하게 `-1`(무제한)로 변경.
적용 결과: citation_accuracy 52.6% → 81.6%.

**남은 실패의 성격**: 이후 남은 실패들을 답변 전문까지 열어 확인한 결과, 잘림이 아니라
`temperature=0.3` 샘플링에 따라 모델이 가끔 지정된 출력 형식(결론→상세설명→법적근거→
근거출처목록)을 이탈해 표/자유서술로만 답하는 **비결정적 현상**이었다. 같은 질문
("소득세법 제55조에 뭐라고 되어 있는지 알려줘")을 재실행해보면 어떤 때는 인용이
정상 포함되고 어떤 때는 0건이었다 — 이 때문에 동일 코드로 재평가해도 citation_accuracy가
81.6%→73.7%로 흔들리는 걸 확인했고, 단일 실행 비교로는 개선 여부를 판단할 수 없다는
결론에 도달했다.

**대응**: (1) 프롬프트에 "서술형 질문이어도 출력 형식과 근거 출처 목록을 예외 없이
포함하라"는 규칙을 추가(`_COMBINED_PROMPT` 10번 항목), (2) `citation_guard.py`에
안전망 추가 — 검색 컨텍스트에 법령 자료가 실제로 있었는데(`[출처:` 존재) 답변에 인용이
하나도 없으면 경고 각주를 붙인다. 단, 이 각주는 사용자에게 "확인 필요"를 알릴 뿐 정답
인용을 대신 채워주지 않으므로 citation_accuracy 지표 자체를 끌어올리진 않는다 — 실사용
안전장치이지 정확도 개선 장치는 아니다.

### 프롬프트/코드 변경의 개선 여부를 단일 평가 실행으로 잘못 판단할 위험 (결과 검증절차 추가)
```
증상: 프롬프트 강화(위 항목의 대응 (1))를 적용하고 골든셋을 재평가했더니
citation_accuracy가 81.6% → 73.7%로 오히려 하락 — 개선인지 퇴보인지 판단 불가
```
**원인**: 실패/성공 항목 목록을 이전 실행과 대조해보니, 실패로 바뀐 항목과 성공으로
바뀐 항목이 서로 달랐다(예: 이전엔 실패였던 `direct-01`이 성공, 이전엔 성공이던
`gift-01`/`vat-03`/`corp-01`/`cmp-01`이 실패). 코드는 그대로인데 결과가 흔들린다는 건
`temperature=0.3` 샘플링 자체의 변동성이지 변경분의 실제 효과가 아니라는 뜻이다.
**평가 스크립트가 항상 1회만 실행하는 구조라 이 변동성을 구조적으로 포착할 수 없었다** —
"한 번 돌려서 수치가 오르면 개선, 내리면 퇴보"라는 그동안의 판단 방식 자체가 이 정도
샘플링 편차 앞에서는 신뢰할 수 없다는 게 이번에 드러난 문제였다.

**해결**: `scripts/eval_rag.py`에 `--repeat N` 옵션을 추가했다. `--eval --with-answer`를
N회 반복 실행하여 (1) citation_accuracy의 평균/최솟값/최댓값을 함께 보고하고,
(2) 문항별로 실행마다 인용 히트 여부가 바뀐 "비결정적 항목"을 별도로 식별해 출력한다.
```bash
python scripts/eval_rag.py --eval --with-answer --repeat 3
```
이제부터 생성 품질에 영향을 주는 변경(프롬프트 수정, `temperature`/`num_predict` 조정 등)은
1회 실행 수치가 아니라 이 반복 평가의 평균과 항목별 안정성으로 판단한다. 반대로 검색
단계 변경(청킹, 임베딩, hybrid_search 로직 등)은 결정론적이라 지금처럼 1회 실행 비교로도
충분하다 — 변동성은 "LLM 생성" 단계에서만 발생한다.

### LLM provider(Ollama) 종속 — 답변 구조화·모델 교체 유연성
```
증상: chat_service.py가 Ollama의 HTTP 요청 스키마(think/keep_alive top-level, options 등)를
직접 조립해, 향후 vLLM이나 다른 모델로 교체하려면 호출부 전체를 다시 짜야 하는 구조
```
**원인**: `_call_ollama`/`_stream_ollama_response`가 `httpx.AsyncClient`로 Ollama의
`/api/chat`을 직접 호출하고 있어, provider 고유 스키마(어떤 필드가 top-level이고
어떤 게 `options` 안인지 등, 과거 `think`/`keep_alive` 배치 버그의 원인이기도 했다)에
비즈니스 로직이 그대로 결합돼 있었다.

**해결**: `app/services/llm_client.py`를 신설해 LangChain의 `ChatOllama`로 감쌌다.
`chat_service.py`는 이제 `call_llm(messages, temperature, num_predict)` /
`stream_llm(...)`만 호출하고 provider 세부사항을 전혀 모른다 — 향후 vLLM(OpenAI 호환
서버)이나 다른 모델로 바꿀 때 `llm_client.py`의 `_build_client()` 한 곳만 교체하면 된다.
마이그레이션 전 LangChain 내부 소스(`ChatOllama._chat_params`)를 직접 확인해
`think`/`keep_alive`가 여전히 top-level, `num_ctx`/`num_predict`가 `options` 안으로
가는 것을 검증한 뒤 적용했다 — 과거 버그를 재도입하지 않기 위함.

적용 결과: 218개 전체 테스트 통과, 실제 Ollama 서버 대상 스모크 테스트(비스트리밍/
스트리밍) 정상 동작, hit_rate@5·MRR·분류정확도(전부 검색 단계에서 결정되는 값이라
LLM 생성과 무관) 회귀 없음. 답변 품질 자체의 변화를 노린 작업이 아니라, provider
전환 비용을 낮추기 위한 내부 구조 개선이다.

---

## 16. 한계 및 개선 과제

| 한계 | 개선 방향 |
|------|-----------|
| 스캔 PDF 미지원 | pytesseract, AWS Textract 연동 |
| 일반(비법령) 문서는 여전히 토큰 기준 청크 분할 | 문장 경계 인식 분할로 보완 여지 (법령류 문서는 조문 경계 분할 적용됨) |
| 유권해석 안건명에서 관련 법령을 첫 번째 「」만 추출 | 본문 전체를 분석해 가장 관련도 높은 법령을 선택하도록 개선 여지 |
| 업로드 문서 자동 파싱(원천징수영수증 등 → 계산기 자동 입력) 미지원 | OCR + 정형 문서 필드 추출 파이프라인 추가 |


---

## 17. 라이선스

라이선스는 추후 추가 예정입니다.

