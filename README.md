# 세무 AI 어시스턴트

> 대한민국 세무 법령 PDF를 업로드하면 **Agentic RAG** 기반으로 법적 근거와 함께 답변하는 AI 어시스턴트입니다.
> 단순 LLM 답변의 환각 문제를 RAG로 해결하고, 법령 위계(법령 > 시행령 > 시행규칙)를 반영한 도메인 특화 설계를 적용했습니다.

---

## 주요 특징

**1. 법령 위계 기반 메타데이터 설계**
업로드 시점에 AI가 문서를 분석하여 법령, 시행령, 시행규칙, 집행기준으로 category를 자동 분류합니다.
검색 후 상위 법령 우선 정렬하여 LLM에 전달함으로써 법적으로 정확한 근거를 제시합니다.

**2. Agentic RAG 3단계 파이프라인**
단순 RAG를 넘어 에이전트가 스스로 판단하는 3단계 구조로 답변 품질을 높였습니다.
- 1단계: 내부 법령 DB 벡터 검색 → 1차 답변 생성
- 2단계: Gap Analysis → Tavily 웹검색으로 최신 예규/판례 보완
- 3단계: 내부 DB + 웹검색 결과 합성 → 최종 답변

**3. 세목 필터링으로 검색 최적화**
질문에서 소득세, 부가세 등 세목을 먼저 분류하고 해당 세목 문서만 검색하여
불필요한 연산을 줄이고 검색 정확도를 높였습니다.

**4. 파일명 패턴 기반 자동 분류**
`(법률)`, `(대통령령)`, `(부령)` 등 법제처 표준 파일명 패턴을 우선 인식하여
AI 호출 없이 빠르고 정확하게 문서를 분류합니다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | FastAPI, asyncpg, pgvector |
| 프론트엔드 | React 18, Vite |
| 데이터베이스 | PostgreSQL + pgvector |
| 인증 | JWT (httpOnly 쿠키) |
| LLM | Ollama qwen3.5:35b-a3b (로컬) |
| 임베딩 | Ollama qwen3-embedding:4b (2560차원, 로컬) |
| 웹검색 | Tavily Search API |
| 컨테이너 | Docker Compose |

> **로컬 모델 선택 이유**: OpenAI API 대신 Ollama 로컬 모델을 사용하여 API 비용을 절감하고,
> 세무 데이터의 외부 전송 없이 프라이버시를 보호합니다.

---

## 시스템 아키텍처

```
[사용자]
   │
   ▼
[React 프론트엔드] ──── Vite Proxy ────▶ [FastAPI 백엔드]
                                              │
                          ┌───────────────────┼───────────────────┐
                          ▼                   ▼                   ▼
                    [routers/]          [services/]           [utils/]
                    입력 검증           비즈니스 로직          공통 기능
                    인증 확인           RAG 파이프라인         JWT, 임베딩
                                            │                  PDF 파싱
                                            ▼
                                    [PostgreSQL + pgvector]
                                    문서 벡터 저장소
                                    채팅 메모리
                                    사용자 정보
```

---

## Agentic RAG 파이프라인

### 문서 업로드 흐름

```
PDF 업로드
  → 텍스트 추출 (PyPDF2)
  → 파일명 패턴 분석 → (법률/대통령령/부령 감지)
  → AI 분류 (파일명으로 못 잡은 경우만)
     - law_name: 소득세법, 부가가치세법 등
     - category: 법령, 시행령, 시행규칙, 집행기준
  → 청크 분할 (800 토큰, 100 토큰 오버랩)
  → 임베딩 변환 (qwen3-embedding:4b, 2560차원)
  → pgvector 저장 (메타데이터 포함)
```

### 채팅 흐름 (3단계 Agentic RAG)

```
질문 입력
  → 세목 분류 (키워드 매핑 → 실패 시 LLM 판단)
  → 질문 임베딩
  → pgvector 유사도 검색 (TOP 10, 세목 필터 적용)
  → 법령 위계 순 정렬 (법령 → 시행령 → 시행규칙 → 집행기준)
  → 채팅 메모리 조회 (최근 3턴)
  │
  ├─ [1단계] 자료 검색기
  │    법령 위계 원칙 + 세법 일반 원칙 기반 1차 답변 생성
  │
  ├─ [2단계] Gap Analysis + Tavily 웹검색
  │    1차 답변의 부족한 부분 식별
  │    → 국세청(nts.go.kr), 법제처(law.go.kr) 중심 검색
  │    → 최신 예규, 판례, 유권해석 보완
  │
  └─ [3단계] 최종 답변 요약기
       내부 DB 결과 + 웹검색 결과 합성
       → 대화 메모리 저장
       → 최종 답변 반환
```

---

## 법령 위계 원칙

검색된 문서에 동일한 내용이 여러 위계에서 발견될 경우 아래 우선순위를 따릅니다.

```
1. 법령     — 최상위 근거, 반드시 인용
2. 시행령   — 법령의 위임 사항, 구체적 기준
3. 시행규칙 — 시행령의 위임 사항, 세부 절차
4. 집행기준 — 행정 해석, 참고용 (법적 구속력 없음)
```

세법 일반 원칙도 프롬프트에 반영했습니다.
- **특별법 우선**: 일반법보다 특별법(조세특례제한법)이 우선 적용
- **신법 우선**: 같은 위계의 법령은 최신 개정령이 우선
- **엄격 해석**: 비과세·감면 요건은 명확한 근거가 있어야 함

---

## 프로젝트 구조

```
tax-assistant/
│
├── main.py                    # 앱 진입점. 라우터 등록, DB 풀 시작/종료
├── config.py                  # 환경변수 중앙 관리
├── init_db.sql                # PostgreSQL 초기화 스크립트
│
├── frontend/                  # React 프론트엔드 (Vite)
│   └── src/
│       ├── api/               # FastAPI 엔드포인트 호출 함수
│       ├── hooks/             # React 상태 관리 커스텀 훅
│       └── components/        # UI 컴포넌트
│           ├── Auth/          # 로그인/회원가입
│           ├── Sidebar/       # PDF 업로드, 파일 목록
│           └── Chat/          # 채팅 UI
│
└── app/
    ├── routers/               # HTTP 요청 수신, 입력 검증
    │   ├── auth.py            # POST /api/auth/signup, /login, /logout
    │   ├── chat.py            # POST /api/chat
    │   └── upload.py          # POST /api/upload
    │
    ├── services/              # 핵심 비즈니스 로직
    │   ├── auth_service.py    # 이메일 중복 확인, bcrypt 해싱, JWT 발급
    │   ├── chat_service.py    # 3단계 Agentic RAG 파이프라인
    │   └── upload_service.py  # PDF 파싱 → 분류 → 청크 → 임베딩 → 저장
    │
    ├── utils/                 # 공통 유틸 함수
    │   ├── jwt.py             # JWT 생성, httpOnly 쿠키 설정/삭제, 검증
    │   ├── embeddings.py      # Ollama 임베딩 API 호출
    │   └── pdf.py             # PDF 텍스트 추출, tiktoken 청크 분할
    │
    └── database.py            # asyncpg 커넥션 풀 싱글턴 관리
```

---

## 계층 간 호출 흐름

```
HTTP 요청
  → routers/    (입력 검증, 인증 확인)
  → services/   (비즈니스 로직 실행)
  → utils/      (공통 기능 호출)
  → database.py (DB 접근)
```

각 계층은 단방향으로만 흐릅니다.

---

## 개발 배경

처음에는 N8N으로 전체 파이프라인을 빠르게 프로토타입으로 검증했습니다.
파이프라인 검증 후 아래 세 가지 이유로 FastAPI로 전환했습니다.

1. **커스텀 로직 제어**: 법령 위계 정렬, 파일명 패턴 분류 등 도메인 특화 로직 구현
2. **비용 절감**: OpenAI API → Ollama 로컬 모델로 전환
3. **인프라 단순화**: DB, 인증, 채팅, 업로드를 단일 서버에서 관리

---

## 시작하기

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ (pgvector 확장 포함)
- Ollama (qwen3.5:35b-a3b, qwen3-embedding:4b 모델)
- Tavily API 키

### 환경변수 설정

`.env` 파일을 생성합니다.

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tax_db
JWT_SECRET=your-long-random-secret-here
JWT_EXPIRE_MIN=1440
OLLAMA_BASE_URL=http://localhost:11434
CHAT_MODEL=qwen3.5:35b-a3b
EMBED_MODEL=qwen3-embedding:4b
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx
```

> JWT_SECRET 생성: `python -c "import secrets; print(secrets.token_hex(32))"`

### Ollama 모델 설치

```bash
ollama pull qwen3.5:35b-a3b
ollama pull qwen3-embedding:4b
```

### DB 초기화

```bash
# Docker로 PostgreSQL 실행
docker compose up -d

# 또는 직접 초기화
psql -U postgres -c "CREATE DATABASE tax_db;"
psql -U postgres -d tax_db -f init_db.sql
```

### 백엔드 실행

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

---

## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/auth/signup` | 회원가입 | 불필요 |
| POST | `/api/auth/login` | 로그인 (쿠키 발급) | 불필요 |
| POST | `/api/auth/logout` | 로그아웃 (쿠키 삭제) | 불필요 |
| POST | `/api/upload` | PDF 업로드 및 벡터 저장 | 필요 |
| POST | `/api/chat` | 채팅 질문 전송 | 필요 |
| GET | `/api/health` | 서버 및 DB 상태 확인 | 불필요 |

자동 생성 API 문서: http://localhost:8000/docs

---

## 주요 설정값

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `EMBED_MODEL` | qwen3-embedding:4b | 임베딩 모델 |
| `CHAT_MODEL` | qwen3.5:35b-a3b | 답변 생성 모델 |
| `CHUNK_SIZE` | 800 | 청크당 토큰 수 |
| `CHUNK_OVERLAP` | 100 | 청크 간 겹치는 토큰 수 |
| `TOP_K` | 10 | 벡터 검색 결과 수 |
| `MEMORY_TURNS` | 3 | 채팅 메모리 보관 턴 수 |
| `JWT_EXPIRE_MIN` | 1440 | JWT 만료 시간 (분) |
| `EMBED_DIM` | 2560 | 임베딩 벡터 차원 |

---

## 한계 및 개선 과제

- 스캔 PDF 미지원 → pytesseract, AWS Textract 연동으로 개선 가능
- 유저당 단일 세션 구조 → sessions 테이블 분리로 멀티 대화 지원 가능
- 토큰 기준 청크 분할 → RecursiveCharacterTextSplitter로 문장 경계 보완 가능
- Cross-Encoder Re-ranker 미적용 → bge-reranker 추가로 검색 품질 향상 가능
- 법령 개정 시 재업로드 필요 → 법제처 API 연동 하이브리드 구조로 개선 가능