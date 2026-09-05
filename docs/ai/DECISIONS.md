# 주요 설계 결정

## ADR-019 — LangChain은 provider 위의 조합·검증 계층에 적용

- 결정: `langchain-core`의 ChatPromptTemplate·Runnable·PydanticOutputParser를 사용하고 자체 HTTP provider는 유지한다. `ChatOllama`는 재도입하지 않는다.
- 적용: 최종 답변 생성·스트리밍, 세목 분류, 계산기 입력 추출, 인용 목록 추출. 시스템 프롬프트 내용은 유지하고 사용자·검색 텍스트를 템플릿 변수로만 삽입한다.
- 검증: 완전한 JSON인지 먼저 검사하고 타입·필수 필드·인용 형식 및 계산기 입력을 검증한다. 오류 시 기존 fallback을 유지하며 자동 LLM 재호출은 추가하지 않는다.
- 추적: 단계별 실행 이름과 프롬프트 버전 메타데이터를 부여한다. LangSmith SDK는 간접 의존성으로 설치되지만 원격 추적·평가 연결은 후속 작업이다.
- 영향: ADR-018의 HTTP 어댑터 결정은 유지한다. 미사용으로 제거했던 `langchain-core`는 실제 용도가 생겨 재도입한다.

## ADR-018 — Ollama 생성도 직접 HTTP 어댑터 사용

- 결정: `ChatOllama` 대신 `httpx`로 Ollama `/api/chat`을 호출한다. `LLMProvider` 규약과 서비스 공통 호출 함수는 유지한다.
- 이유: provider 연결을 자체 어댑터에 모으고 `langchain-ollama`에 대한 실행 의존성을 없앤다. 후속 코드 정리에서 사용처가 없는 `langchain-core`도 제거했다.
- 공통 호출 인자는 `max_tokens`로 통일한다. provider는 프로세스 단위로 재사용하고 종료 시 닫으며 설정 변경은 재시작으로 적용한다. 테스트용 HTTP 주입 전역 변수와 불완전한 설정 캐시 키를 제거했다.
- 구현: 일반 생성, JSON Schema, NDJSON 스트리밍을 지원하며 기존 `options`·`think`·`keep_alive`를 보존한다. HTTP timeout·연결 종료·스트림 오류 및 불완전 종료를 처리한다.
- 범위: 실행 엔진과 모델은 교체하지 않는다. 임베딩은 기존 HTTP 어댑터를 유지한다.

이 문서는 이미 해결한 문제를 다음 세션에서 되돌리거나 같은 논의를 반복하지 않기 위한 기록이다.

## ADR-001 — n8n 프로토타입에서 코드 기반 구조로 전환

- 결정: FastAPI·React·PostgreSQL 기반으로 재설계한다.
- 이유: 조문 단위 파싱, 법령 위계, 사용자 격리, 테스트, 로컬 모델, 마이그레이션을 세밀하게
  제어하기 어렵기 때문이다.
- 결과: 핵심 로직을 서비스 계층에서 테스트할 수 있고 배포 구성을 코드로 재현할 수 있다.

## ADR-002 — Ollama endpoint를 환경설정으로 추상화

- 결정: Ollama IP를 애플리케이션 코드에 하드코딩하지 않는다.
- 개발: `dev/docker-up-wsl.sh`가 WSL에서 Windows 호스트 주소를 탐지한다.
- 운영: Docker 서비스명 또는 사설 DNS를 사용한다.
- 이유: WSL2 NAT 주소는 재시작 시 달라질 수 있다.

## ADR-003 — readiness와 외부 AI 의존성 상태 분리

- 결정: `/health/live`, `/health/ready`, `/health/dependencies`를 분리한다.
- 이유: Ollama 장애가 인증·DB 조회·계산기까지 모두 사용할 수 없는 상태를 의미하지 않는다.
- Docker backend healthcheck는 DB와 Alembic 준비 상태를 기준으로 한다.

## ADR-004 — Alembic을 DB 스키마의 단일 변경 경로로 사용

- 결정: 기존 SQL 스키마를 legacy baseline으로 채택하고 이후 변경은 Alembic revision으로 작성한다.
- 이유: 빈 DB와 기존 볼륨의 상태 차이, 수동 SQL 적용 순서 문제, 배포 재현성 문제를 해결한다.
- 금지: 신규 기능을 위해 `db/migrations/*.sql`만 추가하고 수동 적용하는 방식.

## ADR-005 — 법령 참조 파싱을 법령 도메인 서비스에 배치

- 결정: 범용 `utils`가 아니라 `app/services/law/reference_parser.py`에 둔다.
- 이유: 조·항·호·목, 가지번호, 원문 항 기호는 대한민국 법령에 종속된 도메인 규칙이다.
- 본문 대조는 `structure_parser.py`, XML 수집은 `parser_service.py`로 책임을 분리한다.

## ADR-006 — `제59조의4`와 `제59조 제4항`을 다른 필드로 저장

- 결정: 조 가지번호는 `article_branch`, 항은 `paragraph`로 구분한다.
- 이유: `제59조의4`의 4는 항이 아니라 제59조에서 파생된 독립 조문 번호다.
- 같은 원칙을 `item`과 `item_branch`에도 적용한다.

## ADR-007 — 조문 전체 벡터와 항 벡터를 함께 사용

- 결정: 조문 전체 임베딩을 유지하면서 긴 조문의 항 단위 보조 임베딩을 추가한다.
- 이유: 조 전체만 사용하면 특정 항의 의미가 희석되고, 항만 사용하면 조 전체 맥락 질문이 약해진다.
- 검색 히트가 항 벡터여도 최종 컨텍스트는 필요한 법적 맥락을 포함해야 한다.

## ADR-008 — 법적 권위와 유사도를 분리

- 결정: 검색 유사도와 별개로 법률 → 시행령 → 시행규칙 → 유권해석 순의 우선순위를 적용한다.
- 이유: 의미적으로 비슷한 하위 자료가 상위 법령보다 먼저 제시되는 것을 방지한다.

## ADR-009 — 세액 계산을 LLM에서 분리

- 결정: LLM은 계산기 선택과 입력 추출을 담당하고 실제 세액은 DB 세율표 기반 함수가 계산한다.
- 이유: 산술 환각을 줄이고 계산 단계와 법적 근거를 재현 가능하게 만든다.

## ADR-010 — scripts는 얇은 CLI 진입점으로 유지

- 결정: 수집·동기화·백필·평가의 인자 처리와 실행만 `scripts/`에 둔다.
- 핵심 로직은 `app/services/`에 둔다.
- 장시간 또는 변경 작업은 dry-run·명시적 옵션·종료 코드로 안전하게 제어한다.

## ADR-011 — 채팅 접근제어와 AI HTML 정화를 렌더링 전에 강제

- 결정: 일반 채팅과 SSE 채팅은 LLM 또는 스트리밍을 시작하기 전에 `conversation_id`가 로그인 사용자 소유인지 DB에서 확인한다.
- 결정: 잘못된 UUID, 없는 대화, 타인 소유 대화는 모두 같은 404를 반환하여 대화 ID 존재 여부를 노출하지 않는다.
- 결정: AI Markdown은 `marked` 변환 후 DOMPurify로 정화한 HTML만 DOM에 삽입한다.
- 결정: Docker 빌드 컨텍스트에서는 `.env`와 `.env.*`를 제외하고 공유 가능한 `.env.example`만 허용한다.
- 이유: 인증 여부만으로는 객체 단위 접근권한을 보장할 수 없으며, 생성형 답변과 검색 문서는 신뢰할 수 없는 입력이므로 저장형 XSS와 이미지 레이어의 비밀정보 잔존을 별도로 차단해야 한다.

## ADR-012 — 생성 LLM은 vLLM, 기존 임베딩은 Ollama로 분리

- 결정: 생성 요청은 OpenAI 호환 vLLM 서버로 전환하고, 기존 2560차원 임베딩과 선택적 리랭킹은 Ollama에 유지한다.
- 이유: 생성 provider를 교체하면서 기존 pgvector 데이터를 전면 재임베딩하지 않고 점진적으로 전환하기 위함이다.
- 개발: `docker-compose.vllm.yml`을 overlay로 적용하며 `LLM_PROVIDER=vllm`과 내부 DNS `http://vllm:8000/v1`을 사용한다.
- 자원 제약: 12GB GPU에서 9B 생성 모델과 4B 임베딩 모델을 번갈아 사용하므로 생성 모델은 NVFP4 체크포인트, 제한된 KV cache와 동시 요청 수로 실행한다.
- 실제 런타임 결정: 10.43GiB는 다운로드 체크포인트 크기이며 실제 가중치 VRAM 사용량으로 간주하지 않는다. `--language-model-only`, `--enforce-eager`, 2,048 토큰, 동시 시퀀스 1개를 사용한다. Qwen3.5 하이브리드 구조에서 품질 저하가 보고된 FP8 KV cache 강제 설정은 제거하고 기본 dtype을 사용한다. CPU offload는 Qwen GDN Triton 커널과 호환되지 않아 사용하지 않는다.
- 복구: 기본 Compose와 `dev/docker-up-wsl.sh`는 Ollama 생성 provider의 fallback으로 유지한다.

## ADR-013 — 검색 모델 조합 확정

- 생성: `Qwen3.5-9B NVFP4`를 vLLM으로 서빙한다.
- 임베딩: 기존 `Qwen3-Embedding-4B`와 2560차원 pgvector 데이터를 유지한다.
- 리랭커: `dragonkue/bge-reranker-v2-m3-ko`를 신규 도입한다.
- 이유: 이미 검증·구축된 임베딩을 보존하면서, 한국어 금융 문서 평가 근거가 있는 경량 Cross-Encoder로 후보 조문의 최종 정렬을 개선한다.
- 검색 순서: BM25·벡터 검색 후보 생성 → 리랭커 → 법령 위계 및 직접 조문 일치 규칙 → 최종 컨텍스트 선정.
- 구현: 임베딩과 리랭커의 provider 선택지는 Ollama와 Infinity로 제한하며 애플리케이션은 역할별 adapter를 통해 호출한다.
- 주의: 현재 PC에서 Infinity 전체 모델 로딩은 완료되지 않았으며 적용 전후 골든셋 회귀 평가도 후속 작업이다.

## ADR-014 — 추론 역할과 연산 장치 분리

- 결정: LLM·임베딩·리랭커의 provider와 endpoint를 독립 설정하고, Infinity 임베딩과
  리랭커를 별도 컨테이너로 실행한다.
- 결정: 임베딩·리랭커는 환경변수와 `dev/set-inference-device-wsl.sh`를 통해 CPU/GPU를
  전환할 수 있게 하되, 12GB GPU에서는 vLLM과 다른 모델의 GPU 동시 상주를 차단한다.
- 이유: 장치 배치를 코드에 고정하지 않으면서 GPU OOM과 서비스 전체 재시작을 방지한다.

## ADR-015 — 소규모 서비스 기본 추론 엔진을 llama.cpp로 전환

- 결정: 생성 LLM과 신규 임베딩은 GGUF Q4_K_M 모델을 독립 llama-server로 서빙한다.
- 생성 모델은 `unsloth/Qwen3.5-9B-GGUF:Q4_K_M`, 임베딩은
  `Qwen/Qwen3-Embedding-4B-GGUF:Q4_K_M`을 사용하고 임베딩 pooling은 `last`로 고정한다.
- 이유: 단일 사용자·소규모 서비스에서는 vLLM의 높은 동시 처리량보다 낮은 상주 메모리,
  NVIDIA·Apple Silicon 간 GGUF 이식성, 단순한 OpenAI 호환 API 운영이 더 중요하다.
- 기존 Ollama 경로는 v1 호환을 위해 보존한다.

## ADR-016 — vLLM·Infinity 실험 구성 제거

- 결정: vLLM·Infinity 전용 Compose, 실행 스크립트, provider 선택지, Docker 이미지와 모델
  캐시를 제거하고 llama.cpp·Ollama 두 경로만 유지한다.
- 이유: 12GB VRAM PC에서 생성·임베딩·리랭커의 동시 상주가 불안정했고, 소규모 운영 목표에는
  GGUF 기반 llama.cpp가 메모리와 플랫폼 호환성 측면에서 더 적합하다.
- 영향: ADR-012~014는 실험 당시의 기록으로만 남으며 현재 운영 결정은 ADR-015~016이 대체한다.

## ADR-017 — TEI·리랭커 구성 제거

- 결정: 미사용 TEI 이미지와 리랭커 모델 캐시 및 애플리케이션 리랭킹 계층을 제거한다.
- 이유: 현재 PC에서 세 모델 동시 상주가 어렵고, 검증되지 않은 리랭커 경로를 유지하면 운영·상태
  진단 복잡도만 증가한다. 검색은 벡터·BM25·RRF와 법령 위계 규칙으로 동작한다.
- 영향: 과거 리랭커 관련 ADR은 실험 기록으로만 남는다.
- 저장 벡터는 엔진·양자화 변경 시 재사용하지 않는다. llama.cpp 결과는 `embedding_v2`에
  백필하고 골든셋 평가를 통과한 뒤 활성 검색을 v2로 전환한다.
