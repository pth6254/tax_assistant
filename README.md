# 세무 AI 어시스턴트

대한민국 세무 법령 PDF를 업로드하면 RAG(Retrieval-Augmented Generation) 기반으로 법적 근거와 함께 답변하는 AI 어시스턴트입니다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | FastAPI, asyncpg, pgvector, OpenAI API |
| 프론트엔드 | React 18, Vite |
| 데이터베이스 | PostgreSQL + pgvector |
| 인증 | JWT (httpOnly 쿠키) |
| 임베딩 | text-embedding-3-small (1536차원) |
| LLM | gpt-4o-mini |

---

## 프로젝트 구조

```
tax-assistant/
│
├── main.py                    # 앱 진입점. 라우터 등록, DB 풀 시작/종료, lifespan 관리
├── config.py                  # 환경변수 중앙 관리. 모든 설정값을 여기서만 읽음
├── init_db.sql                # PostgreSQL 초기화 스크립트
├── .gitignore
│
├── frontend/                  # React 프론트엔드 (Vite)
│   ├── index.html             # Vite 진입점 HTML
│   ├── package.json           # 의존성 정의 (React, marked, Vite)
│   ├── vite.config.js         # Vite 설정. /api 요청을 FastAPI(8000)로 프록시
│   └── src/
│       ├── main.jsx           # React 앱 마운트 진입점
│       ├── App.jsx            # 루트 컴포넌트. 로그인 여부에 따라 화면 분기
│       ├── index.css          # 전역 CSS 변수, 리셋, 애니메이션
│       ├── markdown.css       # AI 응답 마크다운 렌더링 스타일
│       │
│       ├── api/               # FastAPI 엔드포인트 호출 함수 모음
│       │   ├── authApi.js     # 로그인, 회원가입, 로그아웃 API 호출
│       │   ├── chatApi.js     # 채팅 메시지 전송 API 호출
│       │   └── uploadApi.js   # PDF 파일 업로드 API 호출
│       │
│       ├── hooks/             # React 상태 관리 커스텀 훅
│       │   ├── useAuth.js     # 로그인/로그아웃 상태, user 정보 관리
│       │   └── useChat.js     # 채팅 메시지 목록, 로딩 상태 관리
│       │
│       └── components/        # UI 컴포넌트
│           ├── Auth/
│           │   └── AuthScreen.jsx    # 로그인/회원가입 탭 화면
│           ├── Sidebar/
│           │   ├── Sidebar.jsx       # 사이드바 전체. 업로드 영역 + 파일 목록 + 유저 정보
│           │   └── FileUpload.jsx    # PDF 드래그앤드롭 업로드 UI
│           └── Chat/
│               ├── ChatArea.jsx      # 채팅 화면 전체. 메시지 목록 + 스크롤 관리
│               ├── MessageBubble.jsx # 개별 말풍선. 사용자/AI 스타일 분기, 마크다운 렌더링
│               └── ChatInput.jsx     # 텍스트 입력창. Enter 전송, 자동 높이 조절
│
└── app/                       # FastAPI 백엔드
    ├── routers/               # HTTP 요청 수신. 입력 검증 후 service로 위임
    │   ├── auth.py            # POST /api/auth/signup, /login, /logout
    │   ├── chat.py            # POST /api/chat, GET /api/health
    │   └── upload.py          # POST /api/upload
    │
    ├── services/              # 핵심 비즈니스 로직
    │   ├── auth_service.py    # 이메일 중복 확인, bcrypt 해싱, JWT 발급
    │   ├── chat_service.py    # 세목 분류 → 임베딩 → 벡터 검색 → 메모리 → GPT 답변 (RAG 파이프라인 전체)
    │   └── upload_service.py  # PDF 파싱 → AI 분류 → 청크 분할 → 임베딩 → pgvector 저장
    │
    ├── utils/                 # 공통 유틸 함수. 비즈니스 로직 없음
    │   ├── jwt.py             # JWT 생성, httpOnly 쿠키 설정/삭제, 토큰 검증
    │   ├── embeddings.py      # OpenAI 클라이언트 싱글턴, 텍스트 → 임베딩 벡터 변환
    │   └── pdf.py             # PDF 텍스트 추출, tiktoken 기반 청크 분할
    │
    └── database.py            # asyncpg 커넥션 풀 싱글턴 관리
```

---

## 계층 간 호출 흐름

```
HTTP 요청
  → routers/      (입력 검증, 인증 확인)
  → services/     (비즈니스 로직 실행)
  → utils/        (공통 기능 호출)
  → database.py   (DB 접근)
```

각 계층은 단방향으로만 흐릅니다. `utils/`가 `services/`를 import하거나 `routers/`가 직접 DB에 접근하는 일이 없습니다.

---

## RAG 파이프라인

```
질문 입력
  → 세목 키워드 매핑 (소득세, 부가세 등)
  → 키워드 매핑 실패 시 GPT로 세목 분류
  → 질문 임베딩 (text-embedding-3-small)
  → pgvector 유사도 검색 (법령 필터 적용)
  → 최근 대화 메모리 조회 (최근 3턴)
  → GPT 답변 생성 (gpt-4o-mini)
  → 대화 메모리 저장
  → 답변 반환
```

---

## 시작하기

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- PostgreSQL 15+ (pgvector 확장 포함)

### 환경변수 설정

`.env` 파일을 생성합니다.

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/tax_db
OPENAI_API_KEY=sk-...
JWT_SECRET=your-long-random-secret-here
JWT_EXPIRE_MIN=1440
```

> JWT_SECRET 생성: `python -c "import secrets; print(secrets.token_hex(32))"`

### DB 초기화

```bash
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

## 주요 설정값 (config.py)

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `EMBED_MODEL` | text-embedding-3-small | 임베딩 모델 |
| `CHAT_MODEL` | gpt-4o-mini | 답변 생성 모델 |
| `CHUNK_SIZE` | 800 | 청크당 토큰 수 |
| `CHUNK_OVERLAP` | 100 | 청크 간 겹치는 토큰 수 |
| `TOP_K` | 10 | 벡터 검색 결과 수 |
| `MEMORY_TURNS` | 3 | 채팅 메모리 보관 턴 수 |
| `JWT_EXPIRE_MIN` | 1440 | JWT 만료 시간 (분) |
