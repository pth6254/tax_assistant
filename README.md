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
9. [환경 변수](#9-환경-변수)
10. [API 엔드포인트](#10-api-엔드포인트)
11. [사용 예시](#11-사용-예시)
12. [핵심 구현 포인트](#12-핵심-구현-포인트)
13. [보안 설계](#13-보안-설계)
14. [트러블슈팅](#14-트러블슈팅)
15. [한계 및 개선 과제](#15-한계-및-개선-과제)
16. [라이선스](#16-라이선스)

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
공식 법령 조문 DB (국가법령정보 API)
        +
사용자 업로드 PDF (시행령·집행기준 등)
        +
Tavily 웹검색 (최신 예규·판례·유권해석)
        ↓
Agentic RAG 3단계 파이프라인
        ↓
법령 조문 번호까지 명시한 근거 기반 답변
```

- **RAG**: 법령 벡터 DB를 먼저 검색하여 근거 없는 생성 차단
- **법령 위계 반영**: 법률 → 시행령 → 시행규칙 → 집행기준 우선순위 적용
- **Agentic**: Gap Analysis로 부족한 부분을 스스로 판단하여 웹검색 보완
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

### 하이브리드 검색

- `law_articles`(공식 법령 조문)와 `documents`(업로드 PDF)를 동시 검색
- 법령 위계 기반 우선순위 정렬로 법률 조문을 최상위에 배치
- 세목 필터링으로 관련 법령만 검색하여 정확도 향상

### Agentic RAG 채팅

- **3단계 파이프라인**: 내부 DB 검색 → Gap Analysis → 웹검색 보완 → 최종 합성
- **SSE 스트리밍**: 토큰 단위 실시간 응답 (긴 답변도 즉시 출력 시작)
- **대화 메모리**: 최근 3턴 컨텍스트 유지
- **Tavily 웹검색**: 국세청·법제처·기획재정부 도메인 중심 최신 자료 보완

### 기타

- JWT httpOnly 쿠키 기반 인증
- React 채팅 UI (마크다운 렌더링)
- 법령 개정 감지 (content_hash 기반)

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

    D -->|Ollama REST API| G[Ollama<br/>qwen3.5:35b-a3b<br/>qwen3-embedding:4b]
    D -->|Tavily API| H[Tavily Search]
    D -->|국가법령정보 API| I[법령정보 Open API]

    F --> F1[documents<br/>PDF 청크 벡터]
    F --> F2[law_articles<br/>법령 조문 벡터]
    F --> F3[chat_logs<br/>대화 메모리]
    F --> F4[users<br/>인증]
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

### 채팅 흐름 (3단계 Agentic RAG)

```
질문 입력
  │
  ├─ [병렬] 세목 분류 (키워드 매핑 → 실패 시 LLM 판단)
  └─ [병렬] 대화 메모리 조회 (최근 3턴)
  │
  → 질문 임베딩 (qwen3-embedding:4b)
  → 하이브리드 벡터 검색 (law_articles + documents, TOP 10)
  → 법령 위계 정렬
     0순위: 법률    (law_articles, law_type=법률)
     1순위: 시행령  (law_articles, law_type=대통령령)
     2순위: 시행규칙 (law_articles, law_type=총리령/부령)
     3~7순위: PDF 문서 (category 기준)
  │
  ├─ [1단계] 내부 DB 1차 답변 생성
  │    법령 위계 원칙 + 세법 일반 원칙 (특별법 우선, 신법 우선, 엄격 해석)
  │
  ├─ [2단계] Gap Analysis
  │    1차 답변의 "근거 없음" / "전문가 확인 권장" 부분 식별
  │    → 법령·실무·계산 관점 3가지 검색 쿼리 생성
  │    → Tavily 병렬 검색 (nts.go.kr, law.go.kr, moef.go.kr)
  │
  └─ [3단계] 최종 답변 합성 (SSE 스트리밍)
       내부 DB + 웹검색 결과 합성
       → 대화 메모리 저장
       → 토큰 단위 스트리밍 출력
```

### 법령 위계 원칙

| 우선순위 | 구분 | 역할 |
|----------|------|------|
| 1 | 법률 | 최상위 근거, 반드시 인용 |
| 2 | 시행령 (대통령령) | 법령의 위임 사항, 구체적 기준 |
| 3 | 시행규칙 (총리령·부령) | 시행령의 위임 사항, 세부 절차 |
| 4 | 집행기준·실무자료 | 행정 해석, 참고용 (법적 구속력 없음) |

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
| LLM | Ollama qwen3.5:35b-a3b (로컬) |
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
│   └── ingest_laws.py           # 법령 수집 CLI (수집/임베딩/재수집)
│
├── db/
│   ├── init.sql                 # DB 초기화 (users, documents, chat_logs)
│   └── migrations/
│       └── V002__add_law_articles.sql  # law_articles 테이블 마이그레이션
│
├── frontend/                    # React 프론트엔드 (Vite)
│   └── src/
│       ├── api/                 # FastAPI 호출 함수 (chatApi, uploadApi, authApi)
│       ├── hooks/               # 상태 관리 커스텀 훅 (useChat, useAuth)
│       └── components/
│           ├── Chat/            # 채팅 UI (ChatArea, ChatInput, MessageBubble)
│           └── Sidebar/         # PDF 업로드, 파일 목록
│
└── app/
    ├── routers/                 # HTTP 수신, 입력 검증, 인증 확인
    │   ├── auth.py              # POST /api/auth/signup, /login, /logout
    │   ├── chat.py              # POST /api/chat, /api/chat/stream
    │   └── upload.py            # POST /api/upload
    │
    ├── services/                # 비즈니스 로직
    │   ├── auth_service.py      # 이메일 중복, bcrypt 해싱, JWT 발급
    │   ├── chat_service.py      # 3단계 Agentic RAG 파이프라인, 스트리밍
    │   ├── upload_service.py    # PDF 파싱 → 분류 → 청크 → 임베딩 → 저장
    │   └── law/
    │       ├── api_service.py       # 국가법령정보 API 클라이언트
    │       ├── parser_service.py    # 법령 XML 조문 파싱
    │       ├── ingestion_service.py # 법령 수집·저장·임베딩 파이프라인
    │       ├── hybrid_search_service.py  # law_articles + documents 하이브리드 검색
    │       └── search_service.py    # 벡터 유사도 검색
    │
    ├── utils/                   # 공통 유틸
    │   ├── jwt.py               # JWT 생성·검증, httpOnly 쿠키 설정
    │   ├── embeddings.py        # Ollama 임베딩 API 호출 (싱글턴 클라이언트)
    │   └── pdf.py               # PDF 텍스트 추출, tiktoken 청크 분할
    │
    └── database.py              # asyncpg 커넥션 풀 싱글턴
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
CHAT_MODEL=qwen3.5:35b-a3b
EMBED_MODEL=qwen3-embedding:4b

# 외부 API (선택)
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx
LAW_API_KEY=your-law-api-key-here
```

> JWT_SECRET 생성: `python -c "import secrets; print(secrets.token_hex(32))"`

### 2단계: Ollama 모델 설치

```bash
ollama pull qwen3.5:35b-a3b
ollama pull qwen3-embedding:4b
```

### 3단계: DB 실행 및 초기화

```bash
# PostgreSQL + pgvector 컨테이너 실행
docker compose up -d

# 마이그레이션 적용 (law_articles 테이블)
psql -U postgres -h localhost -p 5433 -d tax_db \
     -f db/migrations/V002__add_law_articles.sql
```

### 4단계: 법령 데이터 수집 (선택)

```bash
# 세법 전체 자동 탐색 + 저장 (임베딩 없이 먼저 확인)
python scripts/ingest_laws.py

# 임베딩까지 함께 생성
python scripts/ingest_laws.py --embed

# 특정 법령 1개만 테스트
python scripts/ingest_laws.py --law 소득세법 --embed
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

## 9. 환경 변수

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `DATABASE_URL` | ✅ | `postgresql://postgres:postgres@localhost:5432/tax_db` | PostgreSQL 연결 URL |
| `JWT_SECRET` | ✅ | — | JWT 서명 비밀키 (32바이트 이상 권장) |
| `JWT_EXPIRE_MIN` | — | `1440` | JWT 만료 시간 (분, 기본 24시간) |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | Ollama 서버 URL |
| `CHAT_MODEL` | — | `qwen3.5:35b-a3b` | 답변 생성 LLM 모델명 |
| `EMBED_MODEL` | — | `qwen3-embedding:4b` | 임베딩 모델명 |
| `EMBED_DIM` | — | `2560` | 임베딩 차원 수 (모델과 DB 일치 필수) |
| `TAVILY_API_KEY` | — | — | Tavily 검색 API 키 (없으면 웹검색 생략) |
| `LAW_API_KEY` | — | — | 국가법령정보 Open API 키 (법령 수집 시 필요) |

---

## 10. API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/auth/signup` | 회원가입 | 불필요 |
| POST | `/api/auth/login` | 로그인 (httpOnly 쿠키 발급) | 불필요 |
| POST | `/api/auth/logout` | 로그아웃 (쿠키 삭제) | 불필요 |
| POST | `/api/upload` | PDF 업로드 및 벡터 저장 | ✅ 필요 |
| POST | `/api/chat` | 채팅 질문 (일반 응답) | ✅ 필요 |
| POST | `/api/chat/stream` | 채팅 질문 (SSE 스트리밍) | ✅ 필요 |
| GET | `/api/health` | 서버·DB 상태 확인 | 불필요 |

> 자동 생성 API 문서: `http://localhost:8000/docs`

---

## 11. 사용 예시

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
```

### 답변 구조

```markdown
## 1. 💡 결론
핵심 답변 요약

## 2. 📖 상세 설명
법령 조문에 근거한 상세 설명

## 3. ⚖️ 법적 근거
[법률] 소득세법 제20조 - 근로소득
[시행령] 소득세법 시행령 제47조

## 4. ⚡ 실무 주의사항
실무에서 주의할 점

## 📋 근거 출처 목록
내부 DB와 웹검색 결과 출처 목록
```

---

## 12. 핵심 구현 포인트

### 하이브리드 검색 (법령 조문 + PDF)

`law_articles`와 `documents` 두 테이블을 동시에 벡터 검색한 뒤 법령 위계 기반 우선순위로 병합합니다.
법률 조문이 집행기준 PDF보다 항상 상위에 배치됩니다.

### 세목 자동 분류로 검색 범위 축소

질문에서 소득세, 부가세 등을 먼저 분류하고 해당 세목 문서만 검색합니다.
분류 실패 시에만 LLM을 호출하여 불필요한 연산을 줄입니다.

### 파일명 패턴 기반 빠른 문서 분류

법제처 표준 파일명 패턴(`(법률)`, `(대통령령)`, `(부령)`)을 감지하면 AI 없이 즉시 분류합니다.
AI 호출은 파일명으로 분류가 불가능한 경우에만 실행됩니다.

### Gap Analysis 기반 조건부 웹검색

1차 답변에서 "근거 없음", "전문가 확인 권장" 구간을 탐지해 웹검색 필요 여부를 판단합니다.
검색이 필요한 경우에만 Tavily API를 호출하여 불필요한 외부 요청을 방지합니다.

### 비동기 병렬 처리

세목 분류와 대화 메모리 조회는 `asyncio.gather`로 병렬 실행합니다.
Tavily 다중 쿼리도 병렬로 처리하여 대기 시간을 줄입니다.

### SSE 스트리밍

3단계 최종 답변은 Ollama `stream: true` 모드로 토큰 단위 실시간 전송합니다.
`<think>` 태그는 스트리밍 중 필터링하여 사용자에게 노출되지 않습니다.

### 법령 개정 감지

조문 텍스트의 SHA-256 해시를 `content_hash`로 저장합니다.
같은 법령·조문번호라도 해시가 다르면 개정으로 판단하여 `is_current=FALSE` 처리 후 신규 삽입합니다.

---

## 13. 보안 설계

| 항목 | 구현 방식 |
|------|-----------|
| 인증 토큰 저장 | JWT를 httpOnly 쿠키에 저장 (XSS로 탈취 불가) |
| API 보호 | 인증 필요 엔드포인트는 `Depends(verify_token)` 적용 |
| 비밀번호 저장 | bcrypt 해싱 (평문 저장 없음) |
| 세무 데이터 보호 | 로컬 Ollama 사용으로 세무 데이터 외부 LLM 전송 없음 |
| 대화 데이터 | `session_id`(=user_id) 기준으로 사용자별 분리 저장 |

---

## 14. 트러블슈팅

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


---

## 15. 한계 및 개선 과제

| 한계 | 개선 방향 |
|------|-----------|
| 스캔 PDF 미지원 | pytesseract, AWS Textract 연동 |
| 단일 세션 구조 | `sessions` 테이블 분리로 멀티 대화 지원 |
| 토큰 기준 청크 분할 | `RecursiveCharacterTextSplitter`로 문장 경계 보완 |
| Cross-Encoder Re-ranker 미적용 | `bge-reranker` 추가로 검색 품질 향상 |
| 법령 개정 수동 재수집 | 주기적 자동 동기화 스케줄러 추가 |
| pgvector 인덱스 미적용 | 2560차원 이하 모델 전환 시 HNSW 인덱스 추가 가능 |
| 사용자별 문서 격리 없음 | `documents` 테이블에 `user_id` 필터 추가 |


---

## 16. 라이선스

라이선스는 추후 추가 예정입니다.

