# 설치·실행·테스트

로컬 실행(Docker Compose·WSL), 환경 변수, 테스트 실행, 자주 생기는 문제와 해결 방법입니다.

[← README로 돌아가기](../README.md)


## 시작하기

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (PostgreSQL + pgvector 포함)
- [Ollama](https://ollama.com) 설치
- NVIDIA GPU 드라이버 및 WSL Docker용 NVIDIA Container Toolkit (llama.cpp CUDA 사용 시)
- [Tavily API Key](https://tavily.com) (선택, 웹검색 보완 기능)
- [국가법령정보 Open API Key](https://www.law.go.kr/LSO/openApi/openApiIntroPage.do) (법령 자동 수집 시 필요)

### 1단계: 환경변수 설정

`.env` 파일을 프로젝트 루트에 생성합니다.

```env
# Database (Docker Compose 기준 호스트 포트 5433)
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/tax_db

# JWT
JWT_SECRET=replace-with-a-long-random-secret   # 생성: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_EXPIRE_MIN=1440

# 생성 LLM: OpenRouter GPT-6 Luna 유료 모델 (키는 실제 .env에만 입력)
LLM_PROVIDER=openrouter
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=
CHAT_MODEL=openai/gpt-6-luna
# 필요할 때 작업별로 오버라이드 (아래 설명 참고)
# LLM_TASK_TOOL_SELECTION_REASONING_EFFORT=low

# Ollama 임베딩 — 실행 환경에 따라 아래 "Ollama 연결 설정" 참고
OLLAMA_BASE_URL=http://localhost:11434
EMBED_MODEL=qwen3-embedding:4b
# 아래 두 값은 생성 LLM을 Ollama로 되돌릴 때만 적용
OLLAMA_NUM_CTX=4096
OLLAMA_KEEP_ALIVE_SEC=-1

# 외부 API (선택)
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxx
LAW_API_KEY=your-law-api-key-here
```

> JWT_SECRET 생성: `python -c "import secrets; print(secrets.token_hex(32))"`

운영 LLM 호출은 `ANSWER`, `HISTORY_ANSWER`, `CITATION_EXTRACTION`, `QUERY_CLASSIFICATION`,
`TOOL_SELECTION`, `DOCUMENT_CLASSIFICATION`, `QUESTION_PLANNING`, `ANSWER_JUDGE`, `FACT_READING`(채팅 계산의 대화 사실 읽기)의 9개 작업으로 구분합니다. 기본은 모두
`LLM_PROVIDER`/`CHAT_MODEL`을 상속하므로 OpenRouter GPT-6 Luna 하나로 실행됩니다.
각 작업에 `LLM_TASK_<작업명>_PROVIDER`, `_MODEL`, `_BASE_URL`, `_API_KEY`,
`_REASONING_EFFORT`, `_THINK_ENABLED`, `_TIMEOUT_SEC`, `_TEMPERATURE`, `_MAX_TOKENS`를
개별 설정할 수 있습니다. 예를 들어 도구 선택만 로컬 Ollama로 전환하려면 실제 `.env`에
`LLM_TASK_TOOL_SELECTION_PROVIDER=ollama`, `LLM_TASK_TOOL_SELECTION_MODEL=qwen3.5:9b`를
설정합니다. 이때 Ollama 주소는 기본 `OLLAMA_BASE_URL`을 사용하고 모델을 미리 설치해야 합니다.
직접 OpenAI provider를 쓰는 작업은 `OPENAI_API_KEY` 또는 해당 작업의 `_API_KEY`가 필요합니다.
`REASONING_EFFORT`는 지원하는 원격 모델에 전달하고, Ollama/llama.cpp의 추론 사용 여부는
`THINK_ENABLED=true|false`로 제어합니다. 작업별 `MAX_TOKENS`는 기존 호출값을 덮어쓰지만
원격 호출에는 `LLM_REMOTE_MAX_TOKENS` 전역 상한이 계속 적용됩니다. 설정 변경 후 백엔드를
재시작하고 `python dev/probe_chat_routing.py`로 비식별 점검을 수행하세요.
`TEMPERATURE`는 해당 모델이 허용할 때만 전달되며 Luna처럼 추론 모델에서는 적용되지 않습니다.
`/api/health/dependencies`의 `llm_tasks`는 9개 작업 상태를, 기존 `llm`/`routing_llm`은
답변/도구 선택 상태를 표시합니다.

OpenRouter 키를 발급받아 **실제 `.env`의 `OPENROUTER_API_KEY`에만** 입력한 후 WSL에서
`source venv-wsl/bin/activate`와 `bash dev/docker-up-wsl.sh backend`를 실행합니다.
키가 비어 있으면 LLM 상태는 `configuration_missing`이며 답변 생성은 사용할 수 없습니다.
`openai/gpt-6-luna`는 OpenRouter의 **유료** 생성 모델입니다. 크레딧·사용량 한도를 확인하고
[OpenRouter 모델 페이지](https://openrouter.ai/openai/gpt-6-luna)에서 현재 가격을 확인하세요.
기존 Qwen 무료 엔드포인트의 제공자 측 429를 피하려는 전환이며 유료 모델도 429가 완전히 없어지는 것은 아닙니다.
Luna 요청에는 `temperature`를 보내지 않습니다. 기본 추론 수준은 최종 답변·과거법령 설명·인용 추출·도구 선택은
`low`, 업로드 문서 분류는 `none`입니다. 각 작업의 `_REASONING_EFFORT`로 조정할 수 있습니다.
도구 선택 1,024·검색어 분류 1,024·인용 추출 2,048·과거법령 설명 4,096토큰으로 구분하며,
원격 생성의 **1회 출력** 상한은 `LLM_REMOTE_MAX_TOKENS=8192`입니다. 이는 입력 컨텍스트 한도가 아닙니다.
출력 길이 제한으로 끝난 생성은 이어 쓰지 않고 실패로 처리합니다(쟁점 단위 생성·Judge의 출력 예산은
`claim_verification`의 `GENERATION_MAX_TOKENS`·`JUDGE_MAX_TOKENS`). 429·연결 오류는 출력 길이 중단으로 취급하지 않습니다.
각 원격 요청에는 `LLM_TIMEOUT_SEC=180`의 전체 응답 제한 시간도 적용합니다.
HTTP 429만 응답 시작 전 최대 두 번 재시도합니다. `Retry-After`가 4초를 넘으면 즉시 안내하며,
중간 스트림 오류·시간 초과·잔액 부족은 자동 재호출하지 않습니다. 429/잔액/시간 초과는 UI에 구분해 전달합니다.
단일 법령·조문 원문 요청은 파서로 바로 조회하여 도구 선택 LLM 호출을 생략합니다.
사용량은 제공자가 반환하는 토큰 수·비용 등 숫자 메타데이터만 로그에 기록합니다.
Compose 채팅의 LangSmith 추적은 `CHAT_TRACING_ENABLED=true`로 켭니다. 채팅 요청과 스트림 전체를
`chat_request`/`chat_stream` 루트 실행으로 기록하고 내부 LangChain 단계도 함께 추적합니다.
실제 `.env`에 `LANGSMITH_API_KEY`가 있어야 하며 기존 `LANGSMITH_PROJECT`로 기록합니다.
질문·답변·검색 근거가 LangSmith에 전송되므로 민감정보 전송 정책을 확인하세요.
LangSmith의 월간 추적 한도가 소진되면 앱은 동작해도 새 추적은 원격에 저장되지 않을 수 있습니다.
합성 추적 확인은 `docker exec tax_backend python -m dev.probe_langsmith_chat`으로 수행합니다.
모델 전환 시 WSL 가상환경에서 `PYTHONPATH=. python dev/probe_openrouter_model.py <모델 ID>`로 비식별 일반·스트리밍·JSON Schema 응답을 확인합니다.
`--pipeline`을 붙이면 실제 도구 인자 추출과 인용·과거법령 JSON Schema도 합성 입력으로 검사합니다(유료 API 호출).
구조화 응답이 비어 있거나 유효한 JSON이 아니면 한 번만 재시도하고, 두 번 모두 실패하면
완료된 답변으로 취급하지 않습니다. 이는 법령 인용·계산 결과의 정확도 보증을 뜻하지 않습니다.
질문·대화 이력·검색된 법령/사용자 문서 발췌문은 외부 제공자에게 전송되므로 민감한 실사용자
세무 자료는 제공자 데이터 정책을 검토하기 전에는 보내지 마세요. 임베딩은 기존 Ollama와
2560차원 DB 벡터를 그대로 사용하며, 생성 LLM만 전환합니다.

### 2단계: Ollama 임베딩 모델 설치

```bash
ollama pull qwen3-embedding:4b
```

현재 생성·계획·Judge는 OpenRouter를 사용하므로 로컬 생성 모델 설치가 필요하지 않습니다.
Ollama의 `qwen3.5:9b`는 생성 또는 개별 작업을 Ollama로 전환할 때만 설치합니다.

#### 실행 환경별 Ollama 연결 설정

`OLLAMA_BASE_URL`은 FastAPI가 **어디서 실행되는지**를 기준으로 설정합니다.

| 실행 환경 | 설정 예시 | 설명 |
|----------|----------|------|
| Windows에서 FastAPI 직접 실행 | `http://localhost:11434` | FastAPI와 Ollama가 같은 호스트에서 실행 |
| Windows Ollama + WSL2 Docker | `http://ollama.windows.host:11434` | 실행 스크립트가 현재 Windows IP를 별칭에 자동 연결 |
| Linux 운영 서버의 Compose Ollama | `http://ollama:11434` | Docker 내부 DNS의 서비스명 사용 권장 |
| 별도 GPU 추론 서버 | `http://inference.internal:11434` | 사설 DNS 또는 내부 로드밸런서 사용 |

현재 개발 환경은 **Windows에서 Ollama를 실행하고 WSL2에서 Docker를 실행**합니다. WSL2의
`localhost`는 Windows 호스트가 아니며 NAT 게이트웨이 IP도 재시작 후 달라질 수 있습니다.
이를 해결하기 위해 전용 실행 스크립트가 매번 현재 주소를 탐지합니다.

```bash
# WSL: Windows IP·Ollama 필수 모델 확인, Graph 사용 시 Neo4j 준비, 현재 provider로 실행
source venv-wsl/bin/activate
bash dev/docker-up-wsl.sh backend frontend
```

스크립트는 탐지한 IP를 `OLLAMA_WINDOWS_IP`로 Compose에 전달하고, 컨테이너에는 고정된
`ollama.windows.host` 별칭을 등록합니다. 애플리케이션은 변동 가능한 실제 IP를 알 필요가 없습니다.

```text
WSL 기본 게이트웨이 자동 탐지 (예: 172.x.x.1)
        ↓
ollama.windows.host 별칭으로 Compose에 주입
        ↓
FastAPI → http://ollama.windows.host:11434
```

`.env`의 `OLLAMA_BASE_URL=http://localhost:11434`는 Docker 없이 FastAPI를 직접 실행할 때
사용합니다. Docker 환경에서는 Compose가 위 별칭 주소로 덮어씁니다. 운영 환경에서는 동일한
설정 인터페이스를 유지하되 Compose 서비스명(`http://ollama:11434`) 또는 사설 DNS를 사용합니다.

### 3단계: DB 실행 및 자동 마이그레이션

현재 서비스는 OpenRouter 생성과 Windows Ollama 임베딩을 사용합니다. `.env`에 앞 절의 모델 역할을
명시하고 WSL에서 다음 명령으로 백엔드·프런트엔드를 재빌드합니다.

```bash
cd '/mnt/c/Users/Laptop PC/Desktop/tax_assistant'
source venv-wsl/bin/activate
bash dev/docker-up-wsl.sh backend frontend
```

스크립트는 GraphRAG가 켜진 경우 Neo4j를 먼저 기동·확인합니다. 모델 이름·provider를 자동으로
llama.cpp로 바꾸지 않습니다. 새로운 환경은 코드 기본값이 Ollama이므로 OpenRouter 설정과 키를
별도로 입력해야 합니다.

#### 선택형 llama.cpp·임베딩 v2 실험

로컬 생성/임베딩 비교를 명시적으로 수행할 때만 `bash dev/docker-up-llamacpp-wsl.sh`를 사용합니다.
이 overlay는 Qwen3.5-9B GGUF 생성 서버와 Qwen3 Embedding 4B GGUF 비교 서버를 구성합니다.

생성 서버는 GPU를 사용하고 임베딩 서버는 12GB VRAM 충돌을 막기 위해 CPU를 사용합니다.
임베딩은 Qwen 권장값인 `--pooling last`를 강제합니다. 기존 pgvector 데이터는 즉시
교체하지 않으며 `embedding_v2` 백필과 골든셋 평가를 통과한 뒤 활성화합니다.

```bash
# Ollama v1과 llama.cpp v2 벡터 비교
docker exec tax_backend python scripts/compare_embedding_providers.py

# 백필 대상 확인 후 실제 실행
docker exec tax_backend python scripts/backfill_embeddings_v2.py --table all
docker exec tax_backend python scripts/backfill_embeddings_v2.py --table all --run

# v2 환경을 별도로 설정한 뒤 실제 검색 진단 (draft 결과는 품질 승인 아님)
docker exec tax_backend python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft
```

`contracts.json` 합성 계약은 벡터 품질 평가가 아닙니다. 위 draft 실행도 독립적인 품질 승인 점수가 아닙니다.
`EMBEDDING_VERSION=v2`는 대상 벡터 준비·입력 이력을 확인하고 별도 전문가 holdout에서 v1 대비 검색/답변 회귀와
지연을 검수한 뒤 적용합니다. `v1`로 되돌리면 기존 검색으로 롤백됩니다.

WSL Docker에서 `could not select device driver ... gpu` 오류가 발생하면 NVIDIA Container
Toolkit을 WSL 안에 한 번 설치합니다.

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi
bash dev/docker-up-llamacpp-wsl.sh
```

선택형 overlay의 최초 실행은 모델 다운로드와 적재로 시간이 걸리며 `llama_cache` volume을 재사용합니다.
현행 OpenRouter/Ollama 조합을 다시 사용하려면 기본 Compose의 `dev/docker-up-wsl.sh backend frontend`를 실행합니다.

`docker compose up -d --build`를 직접 실행하면 현재 Windows 주소를 알 수 없으므로 의도적으로
설정 오류를 반환합니다. 자동 탐지 없이 직접 실행해야 한다면 먼저 `OLLAMA_WINDOWS_IP`를
명시적으로 export해야 합니다.

```bash
export OLLAMA_WINDOWS_IP="$(ip -4 route show default | awk 'NR == 1 { print $3 }')"
docker compose -f docker-compose.yml up -d --build backend frontend
```

이 직접 실행은 그래프 의존성 확인을 자동으로 하지 않으므로 일반 개발·재빌드는 WSL 스크립트를 사용합니다.

Docker 실행 후 웹 서비스는 **http://localhost:3001**에서 접속합니다. 호스트 3001 포트를 프런트엔드 Nginx의 80 포트에 연결하며 `/api` 요청은 Docker 내부의 백엔드 `backend:8000`으로 전달합니다. 백엔드 직접 접근과 API 문서는 호스트의 **http://localhost:8001**(`127.0.0.1` 바인딩)을 사용합니다. Vite 개발 서버 포트는 기존 5173을 유지하고 API 프록시는 호스트 8001을 사용합니다. 선택형 llama.cpp 생성 서버의 호스트 포트는 충돌을 피하기 위해 8004로 옮겼으며 컨테이너 내부 포트 8080은 그대로입니다.

백엔드는 시작 전에 자동으로 `alembic upgrade head`를 실행합니다. 새 DB에는 전체 스키마와
세율 시드가 생성되고, 기존 DB에는 적용되지 않은 revision만 반영됩니다. 마이그레이션이
실패하면 API 서버는 시작하지 않으므로 불완전한 스키마로 서비스되는 것을 방지합니다.

이 프로젝트는 기존 `asyncpg` 기반 데이터 접근 계층을 유지하면서, 마이그레이션에만
Alembic + SQLAlchemy + psycopg를 사용합니다. 최초 baseline revision은 기존 SQL 기반 DB를
데이터 손실 없이 Alembic 관리 체계로 편입하고, 빈 DB에서는 전체 스키마를 생성합니다.

```bash
# 현재 적용된 revision 확인
docker exec tax_backend alembic current

# 코드의 최신 revision 확인
docker exec tax_backend alembic heads

# 전체 revision 이력 확인
docker exec tax_backend alembic history

# 새 DB 변경 revision 생성
docker exec tax_backend alembic revision -m "add new field"
```

> 앞으로의 DB 변경은 `db/migrations/*.sql`을 직접 실행하지 않고 새 Alembic revision의
> `upgrade()`와 `downgrade()`에 작성합니다. 이미 배포된 revision 파일은 수정하지 않습니다.

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
uvicorn main:app --reload --port 8001
```

### 6단계: 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

---

### 지인에게 공유하기(Cloudflare 빠른 터널)

이 PC에서 돌아가는 서비스를 HTTPS 주소로 몇 사람에게 공유하는 방법입니다. PC가 켜져 있고 Docker 서비스와 Ollama가
실행 중일 때만 접속됩니다.

1. `.env`에 `SIGNUP_INVITE_CODE`(가입 초대 코드), `CHAT_DAILY_LIMIT_PER_USER`(이용자당 하루 질문 수, 기본 20),
   `CHAT_DAILY_LIMIT_TOTAL`(서비스 전체 하루 질문 수, 0이면 제한 없음), `COOKIE_SECURE=true`, `CHAT_TRACING_ENABLED=false`를 둡니다.
2. WSL에서 `./dev/docker-up-wsl.sh backend frontend`, Windows에서 Ollama를 실행합니다.
3. PowerShell에서 `powershell -ExecutionPolicy Bypass -File dev/share-tunnel.ps1`을 실행하고 출력된
   `https://….trycloudflare.com` 주소와 초대 코드를 공유합니다. 창을 닫으면 공유가 끝나고, 다시 열면 주소가 바뀝니다.

DB(5433)·프런트엔드(3001)·pgAdmin(5050) 포트는 이 PC에서만 열리며 pgAdmin은 `--profile admin`으로만 뜹니다. 질문 한도는 답변이 시작되기
전에 기록되므로 중단한 답변도 1회로 셉니다(`chat_usage`). 백업은 WSL에서 `./dev/backup-db.sh`(최근 7개 보관, `backups/`). 백업 파일은 같은
PC에 있으므로 다른 저장소에도 복사해 두세요. 고정 주소가 필요하면 Cloudflare 계정·도메인으로 이름 있는 터널을 만들거나 서버로 옮깁니다.

### Vercel에 화면 배포하기(백엔드는 이 PC)

화면은 Vercel에서, 백엔드는 이 PC에서 고정 주소(Tailscale Funnel 등)로 엽니다. Vercel이 `/api/*` 요청을 백엔드로 넘겨주므로
브라우저에는 같은 사이트라서 로그인 쿠키가 그대로 동작합니다(`frontend/vercel.json`).

1. Vercel에서 GitHub 저장소를 가져오고 **Root Directory를 `frontend`**로 지정합니다. 빌드 설정은 `vercel.json`이 정합니다
   (`npm ci` → `npm run build` → `dist`). 업로드 한도는 `frontend/.env.production`의 `VITE_MAX_UPLOAD_MB=4`입니다.
2. `frontend/vercel.json`의 `REPLACE-WITH-BACKEND-HOST`를 백엔드 고정 주소(예: `pc-name.tailnet-name.ts.net`)로 바꿔 푸시합니다.
   바꾸기 전에는 화면만 열리고 로그인 화면에 "데모 서버가 꺼져 있습니다"가 표시됩니다.
3. 백엔드 `.env`는 `COOKIE_SECURE=true`, `MAX_UPLOAD_MB=4`. 답변 스트림은 15초마다 SSE 주석을 보내 Vercel의 120초 무응답 차단을 피합니다.

## 테스트

> 테스트 도구는 `requirements-dev.txt`에 있습니다(서비스 이미지는 `requirements.txt`만 설치). 테스트는 개발자의 `.env`를 읽지 않고
> DB에 연결하지 않으므로 어느 PC에서나 CI와 같은 결과가 나옵니다(`tests/conftest.py`).
> `.github/workflows/ci.yml`이 push/PR마다 비밀값 검사·컴파일 검사(`compileall`)·전체 테스트를 자동 실행합니다.
> 커밋 전에 API 키나 `.env`의 비밀값(`*KEY*`·`*SECRET*`·`*PASSWORD*`·`*TOKEN*`)이 섞이면 막으려면 clone마다 한 번
> `sh dev/install-git-hooks.sh`를 실행합니다(`scripts/check_secrets.py --staged`, 값은 출력하지 않음).

### 전체 테스트 실행

```bash
pip install -r requirements-dev.txt   # 처음 한 번
python -m pytest -q
```

백엔드 구현 변경 후 현재 코드로 이미지를 재빌드하고 실행합니다. 프런트엔드 변경은 `frontend/`에서
`npm test`와 `npm run build`를 수행합니다. WSL 가상환경의 로컬 단위 검사와 실제 생성/웹/세무 정답 검수를 구분합니다.
마지막 완료 수치는 맨 위 요약을 참고하며 문서만 변경한 작업에서는 전체 테스트 수를 새 실행 결과로 보고하지 않습니다.

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
pytest tests/test_calculator.py -v          # 세금 계산기 공통 세율 구간·공제 로직
pytest tests/test_income_tax.py tests/test_capital_gains.py tests/test_retirement.py tests/test_virtual_asset.py \
       tests/test_inheritance.py tests/test_gift_tax.py tests/test_vat_penalty.py -v   # 세목별 계산기·공식 사례
pytest tests/test_income_tax_chat.py tests/test_capital_gains_chat.py tests/test_inheritance_chat.py \
       tests/test_gift_chat.py tests/test_vat_penalty_chat.py -v   # 채팅 질문 → 계산기 입력·되묻기
pytest tests/test_calculator_engine.py tests/test_tools.py -v   # 계산기·공통 도구 호출
pytest tests/test_citation_guard.py -v      # 답변 인용·수치 검증 후처리
pytest tests/test_tax_schedule.py -v        # 세무 일정 계산
pytest tests/test_jwt.py -v                 # JWT 토큰
pytest tests/test_api_auth.py -v            # 인증 API
pytest tests/test_api_upload.py -v          # 업로드 API
pytest tests/test_api_chat.py -v            # 채팅 API
pytest tests/test_api_law.py -v             # 조문 원문 뷰어 API
pytest tests/test_law_reference.py -v        # 조·항·호·목 법령 참조 파서
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
| `test_calculator.py` | 세금 계산기 공통 세율 구간·공제 로직 | 시드 데이터 mock |
| `test_income_tax.py`, `test_capital_gains.py`, `test_retirement.py`, `test_virtual_asset.py`, `test_inheritance.py`, `test_gift_tax.py`, `test_vat_penalty.py` | 세목별 계산 산식·국세청 공식 사례(가상자산은 법조문 산식) | 세율 파라미터 직접 주입 |
| `test_income_tax_chat.py`, `test_capital_gains_chat.py`, `test_inheritance_chat.py`, `test_gift_chat.py`, `test_vat_penalty_chat.py` | 채팅 질문의 계산기 입력 해석·가정·되묻기 | LLM mock |
| `test_chat_calculator_reading.py` | 채팅 점검에서 찾은 해석 오류(보유 N년, 1주택 부정, 같은 해 먼저 양도, 보증금·종교인소득, "가산세 포함 얼마", "한 달 안에")와 6개 세목의 모델 선택 생략 | LLM mock |
| `test_calculator_engine.py`, `test_tools.py` | 공통 도구 선택·계산 실행·사용자 격리·실패 경계 | LLM/DB mock |
| `test_citation_guard.py` | 조문 인용 실존 검증, 계산 금액 일치 검증 | DB·외부 의존 없음 |
| `test_tax_schedule.py` | 사업자 유형별 신고 기한 계산 | DB·외부 의존 없음 |
| `test_jwt.py` | JWT 토큰 생성 및 클레임 검증 | DB·외부 의존 없음 |
| `test_api_auth.py` | 회원가입·로그인 유효성 검사 및 응답 코드 | 서비스 레이어 mock |
| `test_api_upload.py` | 인증 확인(401), 파일 형식 검사(400), 정상 업로드 | 서비스 레이어 mock |
| `test_api_calculator.py` | 인증 확인(401), 유효성 검사(422), 부가세·가산세 계산 응답 | DB mock |
| `test_penalty_option.py` | 세목 계산기의 가산세 옵션·종합소득세의 가상자산 분리과세·채팅 경로 | 세율 파라미터 직접 주입 |
| `test_calculator_finish.py` | 퇴직소득 과세이연·입주권 비과세·비교과세·간주임대료·종교인소득·영세율 가산세·과소신고 신고세액공제 | 세율 파라미터 직접 주입 |
| `test_api_chat.py` | 인증 확인(401), 유효성 검사(422), 계산기 메타데이터·스트리밍 이벤트 | 서비스 레이어 mock |
| `test_api_law.py` | 조문 원문 뷰어 조회(200)·404 | 서비스 레이어 mock |
| `test_law_reference.py` | 조·항·호·목 구조 파싱, 가지번호 구분, 조문번호 정규화 | DB·외부 의존 없음 |
| `test_api_tax_schedule.py` | 인증 확인(401), 사업자 유형별 일정 응답 | 서비스 레이어 mock |

| `test_chat_service.py` | 세목 키워드 매칭(겹침 억제), 평가용 고정 근거 프롬프트 조립, 계산기 메타 | LLM mock |
| `test_past_tax_tables.py` | 2021-01-01부터의 과거 세율표(Alembic 0022) 누진공제 연속성·법정 금액, 그때 없던 규정(주택 2년 미만 단기세율, 사적연금 15% 분리과세, 개편 전 간이과세) | 세율 파라미터 직접 주입 |
| `test_chat_routing.py` | 되묻기 답변의 계산 이어가기, 복합 질문 쟁점의 세목 분리, 과세 사건 날짜(`tax_date`)와 자료 없는 날짜 안내, 참고 계산 스트리밍 저장 | LLM mock |
| `test_hybrid_search.py` | 컨텍스트 포맷, 우선순위 정렬, 조문번호 fast path | DB·임베딩 mock |
| `test_clause_splitter.py` | 조문 항(項) 분할, 분할 대상 판정 | DB·외부 의존 없음 |
| `test_pdf_chunking.py` | PDF 조문 경계 인식 청킹 | DB·외부 의존 없음 |

> API 테스트는 실제 DB·Ollama 없이 실행됩니다. 서비스 레이어를 mock으로 대체하여 HTTP 계층의 동작을 검증합니다.

### 요소별 품질 평가 및 hard negative 검증

과거 법령 Knowledge Graph 관계 후보에는 [관계 전용 LLM Judge 절차](../evaluation/KG_RELATION_REVIEW.md)를 적용할 수 있습니다. 원본 재대조 → 관계 문구 판정 → 인간 확정 라벨과 비교를 분리하며, 모델 판정만으로 Neo4j 관계를 승인하지 않습니다.
법령 종류·시점별 표본 생성, `KG_JUDGE_*` 평가 전용 모델 설정, 건별 진행 저장과 `--resume` 재개 방법도 같은 문서에 있습니다. Judge 결과·혼동 후보 표시를 숨긴 블라인드 인간 검수 양식과 완료본 검증·골드 변환 절차도 제공하며, 변환 결과는 실서비스 관계 승인과 별개입니다.

```bash
# 합성 파싱·관계·산술 계약과 오답 반례 — DB/모델 불필요
python scripts/evaluate.py run --split all

# 실제 검색/Graph 비교: 미검수 라벨 진단이므로 통과가 아니라 exit 2 예상
python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft

# 모든 평가 영역 수집. 생성 호출은 --allow-generation으로 별도 허용
python scripts/evaluate.py suite --mode live --include-draft --output evaluation/runs/review-batch
```
새 결과는 Git/Docker 빌드에서 제외되는 `evaluation/runs/`에 보존합니다. 정답 데이터와 관측 결과는 별도 파일이며, 미판정 후보는 오답으로 간주하지 않습니다.
쟁점별 검색 후보 추적은 `python evaluation/issue_retrieval_probe.py /tmp/issue-retrieval.json --all`, 현행 법령 인덱스의 읽기 전용 감사는 `python evaluation/current_index_audit.py --all-core-recovery`로 실행할 수 있습니다. 두 진단은 백엔드 컨테이너에서 실행하며 DB를 수정하지 않습니다. 제목 일치 보완은 공식 법률 조문 후보를 최대 2건 추가하며 최종 관련성·시점·주장 검증을 대신하지 않습니다.
출처·기준일·검수 이력이 없는 기존 39문항은 draft로 이관했습니다. 합성 계약 통과를 세무 정답률로 표시하지 않습니다.
답변의 의미·법적 적용은 기준별 인간 검수를 요구하며 키워드/인용 존재만으로 통과시키지 않습니다. 반복 실행은 `--repeat N`, 동일 데이터셋 비교는 `compare`를 사용합니다.
기존 `eval_rag.py`·`eval_graph_rag.py`는 제거했습니다. 실행 명령은 `scripts/evaluate.py`로 통일하고, CLI 구현은 `evaluation/cli.py`에 둡니다. 과거 결과 파일은 보존합니다.
스키마·판정 기준·검수·재현 방법은 [평가 파이프라인 문서](../evaluation/README.md)를 참고하세요.

## 환경 변수

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `DATABASE_URL` | ✅ | `postgresql://postgres:postgres@localhost:5432/tax_db` | PostgreSQL 연결 URL |
| `JWT_SECRET` | ✅ | — | JWT 서명 비밀키 (32바이트 이상 권장) |
| `JWT_EXPIRE_MIN` | — | `1440` | JWT 만료 시간 (분, 기본 24시간) |
| `COOKIE_SECURE` | — | `false` | `true` 설정 시 HTTPS 전용 쿠키 (운영 환경에서 활성화) |
| `OLLAMA_BASE_URL` | — | `http://localhost:11434` | FastAPI 기준 Ollama 주소. WSL2 Docker 개발환경은 Windows 게이트웨이, 운영 Compose는 `http://ollama:11434` 권장 |
| `CHAT_MODEL` | — | `qwen3.5:9b` | 코드 기본값. 현행 서비스는 `openai/gpt-6-luna` 명시; 9개 작업이 상속 |
| `LLM_TASK_<작업명>_PROVIDER` | — | `LLM_PROVIDER` 값 | 각 AI 작업의 provider 독립 선택 |
| `LLM_TASK_<작업명>_MODEL` | — | `CHAT_MODEL` 값 | 각 AI 작업의 모델 독립 선택 |
| `LLM_TASK_<작업명>_REASONING_EFFORT` | — | Luna 작업별 `none`/`low` | 원격 추론 수준; 모델 지원값 사용 |
| `LLM_TASK_<작업명>_THINK_ENABLED` | — | `THINK_ENABLED` 값 | 로컬 Ollama/llama.cpp thinking 여부 |
| `LLM_TASK_<작업명>_BASE_URL`·`API_KEY`·`TIMEOUT_SEC`·`TEMPERATURE`·`MAX_TOKENS` | — | 공통 설정 또는 호출값 | 작업별 연결·출력 설정 |
| `LLM_PROVIDER` | — | `ollama` | 코드 기본값. 현행 서비스는 `openrouter` 명시; 선택형 `llamacpp` 등 지원 |
| `LLM_BASE_URL` | — | provider별 기본값 | OpenRouter 사용 시 `https://openrouter.ai/api/v1` |
| `OPENROUTER_API_KEY` | OpenRouter 사용 시 | — | OpenRouter 인증 키. 실제 `.env`에만 입력 |
| `EMBED_MODEL` | — | `qwen3-embedding:4b` | 임베딩 모델명 |
| `EMBEDDING_PROVIDER` | — | `ollama` | 임베딩 provider. `ollama` 또는 `llamacpp` |
| `EMBEDDING_BASE_URL` | — | Ollama 주소 | 활성 임베딩 provider 주소 |
| `EMBEDDING_VERSION` | — | `v1` | 검색 컬럼 선택. 검증 완료 후에만 `v2`로 전환 |
| `EMBEDDING_DUAL_WRITE` | — | `false` | 신규 데이터의 v1·v2 임베딩 동시 저장 여부 |
| `SEARCH_LEXICAL_BACKEND` | — | `bm25` | 공식 현행 쟁점 키워드 검색; `trigram`은 기존 경로 |
| `SEARCH_BM25_TITLE_WEIGHT` | — | `2` | 제목/본문 BM25의 제목 가중치 |
| `SEARCH_RRF_K` · `SEARCH_LEXICAL_WEIGHT` | — | `10` · `0.5` | BM25 경로 RRF 상수·키워드 가중치 |
| `SEARCH_FUZZY_ENABLED` · `SEARCH_REGEX_ENABLED` · `SEARCH_MMR_ENABLED` | — | `true` | 쟁점 검색의 개별 알고리즘 활성화 |
| `SEARCH_MMR_LAMBDA` | — | `0.85` | 순위 관련성과 중복도 비중 |
| `GRAPH_RAG_ENABLED` | — | `false` | 코드 기본 비활성, 사용 환경에서 현행 Graph 보충 활성화 |
| `ANSWER_JUDGE_MODE` | — | `shadow` | 의미 평가 모드. 법적 주장 등은 shadow에서도 의미 검사를 공개 조건으로 사용 |
| `CLAIM_SIGNAL_GATE` | — | `judge` | 단어 기반 추정 검사(세목·주체·범위 표현)를 Judge 확인 지점으로 전달(`judge`)하거나 직접 차단(`block`, 이전 동작) |
| `THINK_ENABLED` | — | `false` | Qwen3 계열 모델의 Think 모드 활성화 |
| `OLLAMA_NUM_CTX` | — | `4096` | 모든 chat 호출의 컨텍스트 길이 — 12GB GPU에서 생성·임베딩 동시 적재를 위한 기본값 |
| `OLLAMA_KEEP_ALIVE_SEC` | — | `-1` | Ollama 채팅 LLM의 유휴 언로드 대기시간(초). 임베딩 요청에는 적용하지 않음 |
| `EMBED_DIM` | — | `2560` | 임베딩 차원 수 (모델과 DB 일치 필수) |
| `SIMILARITY_THRESHOLD` | — | `0.4` | 검색 결과 최소 유사도 (0~1, 낮출수록 더 많은 결과 반환) |
| `MAX_UPLOAD_MB` | — | `50` | 사용자 문서 업로드 최대 크기 (MB) |
| `TAVILY_API_KEY` | — | — | Tavily 검색 API 키 (없으면 웹검색 생략) |
| `LAW_API_KEY` | — | — | 국가법령정보 Open API 키 (법령 수집 시 필요) |

## 트러블슈팅

### Windows Ollama에 WSL2/Docker 백엔드가 연결되지 않음

```text
httpx.ConnectError: [Errno 111] Connection refused
urllib.error.URLError: <urlopen error [Errno 111] Connection refused>
```

**원인**: Windows, WSL2, Docker 컨테이너는 각각 네트워크 경계가 다릅니다. 특히 WSL2 NAT
환경에서 `localhost`는 호출 주체 자신을 가리키므로, Windows에서 실행 중인 Ollama에 도달하지
못합니다. `host.docker.internal`도 Docker 실행 방식에 따라 Windows가 아니라 WSL/Docker
호스트 게이트웨이를 가리킬 수 있습니다.

다음 순서로 어느 네트워크 구간에서 실패하는지 확인합니다.

```powershell
# 1. Windows: Ollama 프로세스와 API 확인
Get-Process ollama
Invoke-RestMethod http://localhost:11434/api/tags
```

```bash
# 2. WSL2: Windows 게이트웨이 탐지 및 API 확인
WINDOWS_HOST_IP="$(ip -4 route show default | awk 'NR == 1 { print $3 }')"
curl --connect-timeout 3 "http://${WINDOWS_HOST_IP}:11434/api/tags"

# 3. 정상 실행 스크립트로 주소 재탐지 및 컨테이너 재생성
bash dev/docker-up-wsl.sh

# 4. 컨테이너: 별칭, 실제 환경변수와 연결 확인
docker exec tax_backend getent hosts ollama.windows.host
docker exec tax_backend printenv OLLAMA_BASE_URL
docker exec tax_backend python -c "
import os, urllib.request
base = os.environ['OLLAMA_BASE_URL'].rstrip('/')
print(urllib.request.urlopen(base + '/api/tags', timeout=5).status)
"
```

Windows에서는 정상인데 WSL2에서 실패한다면 Ollama가 loopback에만 바인딩됐을 가능성이 있습니다.
Windows 사용자 환경변수에 `OLLAMA_HOST=0.0.0.0:11434`를 설정하고 Ollama를 완전히 재시작합니다.
외부 인터페이스 바인딩 시에는 Windows 방화벽에서 11434 포트를 공용망 전체에 노출하지 말고
Docker/WSL 사설 네트워크로 접근 범위를 제한합니다.

```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
```

연결은 되지만 모델 호출이 실패하면 필수 모델을 확인합니다.

```bash
ollama list
ollama pull qwen3-embedding:4b
```

`dev/docker-up-wsl.sh`는 WSL 게이트웨이 IP 변경을 자동 반영하고, Ollama 연결 또는 필수 모델
검사에 실패하면 불완전한 상태로 Compose를 실행하지 않습니다. 운영 배포에서는 Windows 게이트웨이
대신 Ollama를 Compose 서비스로 실행하여 `OLLAMA_BASE_URL=http://ollama:11434`처럼 서비스
디스커버리를 사용합니다.

### 백엔드가 Alembic 오류로 계속 재시작됨

```
tax_backend  Restarting
FAILED: alembic upgrade head
```

백엔드는 마이그레이션 성공 후에만 FastAPI를 시작합니다. 따라서 migration SQL, DB 권한,
revision 그래프에 문제가 있으면 의도적으로 서버 시작을 중단합니다.

```bash
# 1. 실제 마이그레이션 오류 확인
docker compose logs --tail=150 backend

# 2. 코드가 가진 최신 revision 확인
docker compose run --rm backend alembic heads

# 3. DB에 적용된 revision 확인(백엔드가 실행 중일 때)
docker exec tax_backend alembic current

# 4. 미적용 revision 수동 재실행
docker compose run --rm backend alembic upgrade head
```

다음과 같은 임시 복구는 데이터와 코드의 실제 스키마를 불일치시키므로 사용하지 않습니다.

```text
alembic_version 테이블 직접 UPDATE
문제가 발생한 revision 파일 삭제
기존 db/migrations/*.sql 수동 재실행
운영 DB 볼륨 삭제 후 재생성
```

새 revision이 여러 갈래로 생성되어 `Multiple head revisions`가 발생했다면 먼저 그래프를
확인하고 merge revision을 생성합니다.

```bash
docker compose run --rm backend alembic heads
docker compose run --rm backend alembic merge heads -m "merge migration heads"
docker compose run --rm backend alembic upgrade head
```

> 최초 `20260719_0001` baseline은 기존 SQL 기반 DB를 채택하기 위한 마이그레이션이므로
> 데이터 보호를 위해 파괴적인 downgrade를 지원하지 않습니다. 이후 revision은 가능한 경우
> 명시적인 `downgrade()`를 함께 작성합니다.

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
OLLAMA_NUM_CTX=4096
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
불충분한 경우에만 웹검색이 실행되도록 실제 점수 분포에 맞춰 조정했다. 이 채팅 수준 유사도 경로는 뒤에 쟁점별 근거 충족 경로로
바뀌었고, 남아 있던 상수는 2026-10-12에 삭제했다(웹검색은 `question_planning`의 쟁점별 보충에서만 쓴다).

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

**과거 해결 기록**: 당시 `scripts/eval_rag.py`에 반복 실행을 추가했다. 현재는 그 CLI를 폐기했으며
[새 평가 실행기](../evaluation/README.md)의 `--repeat N`을 사용한다. 현재 검색 진단의 실행 예시는 다음과 같다.
```bash
python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft --repeat 3
```
생성 비교는 해당 답변 데이터셋·검수 범위와 `--allow-generation`을 별도로 지정한다.
개발/draft 라벨은 진단이고 독립 세무 정답 점수가 아니다. 생성은 반복 결과의 평균·편차·항목별 안정성을 보고,
검색 변경도 고정 코퍼스의 회수/순위와 cold/warm·반복 지연을 함께 비교한다.

### LLM provider(Ollama) 종속 — 답변 구조화·모델 교체 유연성
```
증상: chat_service.py가 Ollama의 HTTP 요청 스키마(think/keep_alive top-level, options 등)를
직접 조립해, 향후 vLLM이나 다른 모델로 교체하려면 호출부 전체를 다시 짜야 하는 구조
```
**원인**: `_call_ollama`/`_stream_ollama_response`가 `httpx.AsyncClient`로 Ollama의
`/api/chat`을 직접 호출하고 있어, provider 고유 스키마(어떤 필드가 top-level이고
어떤 게 `options` 안인지 등, 과거 `think`/`keep_alive` 배치 버그의 원인이기도 했다)에
비즈니스 로직이 그대로 결합돼 있었다.

**해결**: `app/services/llm_client.py`의 공통 인터페이스와 `inference/llm/`의
provider 어댑터를 분리했다. 초기에는 `ChatOllama`로 감쌌으나 2026-09-05에
Ollama도 `httpx` 기반 HTTP 어댑터로 교체하고 `langchain-ollama` 의존성을 제거했다.
`chat_service.py`는 `call_llm(...)` / `stream_llm(...)`만 호출한다.
`think`/`keep_alive`의 최상위 배치, `options` 내부 생성 설정, JSON Schema와
스트리밍 오류 처리를 `tests/test_ollama_llm_provider.py`에서 검증한다.

2026-09-05 HTTP 어댑터 전환 검증: 최신 Docker backend 전체 테스트 294개 통과.
`langchain_ollama`가 없는 이미지에서 실제 Ollama 일반 생성·스트리밍·JSON 구조화 응답을 확인했다.

초기 ChatOllama 도입 당시 결과: 218개 전체 테스트 통과, 실제 Ollama 서버 대상 스모크 테스트(비스트리밍/
스트리밍) 정상 동작, hit_rate@5·MRR·분류정확도(전부 검색 단계에서 결정되는 값이라
LLM 생성과 무관) 회귀 없음. 답변 품질 자체의 변화를 노린 작업이 아니라, provider
전환 비용을 낮추기 위한 내부 구조 개선이다.
