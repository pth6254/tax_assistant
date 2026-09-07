# 현재 구현 상태

## 2026-09-08 포트폴리오 실제 실행 캡처

- WSL venv + dev/docker-up-wsl.sh backend frontend로 최신 이미지 실행. 실제 임시 계정으로 소득세법 제50조 제1항 기본공제 설명 질문 → Ollama 답변 → 대화 DB 저장 → 원문 패널 조회를 확인했다.
- 실제 화면 2장을 2880×1800으로 캡처해 기존 합성 이미지를 대체했다. 2장 설명·확대창·구현 근거를 실제 실행 설명으로 변경하고 standalone HTML 및 전체 슬라이드 검증을 완료했다.
- capture-live-ui.cjs와 live-capture.json에 재현 방법/질문/실제 답변을 기록한다. 비밀번호·쿠키는 저장하지 않는다. 임시 계정과 대화는 API로 정리 완료. 기존 사용자 자료와 법령 데이터는 변경하지 않았다.
- 최초 캡처 시 브라우저 SSE 응답 본문 재조회가 실패하여 재실행했다. 두 실행 모두 임시 계정 정리 HTTP 200. 최종 검증은 UI 생성 종료·실제 저장된 assistant 메시지·원문 API HTTP 200을 확인한다.
- 품질 한계: 실제 답변이 요청한 3문장 형식을 따르지 않고 기본공제 대상 설명도 제한적이다. 현재 저장 원문에 하위 호가 빠져 있는지 확인이 필요하다. 실행 성공을 세무 답변 정확성 인증으로 소개하지 않는다.


## 2026-09-07 면접 슬라이드 3~5장 개편

- 3장은 전체 기능 아키텍처(화면/API/기능 서비스/DB·로컬 AI·외부 데이터), 4장은 문제·해결 방법·사용자 효과의 쉬운 설명으로 변경했다.
- 5장은 테스트 개수와 큰 지표 대신 검증 방식·현재 한계·개선 작업을 검색/계산/권한·UI별로 연결했다. 과거 정량 결과는 구현 근거 창에 보존하며 신규 평가 실행으로 주장하지 않는다.
- 1~2장 및 최신 UI 캡처는 유지. 이미지 내장 HTML 재생성 및 5장 시각·오프라인·인쇄·조작 검증 완료. 제품 코드·DB 변경 없음.


## 2026-09-07 포트폴리오 UI 캡처 교체

- 리팩토링된 현재 React 빌드에서 합성 API 데이터로 assets/chat.png·source.png를 2880×1800으로 재캡처해 이전 이미지를 덮어썼다. 문서 목록·AI health 시연 응답도 현재 UI 계약에 맞췄다.
- tax-ai-interview.html을 재생성하여 내장 이미지도 교체했다. 5장 전체 시각 검토, 오버플로·이미지 전환·확대·키보드·오프라인·인쇄 검증을 통과했다. 제품 코드·DB·모델은 변경하지 않았다.


## 2026-09-07 프런트엔드 기능·디자인 리팩토링

- 밝은 문서형 채팅, 네이비/블루 공통 토큰·outline 아이콘, 반응형 접이식 내비게이션, 계산기 입력/결과 분리, 인증 화면을 적용했다.
- 대화 조회 실패/재시도, AbortController 기반 생성 중지, 대화 전환 시 요청 취소·늦은 응답 무시, 스크롤 추적, IME 전송 보호를 추가했다. 중지된 답변은 미완성/미저장 가능성을 명시한다.
- 인용은 DOMPurify 정화 후 텍스트 노드에 키보드 버튼으로 연결한다. 답변의 외부 이미지/폼 등은 차단한다. 원문 패널은 서버 target을 강조하며 미확인 항·호·목은 별도 안내한다.
- 내 문서 화면은 기존 사용자별 목록/업로드/삭제 API를 사용한다. 활성 embedding/v2의 전체 청크 벡터 저장 여부를 search_ready로 제공하며 검색 품질 보증과 구별한다. 같은 이름 교체·삭제는 확인을 받는다.
- 계산기 만원 입력/원 출력, 원 단위 프리필 보존, 성공 결과의 입력 조건 표시, 실패 결과 제거를 유지했다. 미지원 자산 선택과 비과세 자동 판정으로 오해할 수 있는 안내를 정리했다. 기준일 API 정보가 없으므로 임의 연도를 표시하지 않는다.
- 검증: 프런트 build 및 단위 테스트 8개, Edge 합성 API 브라우저 스위트 2개, 최신 Docker 백엔드 374개 통과(기존 경고 26개). 브라우저 검증은 실제 LLM 품질·실제 PDF 임베딩 성공 검증이 아니다.
- 실제 현재 Ollama 생성/임베딩 구성을 보존하고 WSL venv 활성화 후 dev/docker-up-wsl.sh로 재빌드했다. 기존 DB·모델 파일 삭제/백필 없음.


## 2026-09-07 면접용 HTML 포트폴리오

- `docs/portfolio/tax-ai-interview.html`: 이미지 내장·오프라인 실행 5장 슬라이드. 원본은 `interview.html`, 재생성은 `build-standalone.cjs`.
- 소개·실제 UI(합성 API 캡처)·현재 코드 구조·핵심 판단·평가와 한계 구성. 방향키/전체화면/확대/구현 근거/전체 5장 인쇄 지원.
- 2026-07-19 골든셋 38문항의 과거 Hit@5 100%, MRR 0.9276, 기대 조문 포함률 84.21%와 2026-09-07 기록상 회귀 테스트 372/6을 구분했다. 현재 코드 재평가·전문가 검수 완료로 주장하지 않는다.
- 현재 검색 코드에 BM25 실행 경로가 없어 슬라이드에서는 제외했다. README의 오래된 BM25·병렬 계산/RAG-only 실패 fallback·llama.cpp 기본 구조 표기는 후속 문서 정합성 작업 대상이다.
- 프런트 build, Edge 5장 렌더·시각 검토, 오버플로 없음, 키보드/확대/근거/오프라인/인쇄 5페이지 검증. 이번 작업에서 제품 코드·DB·모델 서버는 변경하지 않았다.


## 2026-09-07 계산 실패 원인 분리

- calculator/errors.py에서 데이터 누락·DB 연결·시간 초과·미지원 조건·내부 오류를 분류한다. API는 안전한 detail(code/message/retryable), 도구 이벤트는 error_code/retryable을 전달한다. 입력 누락과 잘못된 타입·음수도 분리한다.
- 세율 조회 실패의 0원 처리와 DB 공제·세율 기본값 fallback 제거. 정상 0원·부가세 음수 환급은 유지한다. 납부지연 일일 세율 등 명시적 업무 상수는 변경하지 않았다.
- 계산 실패는 RAG/웹 검색과 최종 생성 LLM을 우회해 서버 고정 안내를 저장·반환한다. 실패 시 calculator 메타데이터·calc 성공 이벤트가 없다. 도구 선택 실패도 결과를 추측하지 않고 재질문한다.
- 계산기 입력 변경·재제출·탭 전환 시 이전 결과를 제거하고 늦은 응답을 무시한다. 오류는 기존 화면 및 펼쳐진 도구 카드로 표시하며 일시 장애는 재계산을 안내한다. 자동 재시도 없음.
- 주식·기타 자산, 알 수 없는 증여 관계·가산세 종류·간이 업종은 기본 공식으로 대체하지 않고 미지원 처리한다.
- WSL venv + dev/docker-up-wsl.sh로 Docker backend/frontend 재빌드. backend 372 passed(기존 경고 26), frontend 6 tests/build 통과. 합성 API Edge 브라우저에서 정상 0원·입력 누락·이전 결과 제거·데이터 누락 실패 확인. DB 삭제·세율 보정·모델 변경 없음.


## 2026-09-05 도구 호출 프런트엔드 연결

- 서버 실제 선택·실행 단계의 tool 이벤트를 SSE로 전달하고 일반 API에도 tools 배열을 반환한다. 도구 조회 원문/발췌문·계산기 조건 변경 카드, 법령 뷰어 연결을 추가했다.
- 최종 도구 결과는 기존 chat_logs.message JSON에 저장하며 대화 재조회 시 복원한다. DB 스키마 변경은 없으며 LLM 대화 이력에서는 UI 메타데이터를 제외한다.
- SSE 완료 신호는 저장 이후 전송한다. 프런트는 대화 전환 시 이전 fetch를 취소하고 늦게 도착한 응답을 차단한다. 비정상 EOF는 성공이 아닌 연결 중단으로 표시한다.
- WSL venv 활성화 후 backend/frontend Docker 재빌드 완료. 최신 backend pytest 352 passed(기존 계열 경고 26개), 프런트 npm test 5개·npm run build 통과.
- Edge headless + 합성 API로 카드 복원·법령 뷰어·문서 HTML 이스케이프·SSE not_found·계산기 프리필 확인. 실제 Ollama 스트리밍 selecting→running→ok 및 답변 생성 확인(대화 조회/저장만 mock).

## 2026-09-05 법령·사용자 문서·계산기 공통 도구 호출

- tools/planner.py·registry.py·executor.py 및 법령·문서 어댑터 추가. JSON 선택 기반 provider 중립 도구 호출이며 native tool_calls는 아니다.
- calculator/engine.py에서 LLM 선택·추출을 제거하고 계산 실행·포맷을 유지했다. 미사용 CalculationExtraction 스키마도 제거했다.
- 검색 서비스 안의 법령 조회를 law/lookup_service.py로 추출, 라우터와 도구가 공유한다. PDF 검색은 기존 사용자 격리 SQL을 공유하는 공개 진입점을 추가했다.
- 일반/SSE 채팅에 연결했으며 명시적 원문·문서 조회는 중복 RAG·웹 호출을 생략한다. 계산기 프리필 메타데이터는 유지한다.
- WSL venv 활성화 후 dev/docker-up-wsl.sh backend 재빌드, 최신 Docker 전체 pytest 346 passed(기존 경고 24개).
- 실제 Ollama 선택 + DB 법령 원문 조회 성공, 임시 사용자 문서 검색 not_found, 소득세 계산 실행 성공. 사용자 문서 내용 및 DB 데이터를 수정하지 않았다.
- 한 질문당 도구 하나만 지원한다. 문서 성공 반환·권한 주입·오류·취소·본문 생략은 자동 테스트로 검증했으며 실제 사용자 PDF 내용 검수는 하지 않았다.
- 실제 최종 답변까지 호출해 운영 인용 파서 기준 소득세법 제55조 인용을 확인했다. 최초 단순 문자열 검사는 '제 55 조' 공백 표기를 놓쳐 실패했으므로 정규화 비교로 재검증했다. 대화 조회·저장만 mock하여 사용자 대화는 생성하지 않았다. dependency health HTTP 200 ready, git diff --check 통과.

## 2026-09-05 app 미사용 코드·계산기 중복 정리

- 저장소 내부 호출이 없는 `search.hybrid_search_service.fetch_hybrid_context`와 미사용 `re` import를 제거했다.
- 운영에 연결되지 않은 `calculator/updater.py`를 제거했다. 실제 DB 세율표 조회·계산 경로는 유지하며 데이터는 삭제하지 않았다.
- 네 계산기의 동일한 누진세율 함수를 `calculator/brackets.py`로 통합했다. 기존 구간 경계(`>`), float 변환·정수 절사·음수 세액 제한을 그대로 유지한다.
- 합성 구간 회귀 테스트 12개 추가. WSL 가상환경 활성화 후 `dev/docker-up-wsl.sh backend`로 재빌드하고 Docker 전체 pytest **329 passed**(기존 경고 24개)를 확인했다.
- 기동 직후 health 요청은 일시적으로 연결이 거절됐으나 준비 완료 후 live·ready·dependencies 모두 HTTP 200, DB·Ollama 생성·임베딩 정상. 최신 이미지에서도 updater 파일이 없음을 확인했다.
- 큰 chat/upload 서비스의 역할 분리는 이번 범위에서 제외했다. 실제 모델 답변 품질 평가는 별도 후속 작업이다.

## 2026-09-05 LangChain 전환 후 미사용 코드 정리

- 운영 호출이 없고 이전 테스트에서만 사용하던 `_build_final_messages`와 `_parse_extraction_json` 및 관련 import를 제거했다.
- 메시지 구성 테스트는 실제 최종 답변 템플릿을, JSON 처리 테스트는 실제 `extract_calculation_request` Runnable 경로를 검증하도록 변경했다.
- 기존 회귀 케이스를 유지했으며 Docker 재빌드 후 전체 테스트 317 passed. 모델 호출·검색·인용 guard 동작은 변경하지 않았다.

## 2026-09-05 LangChain 프롬프트·Runnable·출력 검증 적용

- `langchain-core==1.4.9`를 실제 사용 목적으로 재도입했다. `ChatOllama` 없이 기존 HTTP provider를 유지한다.
- 최종 답변·세목 분류·계산기 입력 추출·인용 추출에 ChatPromptTemplate을 적용하고 Runnable로 프롬프트→메시지→생성→검증을 연결했다. 스트리밍은 RunnableGenerator로 즉시 전달한다.
- PydanticOutputParser로 응답 필드와 타입을 검증한다. 불완전 JSON은 자동 복구하지 않으며 계산기별 입력도 실행 전에 엄격 검증한다. 오류 시 기존 fallback을 사용한다.
- 단계 이름·prompt_version 메타데이터·로컬 callback을 지원한다. LangSmith SDK는 간접 의존성이지만 원격 추적·평가 연결은 후속 작업이다.
- WSL 관련 테스트 61 passed, 최신 Docker 전체 테스트 317 passed. 실제 Ollama 생성·스트리밍·인용 JSON 추출·계산기 입력 추출 및 dependency ready 확인 완료.
- LangChain의 역할은 처리 구성과 형식 검증이며 세무 답변의 사실 정확도 검수는 별도 골든셋 작업으로 남는다.

## 2026-09-05 LLM 연결 코드 후속 정리

- 미사용 `langchain-core`를 requirements에서 제거했다. 최신 backend 이미지에 `langchain_core`·`langchain_ollama`가 모두 없음을 확인했다.
- 공통 함수의 `num_predict`를 `max_tokens`로 바꾸고 채팅·계산기·업로드 호출부를 함께 갱신했다. Ollama HTTP payload에서만 `num_predict`를 사용한다.
- factory의 임의 `**settings`를 명시적인 타입·키워드 인자로 변경하고 endpoint를 `base_url`로 통일했다.
- 운영 facade의 테스트 전용 `_http_client`와 불완전한 `_provider_key`를 제거했다. provider는 프로세스 단위 재사용·종료하며 환경설정 변경 시 재시작한다.
- WSL 가상환경 관련 테스트 15 passed, Docker 재빌드 후 전체 테스트 296 passed. 실제 일반 생성·스트리밍·구조화 응답 및 dependency ready 확인 완료.

## 2026-09-05 Ollama 생성 HTTP 어댑터

- Ollama 생성 경로에서 `ChatOllama`를 제거하고 `httpx` 기반 `/api/chat` 어댑터를 적용했다.
- 서비스의 공통 `call_llm`·`call_llm_structured`·`stream_llm` 인터페이스와 기존 모델 설정은 유지한다.
- 초기 교체에서 `langchain-ollama`를 제거했고 후속 정리에서 미사용 `langchain-core`도 제거했다.
- JSON Schema, NDJSON 스트리밍, thinking 분리, HTTP 오류·불완전 스트림, timeout과 연결 종료를 처리한다.
- WSL 가상환경 관련 테스트: 13 passed. `dev/docker-up-wsl.sh backend`로 재빌드한 Docker 이미지 전체 테스트: 294 passed.
- 새 이미지에 `langchain_ollama`가 없는 상태에서 실제 Ollama 일반 생성·스트리밍·JSON 구조화 응답을 확인했다. 구조화 응답은 세션 재개 후 약 6.4초에 `{"ok": true}`를 반환했다.
- dependency health는 DB·Ollama LLM·Ollama 임베딩 모두 정상이며, 이번 검증은 통신 경로 스모크 테스트다. 세무 답변 정확도 평가는 별도 후속 작업이다.

## 2026-08-23 Ollama 두 모델 GPU 동시 적재 실험

- RTX 5070 Ti Laptop 12,227MiB에서 `qwen3.5:9b`와 `qwen3-embedding:4b`를
  컨텍스트 4,096·각 `keep_alive=-1`로 동시에 적재했다.
- `ollama ps` 기준 생성 모델 5.5GB·임베딩 모델 4.4GB가 모두 100% GPU로 유지됐고,
  `nvidia-smi` 총 사용량은 11,482MiB, 가용량은 463MiB였다.
- 임베딩과 짧은 생성을 3회 교차 호출해 모델 이탈이나 OOM이 없음을 확인했다.
- VRAM 여유가 작으므로 chat 컨텍스트 기본값을 6,144에서 4,096로 낮췄고 병렬 요청은
  1개를 유지해야 한다. 임베딩 영구 상주 옵션은 코드에 다시 추가하지 않았다.

## 2026-08-23 serving 실험 자원 최종 정리

- WSL Docker에서 vLLM·Infinity·TEI·llama.cpp·리랭커 관련 컨테이너, 이미지와 모델
  볼륨이 남아 있지 않음을 다시 확인했다.
- 어제 생성된 빈 `vllm_huggingface-cache` 볼륨과 Infinity 전용 BuildKit cache 약 890MB,
  삭제된 provider의 Python bytecode를 추가로 제거했다.
- WSL system Python과 `venv-wsl`에는 해당 serving 패키지가 설치되어 있지 않다.
- Windows에는 별도 serving 프로그램이나 어제 다운로드한 대형 모델 파일이 없었다.
  현재 서비스에 필요한 Ollama와 `qwen3.5:9b`·`qwen3-embedding:4b`는 보존했다.
- 다른 시기에 받은 Windows Hugging Face 캐시와 기존 Ollama 모델은 이번 정리 범위에서 제외했다.

## 2026-08-23 llama.cpp 로컬 실행 자원 정리

- 향후 재도입을 위해 `docker-compose.llamacpp.yml`, provider adapter와
  `dev/docker-up-llamacpp-wsl.sh` 코드는 보존했다.
- 현재 PC의 WSL Docker에서는 `tax_llama_chat`·`tax_llama_embedding` 컨테이너,
  llama.cpp CPU·CUDA 이미지와 `tax_assistant_llama_cache` 모델 볼륨을 삭제했다.
- 현재 실제 서비스 구성은 Windows Ollama의 생성 LLM·v1 임베딩이며 리랭커는 없다.
- llama.cpp 재도입 시 표준 실행 스크립트가 이미지와 GGUF 모델을 다시 다운로드한다.

## 2026-08-23 vLLM·Infinity 구성 제거

- 이 PC의 12GB VRAM과 제한된 WSL 메모리에서 다중 모델 상주가 어렵다는 실측 결과에 따라
  vLLM·Infinity 실행 overlay, 실행 스크립트, 전용 provider 코드를 제거했다.
- 전용 Docker 컨테이너 4개와 이미지 3개, 모델 캐시 볼륨
  `tax_assistant_huggingface_cache`·`tax_assistant_infinity_cache`를 삭제했다.
- 현재 실행 경로는 `dev/docker-up-llamacpp-wsl.sh`이며 기존 Ollama v1 임베딩과
  llama.cpp 생성·v2 임베딩만 지원한다.
- TEI 이미지와 리랭커 모델 캐시, 리랭커 애플리케이션 코드·설정·health/UI 항목도 제거했다.
- 아래 vLLM·Infinity 항목은 과거 실험 기록이며 현재 실행 가능한 구성은 아니다.

## 2026-08-23 llama.cpp CPU 리랭커 A/B 평가

- `BGE-Reranker-v2-M3-Q4_K_M.gguf`를 llama.cpp `--reranking` CPU 서버로 임시 실행해
  정답이 확정된 세무 골든셋 38문항을 동일 후보 5개 기준으로 비교했다.
- 리랭커 없음: Hit@5 100%, MRR 0.9276.
- 리랭커 적용: Hit@5 100%, MRR 0.9088, 추가 지연 평균 1.746초·p95 2.257초.
- 순위가 개선된 문항은 4개, 악화된 문항은 5개였고 일부 정답은 1위에서 5위로 하락했다.
  현재 모델은 운영에 도입하지 않으며 기존 RRF·법령 위계 정렬을 유지한다.
- 실험용 컨테이너와 GGUF 파일은 평가 후 삭제했다.

## 2026-08-23 llama.cpp 전환 시작

- LLM provider에 `llamacpp`, 임베딩 provider에 OpenAI 호환 `llamacpp` adapter를 추가했다.
- `docker-compose.llamacpp.yml`은 Qwen3.5-9B Q4_K_M 생성 서버를 CUDA에,
  Qwen3 Embedding 4B Q4_K_M 서버를 CPU에 배치하며 임베딩 pooling을 `last`로 고정한다.
- `dev/docker-up-llamacpp-wsl.sh`를 WSL/NVIDIA 기본 실행 진입점으로 추가했다.
- 생성 경로는 llama.cpp로 전환할 수 있지만, 검색은 기존 벡터 보호를 위해 아직 v1이다.
  동일 문장 호환성 비교·`embedding_v2` 백필·골든셋 평가 후 v2로 전환해야 한다.
- 선택한 한국어 `dragonkue/bge-reranker-v2-m3-ko`의 검증된 GGUF가 없어 리랭커는
  아직 llama.cpp로 전환하지 않았다. 원본을 직접 GGUF Q4_K_M로 변환하고 품질을 검증해야 한다.
- 최신 backend 이미지 전체 회귀 테스트는 `287 passed`다. llama.cpp Compose 구문 검증도
  통과했다. 실제 기동에서는 이미지 다운로드와 CUDA 인식까지 성공했으나 컨테이너 DNS가
  Hugging Face의 IPv6 주소만 반환하고 IPv6 경로가 없어 GGUF 자동 다운로드가 실패했다.
  WSL 호스트의 Hugging Face HTTPS 연결은 정상이며 호스트 선다운로드·파일 마운트 방식으로
  변경해야 한다.

## 2026-08-23 vLLM 메모리 계측 정정

- `ig1/Qwen3.5-9B-NVFP4`의 10.43GiB는 다운로드 체크포인트 크기이며 실제
  가중치 VRAM 사용량으로 확정된 값이 아니다.
- Qwen3.5 하이브리드 구조에서 출력 품질 저하 가능성이 있는 `--kv-cache-dtype fp8`
  강제 설정을 제거하고 `kv_cache_dtype=auto`로 기동했다.
- vLLM 0.27.1 단독 실측에서 `quantization=compressed-tensors`를 확인했다. 모델 로딩은
  9.71GiB, 가중치와 non-torch 합계는 10.11GiB, peak activation은 0.27GiB,
  KV cache는 0.37GiB(6,436토큰), 전체 GPU 사용량은 11,205/12,227MiB였다.
- Windows 그래픽 사용량 때문에 `gpu-memory-utilization=0.96`은 로딩 전 검사에서 실패했다.
  검증된 기본값을 `0.90`으로 낮췄으며 2,048토큰·동시 요청 1개 설정에서 health가 통과했다.

## 2026-08-23 Ollama 임베딩 상주 해제

- Ollama 임베딩 요청에서 `keep_alive=-1` 전달을 제거했다. 임베딩 모델은 Ollama의
  기본 유휴 만료 정책에 따라 자동 언로드되며, `OLLAMA_KEEP_ALIVE_SEC`는 채팅 LLM에만 적용된다.

## 2026-08-22 provider 전환 상태

- LLM은 Ollama/vLLM, embedding은 Ollama/Infinity, reranker는 Ollama/Infinity로
  역할별 provider 허용 범위를 제한했다.
- 최신 백엔드 Docker 이미지 전체 테스트: `284 passed`.
- Infinity Qwen3 Embedding 4B + BGE reranker 동시 로딩은 현재 15 GiB WSL 메모리에서
  완료되지 않았다. 활성 검색은 v1 Ollama를 유지하고 `embedding_v2` 백필은 보류한다.
- Infinity를 임베딩·리랭커 컨테이너로 분리하고 역할별 `cpu`/`cuda` 장치 설정을
  독립화했다. `dev/set-inference-device-wsl.sh`는 12GB GPU에서 vLLM과 Infinity GPU
  모델을 동시에 올리는 전환을 차단한다.
- WSL RAM은 24GB로 확장됐다. 이전 반복 재시작처럼 보인 현상은 일회성 `wsl.exe -e`
  종료에 따라 WSL 내부 dockerd도 함께 종료된 것이며 Docker Desktop 크래시가 아니다.
- 전체 기동의 실제 차단 원인은 Windows Ollama 임베딩 모델의 GPU 상주다. Q4_K_M
  모델이 VRAM 약 4.37GB를 점유하여 vLLM이 필요한 free VRAM을 확보하지 못한다.
  현재 모델 컨테이너는 중지 상태이며 DB만 정상이다.

기준일: 2026-08-22

이 문서는 세션 간 작업 맥락을 전달하는 상태판이다. 완료 여부가 의심되면 실제 코드,
`git status`, 테스트 결과를 우선 확인한다.

## 1. 구현 완료

- FastAPI·React 기반 세무 상담 UI와 SSE 스트리밍
- JWT httpOnly 쿠키 인증과 사용자·대화 관리
- 국가법령정보 법률·시행령·시행규칙 수집
- 법령해석례 수집 및 법령 검색 경로 통합
- 조문 단위 저장, 개정 해시 감지, 현재 버전 필터링
- pgvector와 키워드 검색을 결합한 하이브리드 검색
- 법령 위계 기반 우선순위 재정렬
- 조문번호 직접 조회 fast path
- 조·항·호·목 및 조/호 가지번호 구조화
- 실제 조문 본문에서 항·호·목 존재 여부와 본문 추출
- 긴 조문의 항 단위 보조 임베딩
- PDF 업로드, 법령형 청킹, 사용자별 문서 격리
- 조건부 Tavily 웹 검색
- 세금 계산기 6종과 tool calling
- 조문 인용·계산 수치 citation guard
- 세무 신고 일정
- Ollama 로컬 모델 연동 및 WSL 호스트 자동 탐지
- liveness·readiness·dependency healthcheck
- Alembic legacy baseline과 Docker 시작 시 `upgrade head`
- 수집·동기화·백필·RAG 평가 CLI
- 채팅 실행 전 `conversation_id`와 로그인 사용자의 소유권 검증
- AI Markdown 응답을 DOMPurify로 정화한 뒤 렌더링
- Docker 빌드 컨텍스트에서 `.env`와 `.env.*` 제외
- 생성 LLM을 vLLM OpenAI 호환 서버로 선택 실행하는 provider 어댑터와 Compose overlay

## 2. 최근 구현 및 검증 상태

최근 작업은 법령 참조 구조화와 다중 사용자 보안 보강이다.

- `reference_parser.py`: 법률·시행령·시행규칙의 조·항·호·목 참조 파싱
- `structure_parser.py`: 요청한 항·호·목의 실제 본문 추출과 실존 여부 반환
- `parser_service.py`: 국가법령정보 XML의 `<항>`, `<호>`, `<목>` 보존
- `LawArticleDetail`: 구조화된 `reference`와 본문 대조 `target` 응답
- 실제 국가법령정보 XML에서 `소득세법 제59조의4 제9항 제2호 가목` 추출 확인
- `require_conversation_owner`: 일반·SSE 채팅 모두 응답 시작 전에 대화 소유권 확인, 타인 소유·잘못된 UUID는 동일한 404 반환
- `MessageBubble.jsx`: `marked` 변환 결과를 DOMPurify로 정화하여 저장형 XSS 차단
- `.dockerignore`: `.env`, `.env.*` 제외 및 `.env.example`만 예외 허용
- `dev/docker-up-wsl.sh`로 backend·frontend 재빌드 및 DB·Alembic·Ollama dependency `ready` 확인
- 현재 backend 이미지의 `/app/.env` 부재 확인
- 마지막 보고된 전체 테스트: `278 passed`
- 생성 LLM 호출을 `llm_client.py`로 통합하고 vLLM 비스트리밍·SSE·JSON Schema 요청 지원
- `docker-compose.vllm.yml`, `dev/docker-up-vllm-wsl.sh` 추가
- vLLM 이미지 0.27.1에서 compressed-tensors NVFP4 및 FlashInfer NVFP4 커널 인식 확인
- 전체 회귀 테스트: 최신 backend 이미지에서 `280 passed`
- WSL에 NVIDIA Container Toolkit 1.20.0 설치 및 Docker `nvidia` runtime 구성 완료
- Docker 컨테이너에서 RTX 5070 Ti Laptop GPU(12,227 MiB) 인식 확인
- LLM·임베딩·리랭커를 역할별 provider adapter/factory로 분리
- 임베딩과 리랭커 provider 선택지를 Ollama·Infinity로 통일하고 CPU Infinity 다중 모델 overlay 추가
- 하이브리드 검색 상위 20개 후보를 Cross-Encoder로 정렬하고 실패 시 기존 순서로 안전하게 fallback
- 생성 모델 체크포인트를 Qwen3.5-9B 원본 bitsandbytes 로딩에서 `ig1/Qwen3.5-9B-NVFP4`로 변경
- RTX 5070 Ti 12GB에서 vLLM 실제 기동 완료: compressed-tensors NVFP4, 텍스트 전용, eager, 기본 KV dtype, 2,048 토큰, 동시 시퀀스 1개
- 기존 검증 기준 `/v1/models`와 thinking 비활성 한국어 chat completion HTTP 200
- 실제 DB 검색 smoke test: CPU 리랭커를 상위 4개·앞 400자로 제한해 5개 결과 유지, 약 12.2초(초기 8개 후보 약 49.7초에서 개선)
- 프런트엔드 채팅 헤더는 health 응답의 실제 provider·모델·embedding version을 동적으로 표시
- 최신 backend 이미지 전체 테스트: `282 passed`

검증 명령은 항상 현재 코드로 다시 실행한다. 위 숫자는 영구 기준이 아니라 마지막 확인 기록이다.

## 3. 현재 작업 트리 주의

2026-08-10 확인 시 보안 보강 관련 변경이 아직 작업 트리에 존재했다. 새 세션은 반드시
`git status --short`와 `git diff`를 먼저 확인하고 사용자 변경을 덮어쓰지 않는다.

주요 변경 가능 파일:

- `.dockerignore`
- `app/services/conversation_service.py`
- `app/routers/chat.py`
- `app/routers/conversations.py`
- `frontend/src/components/Chat/MessageBubble.jsx`
- `frontend/package.json`, `frontend/package-lock.json`
- `tests/test_api_chat.py`

## 4. 남은 우선순위

1. 리랭커 적용 전후 세무 골든셋 Hit@K·MRR·nDCG·지연시간 비교
2. 추출된 `target.text`를 직접 조문 RAG 컨텍스트에 우선 반영
3. 기존 법령 데이터 재수집 및 임베딩 갱신
4. citation guard를 조 번호에서 항·호·목 검증까지 확장
5. 프런트엔드 조문 뷰어에서 대상 항·호·목 강조 및 자동 스크롤
6. 한 질문에 포함된 복수 법령 참조 동시 추출·조회
7. 실제 법률·시행령·시행규칙 XML fixture 회귀 테스트 확충
8. 장기적으로 항·호·목을 별도 구조화 테이블 또는 JSONB로 저장
9. 전체 데이터 갱신 후 RAG 골든셋 재평가

## 5. 알려진 제한과 데이터 보정

- 새 XML 파서는 호·목을 보존하지만 과거 파서로 수집한 기존 DB 행에는 호·목이 빠져 있을 수 있다.
- 전체 반영에는 `python scripts/sync_laws.py --embed`가 필요하다.
- 전체 동기화는 DB와 임베딩을 변경하는 장시간 작업이므로 사용자 동의와 Ollama 상태 확인 후 실행한다.
- 현재 citation guard는 조문번호 중심이며 구조화된 항·호·목 검증은 다음 단계다.
- API의 `target` 응답이 프런트엔드 강조 UI에 완전히 연결됐는지 별도 확인이 필요하다.

## 6. 다음 작업 시작 체크리스트

```text
[ ] git status --short 확인
[ ] AGENTS.md와 docs/ai 문서 확인
[ ] 관련 코드와 테스트 확인
[ ] vLLM 사용 시 dev/docker-up-vllm-wsl.sh로 최신 이미지 빌드
[ ] 변경 범위 테스트 후 전체 pytest
[ ] git diff --check
[ ] CURRENT_STATUS/HANDOFF 갱신
```
