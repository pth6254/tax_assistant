# 세션 인수인계

## 2026-09-08 실제 실행 이미지 교체

- 발표 파일의 assets/chat.png·source.png는 이제 실제 Docker/Ollama 실행 결과다. 합성 캡처를 다시 실행해도 발표 이미지를 덮어쓰지 않도록 capture-ui.cjs는 OS 임시 폴더로 출력한다.
- 실제 재캡처는 capture-live-ui.cjs. localhost 서비스에 자기 임시 계정만 생성·삭제하며 live-capture.json에는 비밀 없이 질문·답변·확인 결과를 저장한다.
- 캡처 중 발견한 후속 품질 검증: 제50조 기본공제 대상 답변의 설명 범위, 3문장 지시 미준수, 저장 원문의 하위 호 누락 가능성. 이번에는 답변/DB/프롬프트를 고치거나 화면에서 숨기지 않았다. 과거 파서 데이터와 최신 공식 원문 비교는 별도 승인 범위에서 진행할 것.
- 시연 계정 2개(최초 캡처 검증 오류 후 재실행) 모두 종료 시 회원 삭제 API HTTP 200으로 정리했다. 기존 사용자 자료는 접근하지 않았다.


## 2026-09-07 슬라이드 설명 방식 개편

- 면접 슬라이드 3~5장을 전체 기능 아키텍처 / 쉬운 문제 해결 / 검증 방식·한계·개선으로 변경했다. 테스트 개수는 본문에서 제거했고 과거 골든셋 지표 정의는 구현 근거에 남겼다.
- 편집 원본 interview.html과 배포용 tax-ai-interview.html 모두 반영. 기존 최신 UI 이미지는 유지한다. 수정은 발표 자료에 한정되며 실제 재평가·전문가 검수는 후속 작업이다.


## 2026-09-07 프런트엔드 리팩토링 인수인계

- ChatArea/useChat, 공통 UI, DocumentsScreen/useDocumentLibrary, Calculator/forms로 역할을 분리했다. 현재 작업은 UI/문서 상태 조회에 한정하며 세율·계산 수식은 변경하지 않았다.
- 재검증: frontend에서 npm test와 npm run build. preview 실행 후 tools.browser.cjs 및 workspace.browser.cjs를 실행한다. PLAYWRIGHT_MODULE로 설치 위치를 지정할 수 있다. API는 합성 응답이며 실제 사용자 자료를 생성·삭제하지 않는다.
- 문서 search_ready는 활성 벡터 컬럼의 non-null 개수 기준이다. 임베딩 모델 의미적 호환성, 인덱스 품질 또는 검색 성공을 인증하지 않는다. 업로드는 기존 동기 요청이며 백그라운드 작업 상태/진행률 복구 기능은 미구현이다.
- 계산 결과의 기준일/실제 사용한 자료 시행일은 서버가 아직 제공하지 않는다. 현재 정보 없음으로 표시한다. 요청별 세율 provenance 및 세목별 적용 범위 검증은 후속 과제다.
- 같은 파일 업로드의 서버 DELETE/INSERT 원자성·동시 업로드 충돌은 별도 개선이 필요하다. 이번에는 사용자 확인과 목록 확인 전 업로드 보호를 추가했다.
- HTML 면접 슬라이드의 이전 UI 캡처 교체 완료(2026-09-07 후속 요청): capture-ui.cjs의 문서/health mock을 갱신하고 2880×1800 이미지 2장을 덮어썼다. standalone 재빌드·5장 전체 시각/자동 검증 완료. 이전 이미지 별도 백업 없음. 합성 데이터·health 시연 상태이며 실제 모델 응답으로 소개하지 않는다.


## 2026-09-07 면접 슬라이드 제작

- 발표 파일: `docs/portfolio/tax-ai-interview.html` (단독 전달 가능). 편집 원본·이미지·빌드/캡처/검증 스크립트 및 사용법은 같은 폴더에 있다.
- 실제 React 화면에 합성 API 데이터를 주입해 캡처했다. 개인정보·실제 세무 답변·실제 법령 본문은 포함하지 않았다. 소스 링크는 저장소 상대 경로이므로 파일 단독 공유 시 링크는 끊기지만 근거 설명 텍스트는 남는다.
- 슬라이드 레이아웃·오프라인 동작·인쇄 5페이지 검증 완료. 발표 전 개인별 담당 범위/기간/기여율은 본인 확인 후 추가할 것. 자료에는 확인되지 않은 수치를 넣지 않았다.
- 후속 문서 정합성: README와 과거 컨텍스트의 BM25·검색/계산 병렬·실패 RAG-only 설명은 현재 코드와 다르다. 이번에는 제품 설명 전체를 변경하지 않고 슬라이드에 실제 코드를 반영했다.
- 현재 코드 품질 전체 재평가나 모델 재기동은 수행하지 않았다. 임시 프런트 preview는 종료했고 검증 캡처/PDF는 OS 임시 폴더에 있다.


## 2026-09-07 계산 실패 정책 반영

- 계산 실패를 0원/기본 공제로 반환하지 않는다. errors.py의 안전한 오류 계약을 API와 도구가 공유하며 실패 답변은 최종 LLM을 우회한다. 변경된 기대값(빈 세율표는 오류, 잘못된 도구 인자는 입력 오류)에 맞춰 테스트를 수정했다.
- 백엔드 372개·프런트 6개와 Docker 프런트 build, 합성 API 브라우저 검증 통과. 기존 DB를 변조하지 않고 mock으로 장애를 주입했다. 이번 변경은 법정 세율·수식 정확성 인증이 아니다.
- 다음 검증: 세목별 실제 적용 범위·시행연도·공제 한도·Decimal 반올림 및 부분적으로 손상된 세율표 검증을 통합 평가기에 포함할 것. 데이터 보정 필요 여부는 별도 감사 후 결정한다.
- 양도소득세의 주식/기타 선택지는 화면에 남아 있으나 실행하면 미지원 안내한다. 별도 계산식 구현 전 부동산 공식을 재사용하지 않는다.
- 실행 시 현재 Ollama 구성은 dev/docker-up-wsl.sh를 사용한다. 직접 docker compose 호출 시 자동 탐지 환경변수 OLLAMA_WINDOWS_IP가 없어 실패할 수 있다.


## 2026-09-05 도구 카드·SSE·대화 복원 완료

- ToolCallCard.jsx와 toolState.js가 도구 진행/결과를 표시한다. 문서 본문은 React 텍스트 노드로만 렌더링한다. 법령 성공은 원문 뷰어, 계산 성공은 프리필 화면으로 연결한다.
- 공통 planner의 on_event callback → chat_service 준비 태스크/큐 → SSE 경로다. 연결 종료 시 준비 태스크를 취소한다. 최종 결과만 저장하고 LLM history에는 role/content만 전달한다.
- backend 352 tests, frontend 5 tests/build, 합성 API 브라우저 smoke, 실제 Ollama 스트리밍 이벤트 확인 완료. 브라우저 검증은 로컬 preview에서 진행했으며 실제 계정·문서 데이터는 수정하지 않았다.
- 브라우저 테스트는 tests/tools.browser.cjs(프런트 디렉터리 기준)이며 Playwright·Edge가 필요하다. 의존성은 제품 런타임에 추가하지 않았다.
- 남은 별도 과제: Docker frontend npm install 출력에서 취약점 2건(moderate 1, high 1)이 보고됐다. 이번 기능 작업에서는 의존성 강제 업그레이드를 하지 않았다. 통합 품질 평가기와 실제 소유 PDF 성공 경로 골든셋도 후속 과제다.

## 2026-09-05 공통 도구 계층 도입

- 선택은 tools/planner.py, 입력 허용 목록은 registry.py, 제한 실행은 executor.py에 있다. calculator/engine.py의 이전 extract_calculation_request/run_calculation_for_query는 제거했으며 테스트는 실제 공통 경로로 이동했다.
- 법령 조회는 law/lookup_service.py가 단일 구현이다. 사용자 PDF는 search_user_documents → 기존 _search_documents의 user_id SQL 필터로 조회한다.
- Docker 전체 테스트 346 passed. 실제 Ollama의 법령·문서·계산기 선택과 법령 조회·계산 실행, 문서 없는 사용자 not_found 확인.
- 후속: 통합 평가기 구축, 다중 도구 연쇄 실행 여부 결정, 실제 소유 PDF 성공 경로 골든셋 추가. 문서 페이지 번호는 현재 반환하지 않는다.
- DB/모델/사용자 대화 데이터 삭제·추가 없음. 기존 테스트는 유지·이관했으며 새 도구 보안·실패 경계 테스트를 추가했다.
- 최종 답변 생성·인용 guard까지 실제 호출 성공(대화 조회·저장만 mock). 인용은 단순 문자열 대신 운영 extract_citations로 정규화해서 비교해야 한다. dependency ready 확인, git diff --check 통과.

## 2026-09-05 app 정리 완료

- 미사용 검색 wrapper와 `calculator/updater.py` 제거, 네 계산기의 누진세율 적용은 `calculator/brackets.py`로 통합. README 구조도도 갱신했다.
- `dev/docker-up-wsl.sh backend` 최신 이미지 전체 pytest 329 passed. 기동 준비 후 live·ready·dependencies HTTP 200 확인. 이번에는 실제 LLM 답변 생성 시험은 반복하지 않았다.
- DB·모델 데이터 변경 없음. 세율 자동 갱신은 운영 기능이 아니었으며 재도입하려면 출력 검증·실제 시행일 검증·승인 후 반영 설계가 선행돼야 한다.
- 추가 필수 작업은 없으며 chat/upload 역할 분리는 선택적 후속 작업이다. 기존 답변 품질 평가 우선순위를 유지한다.

## 2026-09-05 미사용 호환 함수 제거

- `chat_service._build_final_messages`, `calculator.engine._parse_extraction_json`은 운영 코드에서 사용되지 않아 제거했다. 이 함수들을 테스트를 위해 재도입하지 않는다.
- 테스트는 실제 ChatPromptTemplate과 계산기 추출 파이프라인을 대상으로 변경했다. Docker 최신 이미지 전체 pytest 317 passed.
- 추가 작업이나 데이터 보정은 필요하지 않으며 다음 우선순위는 기존 답변 품질 평가다.

## 2026-09-05 LangChain 선택 기능 도입 완료

- 사용자의 1·2·3번 요청을 ChatPromptTemplate, Runnable, PydanticOutputParser 적용으로 진행했다. LangSmith는 후속 연결 대상으로 남겼다.
- `ai_pipeline.py`는 공통 호출 함수를 받아 실행하며 provider SDK를 import하지 않는다. `langchain-core`만 재도입하고 `langchain-ollama`는 제거 상태를 유지한다.
- `ai_output.py`에 분류·인용·계산기 추출 모델을 추가했다. 잘린 JSON·잘못된 타입·누락/알 수 없는 필드는 fallback 처리하며 자동 생성 재시도는 없다.
- 최신 Docker 전체 테스트 317 passed. 실제 HTTP provider를 통한 생성·스트리밍·구조화 인용·계산기 추출 및 dependency ready 확인 완료.
- Windows PowerShell에서 한글 포함 Python 코드를 WSL stdin으로 전달할 때 `$OutputEncoding`을 UTF-8로 설정해야 한다. 기본 인코딩으로 한글이 `?`가 된 스모크는 전달 방식을 고쳐 재검증했다.
- 다음 작업: 골든셋·평가 기준 마련 후 LangSmith 추적·평가 연결. 현재는 run_name·prompt_version·callback 경계를 준비했으며 외부 업로드 설정은 추가하지 않았다.

## 2026-09-05 LLM 연결 코드 정리 완료

- `langchain-core`도 제거하여 최신 Docker 이미지는 LangChain 패키지 없이 실행된다.
- `call_llm`·`call_llm_structured`·`stream_llm`의 생성 길이 인자는 `max_tokens`다. 저장소 내부 호출부는 모두 갱신했으며 별도 외부 스크립트에서 `num_predict=`로 호출했다면 변경해야 한다.
- factory의 설정 인자를 명시하고 `base_url`로 통일했다. 테스트용 HTTP 주입 전역 변수와 설정 캐시 키를 제거했다. 프로세스 설정은 재시작으로 변경한다.
- `dev/docker-up-wsl.sh backend` 재빌드 완료. Docker 전체 pytest 296 passed, 실제 Ollama 일반 생성·스트리밍·구조화 응답 모두 성공, dependency ready 확인.
- 다음 작업은 답변 품질 평가이며 이번 정리는 모델·프롬프트를 바꾸지 않았다.

## 2026-09-05 ChatOllama 제거 및 HTTP 어댑터 검증 완료

- `inference/llm/ollama.py`가 Ollama `/api/chat`을 `httpx`로 직접 호출한다. 서비스 공통 인터페이스, 모델·컨텍스트·상주·thinking 설정은 유지했다.
- 초기 교체에서 `langchain-ollama`를 제거했고 후속 정리에서 미사용 `langchain-core`도 제거했다.
- WSL 가상환경 활성화 후 `dev/docker-up-wsl.sh backend`로 최신 backend 이미지를 빌드·기동했다. 전체 pytest 294 passed, 실제 일반 생성·스트리밍·JSON 응답 및 dependency ready 확인 완료.
- 기존 JSON 스모크 세션은 중단되어 결과를 회수하지 못했다. 재개 후 구조화 호출을 다시 실행해 약 6.4초에 정상 응답을 확인했다.
- 다음 작업: 답변 품질 골든셋과 평가기. 이번 변경으로 세무 답변 정확도가 개선됐다고 판단하지 않는다.

## 2026-08-23 Ollama 동시 GPU 적재

- `qwen3.5:9b` 5.5GB와 `qwen3-embedding:4b` 4.4GB를 컨텍스트 4,096에서 모두
  100% GPU로 적재했고 3회 교차 호출을 통과했다. 잔여 VRAM은 약 463MiB다.
- 운영 chat 기본 `OLLAMA_NUM_CTX`는 4,096로 변경했다. 병렬도 증가나 Windows GPU 사용량
  급증 시 OOM 위험이 있으므로 `OLLAMA_NUM_PARALLEL=1`을 유지한다.

## 2026-08-23 serving 실험 환경 최종 감사

- WSL/Windows를 점검해 vLLM·Infinity·TEI·llama.cpp·리랭커 실행 자원과 어제 받은 모델을
  정리했다. WSL에는 관련 컨테이너·이미지·모델 볼륨·Python 패키지가 남아 있지 않다.
- 현재 운영 자원인 Windows Ollama, `qwen3.5:9b`, `qwen3-embedding:4b`와 프로젝트 DB는 보존했다.
- 재도입용 llama.cpp 코드와 Compose 파일만 저장소에 남아 있다.

## 2026-08-23 llama.cpp 실행 자원 삭제

- llama.cpp 도입 코드는 유지하고 WSL Docker의 컨테이너 2개, 이미지 2개와
  `tax_assistant_llama_cache`만 삭제했다.
- 현재 런타임은 Ollama LLM·Ollama v1 임베딩이며, llama.cpp를 다시 사용할 때는
  `dev/docker-up-llamacpp-wsl.sh`가 필요한 이미지와 모델을 재다운로드한다.

## 2026-08-23 vLLM·Infinity 제거

- vLLM·Infinity 전용 파일, 컨테이너, 이미지와 Hugging Face/Infinity 모델 캐시 볼륨을 삭제했다.
- 이후 표준 실행은 `dev/docker-up-llamacpp-wsl.sh`만 사용한다.
- PostgreSQL 데이터와 `tax_assistant_llama_cache`는 보존했다.
- 과거 vLLM·Infinity 절은 실험 이력이며 재실행 지침이 아니다.
- TEI Docker 이미지와 `tax_assistant_reranker_cache`, 리랭커 코드·설정·health/UI 표시도 제거했다.
- 후속 llama.cpp CPU A/B에서 BGE-Reranker-v2-M3 Q4는 MRR 0.9276→0.9088로 하락하고
  평균 1.746초가 추가되어 채택하지 않았다. 현재 검색 정렬을 유지한다.

## 2026-08-23 llama.cpp 소규모 서비스 전환

- 신규 overlay `docker-compose.llamacpp.yml`과 실행 스크립트
  `dev/docker-up-llamacpp-wsl.sh`를 추가했다.
- 생성은 Qwen3.5-9B GGUF Q4_K_M CUDA, embedding_v2는 Qwen3 Embedding 4B GGUF
  Q4_K_M CPU/last pooling 구성이다. 활성 임베딩은 데이터 안전을 위해 아직 v1이다.
- 다음 필수 작업은 llama.cpp 임베딩 비교·백필·골든셋 평가와
  `dragonkue/bge-reranker-v2-m3-ko`의 자체 GGUF Q4_K_M 변환 및 평가다.
- 최신 backend 이미지 전체 테스트는 `287 passed`, llama.cpp Compose config는 정상이다.
  실제 기동에서 llama.cpp CPU/CUDA 이미지는 정상 pull됐으나 컨테이너가 Hugging Face의
  IPv6 주소만 해석하고 연결하지 못해 GGUF 다운로드가 실패했다. WSL 호스트 HTTPS는
  정상이다. 다음 작업은 호스트에 GGUF를 선다운로드하고 read-only volume으로 마운트하는 것이다.
- Mac에서는 Docker가 Metal GPU를 전달하지 않으므로 llama-server를 호스트에서 실행하고
  backend 컨테이너가 `host.docker.internal`로 접속하는 별도 프로파일이 필요하다.

## 2026-08-23 vLLM NVFP4 재검증

- 10.43GiB는 체크포인트 다운로드 크기이며 실제 가중치 VRAM 사용량으로 해석하지 않는다.
- 모델 제작자의 Qwen3.5 하이브리드 구조 주의사항에 따라 Compose의 FP8 KV cache 강제
  설정을 제거했다. 단독 계측에서 compressed-tensors 양자화, 모델 로딩 9.71GiB,
  weights+non-torch 10.11GiB, activation 0.27GiB, KV cache 0.37GiB를 확인했다.
- `gpu-memory-utilization=0.96`은 Windows가 사용하는 VRAM 때문에 시작 전 검사에서 실패했다.
  `0.90`에서는 11,205/12,227MiB를 사용하며 컨테이너 health가 통과했다.

## 2026-08-23 Ollama 임베딩 상주 옵션 제거

- Ollama 임베딩 adapter는 `/api/embed` 요청에 `keep_alive`를 보내지 않는다.
- `OLLAMA_KEEP_ALIVE_SEC=-1`은 Ollama 채팅 LLM에만 적용된다. 이미 메모리에 올라간
  임베딩 모델은 다음 정상 임베딩 요청부터 Ollama 기본 유휴 만료 정책을 적용받는다.

## 2026-08-22 provider 중립화 및 Infinity 검증

- 생성 LLM provider는 `ollama`/`vllm`, 임베딩과 리랭커 provider는 각각
  `ollama`/`infinity`만 허용한다.
- 최신 백엔드 Docker 이미지 전체 테스트 결과는 `284 passed`이다.
- Infinity 공식 CPU 이미지의 Transformers가 Qwen3를 인식하지 못해 커스텀 이미지에
  Transformers 4.56.2와 Sentence-Transformers 5.1.1을 고정했다.
- Qwen 공식 모델은 last-token pooling을 요구한다. smoke test에서 부분 snapshot이
  mean pooling으로 대체되는 현상을 확인했다. 활성 버전은 v1 Ollama로 유지하며
  `embedding_v2` 백필은 실행하지 않았다.
- 공식 Ollama는 범용 `/api/rerank`를 제공하지 않는다. Ollama reranker adapter는
  호환 API 게이트웨이용이며, 기본 Ollama에서는 Infinity를 사용하거나 비활성화한다.
- Infinity 임베딩과 리랭커를 별도 컨테이너로 분리했다. 각 역할은
  `INFINITY_*_DEVICE=cpu|cuda`로 독립 배치하며 `dev/set-inference-device-wsl.sh`로
  해당 컨테이너만 재생성할 수 있다. 12GB GPU에서는 vLLM 실행 중 GPU 전환을 차단한다.
- 이전의 컨테이너 시작 시각 초기화는 Docker Desktop 크래시가 아니었다. Docker는
  Ubuntu WSL 내부 systemd 서비스이며, Codex의 일회성 `wsl.exe -e` 명령이 끝날 때
  배포판도 Stopped 상태가 되어 다음 명령에서 다시 시작된 것이다.
- 실제 vLLM 차단 원인은 Windows Ollama의 `qwen3-embedding:4b Q4_K_M`이
  `keep_alive=-1`로 GPU에 상주하면서 VRAM 약 4.37GB를 점유한 것이다. vLLM의 기존 0.96 설정은
  시작 시 11.46GiB free VRAM을 요구하지만 실제 free는 10.77GiB였다. Ollama 임베딩을
  CPU 전용 서버로 옮기거나 언로드하기 전에는 12GB GPU에서 vLLM과 동시 실행할 수 없다.
- WSL RAM은 24GB(실제 23.47GiB), swap 16GB로 정상 적용됐다. 안정화를 위해 vLLM과
  두 Infinity 모델은 현재 중지했다.

이 파일은 미완료 작업 또는 다음 세션에 반드시 전달해야 하는 내용이 있을 때 갱신한다.
완료된 작업의 장기 상태는 `CURRENT_STATUS.md`, 영구 설계 이유는 `DECISIONS.md`에 반영한다.

## 현재 인수인계

- 활성 작업: vLLM 생성 서버와 한국어 리랭커 구현 및 실제 기동 완료. 새 작업 전 `git status --short`로 기존 변경을 확인할 것.
- 최근 영역: 생성 LLM vLLM 전환, Ollama 임베딩 유지, Docker GPU 실행 스크립트.
- 최근 검증: provider·health·검색 관련 최신 backend 선택 테스트 `29 passed`. 전체 테스트는 Infinity 전환 완료 후 재실행 필요.
- NVIDIA Container Toolkit 1.20.0 설치, Docker `nvidia` runtime 등록 및 컨테이너 `nvidia-smi` 검증 완료. `dev/docker-up-vllm-wsl.sh`로 전체 스택 기동 및 dependency health를 확인했다.
- 모델 조합: 생성 `ig1/Qwen3.5-9B-NVFP4`, 임베딩 `Qwen3-Embedding-4B`, 리랭커 `dragonkue/bge-reranker-v2-m3-ko`. 임베딩·리랭커는 Infinity CPU 다중 모델 overlay로 통합 중이다.
- 12GB GPU 제약: NVFP4 모델은 텍스트 전용·eager·기본 KV dtype·2,048 토큰·동시 1요청·GPU utilization 0.90으로 검증했다. CPU offload는 Qwen GDN Triton 커널의 CPU pointer 오류로 사용할 수 없다.
- CPU 추론 제약: WSL 할당 RAM은 15GiB이며 Infinity 컨테이너는 12GiB로 제한했다. Qwen3 Embedding 4B 백필과 reranker 동시 실행의 지연·메모리를 실제 측정해야 한다.
- 공식 Infinity `latest-cpu` smoke test는 내장 Transformers가 `qwen3`를 인식하지 못해 실패했다. `docker/infinity.Dockerfile`에서 Qwen3 지원 버전을 고정했으며 커스텀 이미지 재검증이 필요하다.
- 프런트엔드는 `/api/health/dependencies`를 30초마다 조회해 역할별 실제 provider와 모델을 표시한다.
- 데이터 주의: 기존 DB는 과거 수집기로 인해 호·목이 누락됐을 수 있으며 전체 재수집은 아직
  자동 실행하지 않는다.
- 추천 다음 작업: `target.text`를 직접 조문 RAG 컨텍스트에 우선 반영.

## 작업 중 갱신 형식

```markdown
### YYYY-MM-DD — 작업 제목

- 사용자 목표:
- 완료한 변경:
- 변경 파일:
- 실행한 검증과 결과:
- 남은 작업:
- 막힌 이유 또는 필요한 사용자 결정:
- 데이터·마이그레이션·배포 주의사항:
```

## 갱신 원칙

- “테스트 완료” 대신 명령과 결과 수를 쓴다.
- 실행하지 않은 작업을 완료로 표시하지 않는다.
- 코드 경로와 함수명을 구체적으로 적는다.
- 비밀값, 토큰, 실제 `.env` 내용을 기록하지 않는다.
- 작업이 완전히 끝나면 임시 메모를 제거하고 `CURRENT_STATUS.md`에 최종 상태를 반영한다.
