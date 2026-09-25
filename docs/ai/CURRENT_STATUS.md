# 현재 구현 상태

## 2026-09-25 버전별 Knowledge Graph 시범 적용

- 보존 XML에서 버전별 조·항·호·목 노드와 `CHILD_OF` 계층을 구성하고, 명시적 정의·정식 법령명 인용을 출처 문구/해시가 있는 검수 후보로 저장한다. 검수된 관계만 과거 법령 RAG 조회에 연결했다.
- 소득세법 버전 306 `제1조의2` 한 조문만 시범 적재했다. 조·항·호 노드 8개, 정의 개념 5개, 명시적 참조 2개, 후보 관계 7개 중 원문 일치를 확인한 정의 2개·인용 1개를 승인했다. 법률가의 법적 의미 검수나 전수 백필은 아니다.
- 실제 조회에서 `거주자`/`비거주자` 정의와 법인세법 제2조 제1호 인용 보충을 확인했다. WSL 최신 backend 재배포 후 전체 테스트 682 passed/2 skipped. 일반 현행 채팅은 이전 CITES GraphRAG를 유지한다.
- 범위·검수 명령·제한: `docs/TAX_KNOWLEDGE_GRAPH.md`. 현행 `law_articles`와 과거 XML의 항·호 본문 차이/갱신 시점 차이를 보정하기 전에는 현행 지식그래프로 자동 승격하지 않는다.

## 2026-09-25 GraphRAG 근거 보충 고정 개수 제한 제거

- 현행·과거 법령 그래프 확장에서 추가 근거 2건 제한을 제거했다. 현행은 후보 관계 최대 24건·추가 본문 합계 4,000자·3초, 과거는 seed별 후보 최대 12건·3초와 최종 생성 입력 10,000바이트 선별을 유지한다.
- 짧고 검증된 인용 조문 3건이 모두 추가되는 현행·과거 회귀 테스트를 추가했다. 별도 품질 평가 없이 무제한 분량을 LLM에 전달하지 않는다.
- WSL 가상환경에서 `dev/docker-up-wsl.sh backend`로 재배포하고 최신 컨테이너 전체 테스트 678 passed/2 skipped를 확인했다. 읽기 전용 현행 법령 검색 스모크에서는 결과 8건 중 그래프 보충 3건이 반환됐다. 법적 관련성·답변 정확도 판정은 별도다.

## 2026-09-25 로컬 일반 채팅 GraphRAG 재활성화

- 로컬 `.env`에 누락된 `GRAPH_RAG_ENABLED` 항목을 활성화했다. 기존 코드·Compose의 기본값 false와 과거 법령 전용 설정은 변경하지 않았다.
- WSL 가상환경과 `dev/docker-up-wsl.sh backend`로 백엔드를 재생성했다. 실행 중인 백엔드에서 일반/과거 GraphRAG 모두 활성화되고 Neo4j 연결이 정상임을 확인했다.
- 읽기 전용 현행 법령 검색 스모크에서 결과 7건 중 그래프 보충 2건을 확인했다. 사용자 대화·법령 DB·그래프 데이터를 변경하지 않았다.
- 최신 백엔드 이미지 전체 테스트: 676 passed, 2 skipped. 실제 세무 답변의 법적 정확도 향상은 이 스모크로 입증되지 않았으며 복합 질문 골든셋 검수가 남는다.

## 2026-09-25 AI 호출 작업별 설정

- 기존 routing/answer 2단계 설정을 6개 호출 작업별 `LLM_TASK_<NAME>_*` 설정으로 일반화했다. 모든 작업은 기본 GPT-6 Luna를 사용하고 필요할 때 각각 Ollama·OpenRouter·OpenAI 호환 endpoint 등으로 바꿀 수 있다.
- 원격 reasoning effort와 로컬 thinking, provider·model·URL·API key·timeout·temperature·최대 출력 토큰을 작업별로 설정한다. 알려지지 않은 작업명과 잘못된 설정값은 거부한다. health에는 6개 작업 상태를 표시한다.
- 합성 실호출에서 Luna 도구 선택은 성공했다. 최초 검색어 분류 `none`/512토큰은 JSON 파싱 실패 후 폴백하여 `low`/1024토큰으로 조정했고 재호출에서 3개 검색어가 생성됐다. 이는 세무 정확도 검증이 아니다.
- WSL 가상환경으로 backend 최신 이미지를 재빌드했고 컨테이너 전체 테스트는 676 passed/2 skipped였다. `/api/health/dependencies`는 6개 LLM 작업 모두 OpenRouter/Luna `ok`, 전체 `ready`였다.

## 2026-09-25 채팅 모델 역할 분리 — 이전 실험 기록, 현재는 작업별 설정으로 대체

- 최종 답변·과거법령 비교·인용 구조화는 OpenRouter Luna, 도구 선택·법령 분류·검색어 생성은 GPT-5 nano로 분리했다. 모델별 provider를 독립 생성·종료하며 `/api/health/dependencies`에서 둘 다 확인한다.
- 실제 OpenRouter nano의 일반·스트리밍·JSON Schema 응답이 성공했고, 합성 질문에서 계산기 선택과 검색어 생성이 동작했다. 이는 전체 세무 답변 품질 평가를 의미하지 않는다.
- 로컬 Ollama Qwen3.5 9B routing 옵션은 설정·단위 테스트로 검증했으나 이번 작업에서 실서비스 품질 비교는 수행하지 않았다. 기존 LangSmith 월간 trace 한도 429는 별개로 남아 있다.
- WSL 가상환경을 사용해 backend 이미지를 재빌드했고 `docker exec tax_backend pytest -q`는 666 passed/2 skipped였다. `/api/health/dependencies`는 Luna·nano·임베딩 모두 ok, 전체 ready였다.

## 2026-09-25 장문 답변·LangSmith 채팅 추적

- 원격 1회 8,192토큰 출력 제한은 유지하고 `length` 종료 시 최대 2회 이어 생성한다. 일반/SSE 모두 겹치는 문장을 합치고 정상 완료 후 기존 인용·계산 검증 및 저장을 수행한다. 반복 또는 횟수 초과 시 미완료 오류로 처리한다. 프런트엔드 Nginx의 비스트리밍 read timeout은 900초로 확장했다.
- 채팅 `chat_request`/`chat_stream` 루트 LangSmith 추적을 설정하고 Compose `.env`에서 `CHAT_TRACING_ENABLED=true`로 활성화했다. 실제 키는 `.env`에 있으며 값은 문서·로그에 복사하지 않는다. 스트림 사용자 중단 시 도구 작업 취소 회귀 테스트 통과.
- 최신 이미지 661 passed/2 skipped. 합성 추적의 LangSmith 원격 읽기 검사는 **월간 unique traces 한도 429로 실패**했다. 설정은 켜졌으나 현재 계정에서 새 채팅 추적의 원격 저장은 확인되지 않았다. 할당량 복구 또는 증액 후 `dev/probe_langsmith_chat.py`를 다시 실행해야 한다.

## 2026-09-25 유료 생성 경로 안전장치

- Luna 추론 정책을 출력 길이 추정에서 호출 목적(ContextVar) 기반으로 변경: 도구 선택·분류·인용 추출은 none, 답변은 low. 도구 1024/분류 512/인용 2048/과거법령 4096, 원격 전체 출력 상한 기본 8192. 입력 컨텍스트 상한이나 질문당 총 비용 제한은 아니다.
- OpenAI 호환 요청에 전체 응답 deadline을 적용하고 HTTP 429만 응답 전 최대 2회 재시도한다. 긴 Retry-After, 402, 시간 초과, 중간 스트림 실패는 자동 재호출하지 않는다. 일반·SSE·재생성 API는 안전한 오류 code/message를 전달한다.
- 전체가 단일 법령 참조인 원문 요청은 선택 LLM을 생략한다. 일반적인 '그럼/다시'만으로 도구 선택하지 않으며 실제 계산 뒤 금액 변경 후속 질문은 유지한다. 연도 자체를 금액으로 취급하지 않는다.
- 사용량 숫자 메타데이터를 기록하고 채팅 입구의 질문 원문 로그를 제거했다. 당시 Compose backend의 LangSmith 자동 tracing은 opt-in 기본 false였으며, 위 채팅 추적 요청으로 실제 `.env`에서 활성화했다. 테스트는 tracing을 강제 비활성화한다.
- WSL 재빌드 후 실모델 일반·스트리밍·JSON Schema·도구 인자·CitationList·과거법령 Answer 스키마 검증 6종 성공. 합성 입력만 사용했으며 세무 정답률 검증은 아니다. health ready, OpenRouter/Luna·Ollama 임베딩 정상.
- 최종 최신 이미지 테스트: 652 passed, 2 skipped(선택형 Neo4j 통합 테스트), 5 subtests passed. backend healthy, 3002 경유 dependencies ready, runtime tracing 두 플래그 false. git diff --check 통과. 실제 사용자 UI 클릭·세무 골든셋은 이번 검증 범위가 아니다.

## 2026-09-25 OpenRouter GPT-6 Luna 생성 전환

- 사용자 요청으로 실제 `.env`와 공개 `.env.example`의 생성 모델을 `openai/gpt-6-luna`로 변경했다. Ollama 임베딩과 DB 벡터는 유지한다.
- 최초 전환 시에는 출력 상한 400토큰 이하를 추론 none으로 분류했으며, 이후 위 호출 목적 기반 정책으로 대체했다. Luna의 temperature 제외는 유지한다.
- WSL 가상환경에서 비식별 일반 생성·스트리밍·JSON Schema 실호출이 모두 성공했다. `dev/docker-up-wsl.sh backend`로 재빌드·배포했고 `/api/health/dependencies`는 OpenRouter/Luna와 Ollama 임베딩 모두 ok, backend는 healthy다. 최신 이미지 전체 pytest는 632 passed/2 skipped. 세무 정답률·장기 429 발생률은 아직 평가하지 않았다.
- 전체 테스트 종료 후 LangSmith의 월간 추적 한도 429 경고가 별도로 관찰됐다. OpenRouter 생성 검증 성공과는 별개이며 추적 수집 개선은 후속 작업이다.

## 2026-09-25 Qwen3.8 27B 무료 모델 직접 채팅 실험

- 사용자 요청으로 로컬 `.env`의 생성 모델을 Qwen3.8 27B 무료 엔드포인트로 변경했다. 공개 `.env.example`과 기본 모델 추천은 변경하지 않았다.
- WSL 가상환경에서 backend 이미지만 재빌드·재기동했고, 실행 중인 설정 일치·backend/frontend health·프런트엔드 HTTP 200을 확인했다. 추가 생성 호출은 하지 않았다. 직전 비식별 실호출의 일반/스트리밍/구조화 응답은 모두 HTTP 429였으므로 실제 채팅도 제한될 수 있다.
- 다른 모델로 자동 fallback하지 않는다. 실험 종료 후 Dots3로 되돌리려면 로컬 모델 설정을 복구하고 backend를 재기동한다.

## 2026-09-25 재생성 스트리밍 오류 수정·Gemma 무료 모델 호환성 실험

- 답변 재생성 마지막 저장 단계의 `UnboundLocalError(get_pool)`는 함수 내부 중복 import가 전역 import를 가린 것이 원인이었다. 중복 import를 제거하고 재생성 스트림이 최종 저장까지 도달하는 회귀 테스트를 추가했다.
- 일반 채팅·재생성 SSE에서 예기치 않은 제공자/저장 예외를 안전한 `error` 이벤트로 전달하고 `[DONE]`을 보내지 않도록 했다. 내부 예외 내용은 화면에 노출하지 않는다.
- `google/gemma-4-26b-a4b-it:free`를 기존 OpenRouter 어댑터로 비식별 실호출: 일반 생성 HTTP 429, 스트리밍 HTTP 429, 엄격한 JSON Schema 호출 HTTP 404. 당시 생성 모델은 Dots3로 유지했다. 무료 엔드포인트의 단순 JSON 출력 지원은 현재 프로젝트의 엄격한 JSON Schema 지원과 같지 않다.
- 후속: 무료 엔드포인트의 한도/구조화 출력 지원이 변경되면 `dev/probe_openrouter_model.py`로 재검증하고, 통과 시 세무 답변·근거 품질을 별도 비교한다.
- WSL 가상환경에서 백엔드 이미지를 재빌드·재기동했다. Alembic `20260925_0005 (head)`, 백엔드·프런트엔드 health 정상, 최신 백엔드 이미지 전체 631 passed/2 skipped. 실제 사용자 대화 내용이나 DB 레코드는 시험용으로 변경하지 않았다.

## 2026-09-25 마지막 답변 버전 저장·전환

- 마지막 질문 수정은 기존처럼 새 대화로 분기한다. 마지막 답변 다시 생성은 같은 대화의 같은 assistant 메시지에 버전을 추가한다. 기존 내용과 도구 결과는 `chat_answer_versions`에 보존하고 선택한 답변만 `chat_logs.message`에 표시한다.
- 재생성 시 현재 질문 쌍을 생성 문맥에서 제외한다. 완료·DB 커밋 후에만 새 버전으로 전환하며 실패·중단 시 이전 답변을 유지한다. 소유권, 마지막 완료 턴, 예상 선택 버전을 검증한다. 일반 채팅 저장도 대화 행 잠금/트랜잭션을 사용해 버전 저장과 교차 실행을 직렬화한다.
- UI는 마지막 답변에만 버전 선택 버튼을 제공한다. Alembic `20260925_0005`가 필요하다. 재생성·버전 전환 API 및 단위 테스트를 추가했다.
- WSL 가상환경에서 Compose 재빌드 및 Alembic head 적용을 확인했다. 백엔드 628 passed/2 skipped, 프런트엔드 14 passed/빌드 성공, 합성 API Edge 브라우저에서 편집 분기·동일 대화 재생성·버전 이동을 확인했다.

## 2026-09-25 내 정보 화면 카드 잘림·타이포그래피 수정

- 실제 브라우저에서 프로필·비밀번호·계정 삭제 카드의 내용과 버튼이 하단에서 잘리는 문제를 확인했다. 세로 flex 자식 카드의 기본 축소와 카드 `overflow:hidden`이 결합한 것이 원인이다.
- 프로필 전용 스크롤 영역과 `flex:none` 카드 스타일로 변경하고, 헤더·필드·버튼 글꼴/간격을 공통 UI와 맞췄다. 데스크톱 헤더 제목 위치도 스타일 우선순위를 바로잡았다. WSL Compose 재빌드·배포 완료.
- 합성 API Edge headless 브라우저에서 데스크톱/모바일 카드 잘림·가로 넘침·프로필 저장·비밀번호 변경을 검증했다. 프런트엔드 14 passed/빌드 성공, 최신 백엔드 623 passed/2 skipped.

## 2026-09-25 채팅 메시지 액션 아이콘

- 마지막 질문 수정과 마지막 답변 재생성 버튼을 아이콘 전용 액션으로 바꾸고, 완료된 답변마다 공유 아이콘을 추가했다. 접근성 이름·툴팁은 유지한다.
- 공유는 사용자의 클릭 시에만 Web Share API를 호출하고, 미지원 브라우저에서는 해당 답변 텍스트를 클립보드에 복사한다. 공개 링크·서버 측 공유 저장은 하지 않는다. 원본 대화를 보존하는 수정/재생성 흐름은 그대로다.
- WSL venv에서 Compose 재빌드·기동했고 API ready/프런트엔드 HTTP 200을 확인했다. 프런트엔드 단위·렌더링 테스트 14 passed와 프로덕션 빌드 성공. 브라우저 자동화는 로컬 Playwright 패키지가 없어 이번 턴에는 실행하지 못했다.

## 2026-09-25 생성 출처 제목 오탈자 교정

- Dots3 채팅 답변의 출처 목록에서 `Lerer`, `얡수` 등 잘못 생성된 조문 제목을 관찰했다. 현재 `law_articles`의 소득세법 제101조·상속세 및 증여세법 제35조·소득세법 시행령 제167조/제98조 제목은 정상 저장되어 있어 DB 인코딩 문제가 아니라 생성 출력 문제로 판단했다.
- 일반·스트리밍 채팅에서 출처 목록의 제목만 현행 DB 제목으로 교정하고, 조문을 찾지 못하면 생성 제목을 제거한다. 스트리밍은 최종 `replace` 이벤트로 화면과 저장 답변을 일치시킨다. 과거 법령 답변 경로는 현행 제목 교정 대상에서 제외한다.
- 백엔드·프런트엔드를 WSL venv의 `dev/docker-up-wsl.sh`로 재빌드·기동했다. 최신 이미지 전체 백엔드 623 passed/2 skipped, 프런트엔드 13 passed. 컨테이너에서 실제 소득세법 제101조 제목 `양도소득의 부당행위계산`으로 교정됨을 확인했다. 실제 세무 답변의 법률적 정확도 전체는 별도 평가가 필요하다.

## 2026-09-25 Dots3 Note Preview 무료 모델 전환·실행 확인

- Qwen3.8 무료 엔드포인트가 제공자 측 429 제한을 지속하여 사용자 요청으로 `dots-studio/dots-3-note-preview:free`에 수동 전환했다. `.env`/`.env.example`과 README·설계 문서를 동기화하고 WSL venv에서 backend 재빌드·재기동 완료. 다른 모델이나 유료 모델로 자동 fallback하지 않는다.
- 사전 후보 점검에서 Dots3와 Nex Mini 모두 비식별 일반·JSON Schema 요청 HTTP 200과 비어 있지 않은 출력에 성공했다. 범용 설명용 Dots3를 선택했다. 재배포 후 health 전체 ready/생성 Dots3 ok/임베딩 Ollama ok, 비식별 일반·구조화·SSE 실호출 모두 성공.
- 최신 backend 이미지 전체 pytest 619 passed/2 skipped. 이는 제공자 연결·형식 확인이며 실제 세무 질문의 법률적 정확도·인용 품질 또는 장기 가용성을 보증하지 않는다. 무료 Preview 제공자 제한과 외부 전송 정책을 계속 고려한다.

## 2026-09-25 Qwen3.8 27B 무료 모델 고정 — 재기동 후 생성 429

- 실제 `.env`와 `.env.example`의 생성 모델을 `qwen/qwen3.8-27b:free`로 변경하고 WSL venv에서 `dev/docker-up-wsl.sh backend`로 최신 backend를 재빌드·재시작했다. 비밀 키 값은 출력하지 않았다.
- `/api/health/dependencies`는 전체 ready, 생성 `openrouter`/`qwen/qwen3.8-27b:free` ok, 임베딩 `ollama` ok를 반환했다. 이 상태 검사는 모델 카탈로그 조회이지 실제 생성 가능성 검사가 아니다.
- 비식별 일반 생성 실호출은 OpenRouter HTTP 429로 거절됐고 재시도도 429였다. 오류 메타데이터의 `provider_name=ModelRun`과 `raw`에서 해당 무료 모델의 upstream 일시 rate limit을 확인했다. 같은 키의 `/key`는 200, 무료 계정이며 키의 금액 한도 잔여 0은 아니었다. 구조화·스트리밍 생성 실호출은 이번 모델에서 아직 미검증이다.
- 최신 Docker 이미지 전체 pytest 619 passed/2 skipped. 테스트 통과와 health ok를 실제 Qwen 답변 성공으로 해석하지 않는다.

## 2026-09-25 OpenRouter 무료 생성 실제 전환·검증

- 사용자가 실제 `.env`에 API 키를 입력한 뒤 WSL venv와 `dev/docker-up-wsl.sh backend`로 최신 backend를 재빌드·재기동했다. 키 값은 출력·문서화하지 않았다.
- 실제 `/api/health/dependencies`에서 전체 ready, 생성 `openrouter`/`openrouter/free` ok, 임베딩 `ollama` ok 확인. 비식별 요청의 일반 생성과 SSE 스트리밍이 완료됐다.
- `openrouter/free`가 요청마다 서로 다른 무료 모델로 라우팅됨을 관찰했다. 구조화 JSON 요청은 일부 선택 모델에서 HTTP 200/stop이어도 빈 본문 또는 잘못된 JSON을 반환했다. OpenRouter 구조화 요청에 `require_parameters`를 적용하고 유효하지 않은 출력만 1회 재시도하며, 2회 실패는 `invalid_structured_output` 미완료로 처리한다. 재빌드 후 비식별 구조화·스트리밍 실호출 통과.
- 최신 Docker 이미지 전체 pytest 619 passed/2 skipped. 무료 모델의 선택·품질·한도는 변동 가능하며, 세무 답변/인용의 정답률이나 실제 민감 자료 처리 적합성은 이번 스모크로 검증되지 않았다.

## 2026-09-25 OpenRouter 무료 생성 provider 준비 — 키 입력/실호출 대기

- `.env`와 `.env.example`에 `LLM_PROVIDER=openrouter`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `CHAT_MODEL=openrouter/free`, 빈 `OPENROUTER_API_KEY`를 추가했다. 실제 키 값은 기록하지 않는다.
- OpenAI 호환 어댑터에서 llama.cpp 전용 `chat_template_kwargs`를 OpenRouter에 보내지 않고, 일반·JSON Schema·SSE 호출의 종료 사유를 검사한다. WSL 시작 스크립트는 OpenRouter 선택 시 로컬 채팅 모델 설치를 요구하지 않고 Ollama 임베딩만 검사한다. health는 키 누락을 `configuration_missing`으로 보고한다.
- 키가 없으므로 실제 OpenRouter 생성과 모델 품질/무료 한도는 미검증. 현재 실행 중인 Docker 컨테이너는 재배포하지 않아 기존 Ollama 경로를 유지한다. 키 입력 후 WSL venv에서 `dev/docker-up-wsl.sh backend`로 재빌드·기동하고 실제 일반·구조화·스트리밍 답변 및 인용 평가가 필요하다.
- WSL venv 전체 테스트 617 passed/2 skipped(추적 비활성), 스크립트 구문·Compose 설정 검증 통과. 공개 모델 목록에서 `openrouter/free` ID 존재를 확인했다. Windows Git의 `git diff --check`도 통과했다.

## 2026-09-25 8,192토큰 일회성 실험 — 정상 종료, 품질/메모리 한계

- 사용자 요청으로 운영 설정 파일·DB·대화 저장을 바꾸지 않고 격리된 backend 프로세스에서 생성 `num_ctx=8192`를 주입해 직전과 동일한 비식별 복합 질문을 실제 검색·Ollama 스트리밍으로 1회 실행했다. 웹 검색·LangSmith 추적은 비활성화했다.
- 최종 생성 `prompt_eval_count=3815`, `eval_count=1220`, `done_reason=stop`, 약 2,240자, 총 23.8초. 직전 4,096 실험의 3,815+281=`length` 중단과 달리 생성은 끝났다. 단일 샘플이며 다른 질문/동시 요청의 안정성은 미검증.
- 종료 후 `ollama ps`에서 생성 5.7GB·임베딩 4.4GB 모두 100% GPU, 전체 VRAM 11,825/12,227MiB(여유 120MiB). 메모리 여유가 매우 작아 상시 8,192 기본값 전환은 보류한다. 답변의 근거 목록이 요청한 제59조의4/시행령·시행규칙이 아니라 다른 소득세법 조문으로 흐르는 품질 실패도 관찰했다.
- 실험 후 생성 모델에 4,096 요청을 보내 `ollama ps CONTEXT=4096` 복구를 확인했다. backend 환경설정은 원래 4,096으로 유지. 복구 후 GPU 7,361/12,227MiB 사용(임베딩 모델은 언로드 상태).

## 2026-09-25 복합 질문 실제 스트리밍 재현

- 비식별 복합 질문: 소득세법 제59조의4 제1항 제1호 요건과 관련 시행령·시행규칙 추가 요건, 적용/유보 경우, 조문 근거를 함께 요청했다. 실제 `tax_backend` 서비스 파이프라인에서 대화 저장·웹 검색·LangSmith 추적만 차단하고 Ollama·DB·검색은 그대로 사용했다.
- 분류 호출 `stop`(입력 235/출력 46토큰). 최종 생성은 입력 3,815/출력 281토큰에서 `done_reason=length`로 종료했다. 합계 4,096은 현재 `OLLAMA_NUM_CTX`와 일치한다. 약 518자/256청크의 미완성 텍스트 뒤 `LLMGenerationIncomplete`가 발생했고 저장하지 않았다.
- 같은 준비 경로의 입력은 검색 근거 5건·4,326자(모두 소득세법), 시스템 프롬프트 2,300자였다. 시행령·시행규칙 근거는 이 실행의 최종 검색 컨텍스트에 포함되지 않아, 종료 문제와 별도로 복합 질문 근거 선택 실패도 확인했다. 실제 사용자 질문 전체가 이 경로와 동일하다고 일반화하지 않는다.
- 후속: 필수 조문 우선 검색, 다법령/위계 근거 수집, 4,096토큰 내 입력/출력 예산 분리, 실패 시 보수적 유보를 설계·평가한다. 컨텍스트 증설 또는 모델 교체만으로 해결됐다고 주장하지 않는다.

## 2026-09-25 생성 중단 사유 감지

- Ollama `/api/chat`의 `done_reason`과 입력·출력 토큰 수를 원문 없이 로깅한다. `length` 등 비정상 종료를 성공으로 처리하지 않는다. 스트리밍은 일부 내용 뒤 오류 이벤트만 보내고 `[DONE]`을 보내지 않으며, 비스트리밍은 502를 반환한다. 일부 내용은 검증·저장되지 않았음을 UI에 알린다.
- 실제 Windows Ollama `qwen3.5:9b`에 `num_predict=2`로 요청하여 `done_reason=length`, `eval_count=2`를 확인했다. 이는 종료 신호 재현이며 사용자가 보고한 복합 질문의 실제 원인을 확정한 것은 아니다.
- 컨텍스트 4,096토큰/12GB GPU 설정은 유지했다. 복합 질문 재현 후 토큰 계측과 근거 선택 예산을 검토해야 한다. 모델 교체, 재임베딩, DB 변경은 하지 않았다.
- 현재 Ollama 구성으로 backend 이미지를 재빌드·배포했고 `tax_backend` healthy 확인. 최신 이미지 전체 pytest 612 passed/2 skipped(추적 비활성), 프런트엔드 12 passed. 처음 테스트 실행에서는 기존 LangSmith 추적 설정으로 원격 전송 429 경고가 발생했으며, 추적을 끈 재검증에서 경고 없이 통과했다.

## 2026-09-25 국제세무 공식자료 1차 파일럿 수집

- 한–미·한–일·한–중 확장을 위한 미국·일본·중국 법령/안내문과 양자 조약 **17/17건 원본 수집**, SHA-256·크기 검수 통과, 실패 0. 원본 총 21,549,949 bytes. `evaluation/sources/international-tax/pilot-2026-09-25/`(Git/Docker 제외)에 원본·텍스트·manifest·review.html 보존.
- 법적 효력·적용 시점·번역·HTML 본문 선택은 아직 미검수. 한–일 조약 원본 PDF는 스캔본이라 OCR 필요. 미국 법전은 2024년 판본, 일본 안내는 2025년판으로 구분했다. **정답셋/프로덕션 DB/임베딩/Graph/채팅에는 미연결**.
- 수집기 `evaluation/international_sources.py`, CLI `scripts/collect_international_tax.py` 및 재개/읽기 전용 감사. 최신 Ollama backend 이미지 전체 테스트 608 passed/2 skipped, `git diff --check` 통과. 실행·출처·후속 검수: `docs/evaluation/international-tax-pilot-2026-09-25.md`.

## 2026-09-25 국세청 공식 세무일정 캘린더

- 인증 사용자용 `/api/tax-schedule/official`이 국세청 공개 월별 표를 읽어 게시 날짜·제목·비고·원문 URL·확인 시각을 반환한다. 30분 메모리 캐시, 확인 실패 시 24시간 이내 이전 조회만 stale 표시, 그 외 503. 표 구조/요청 연월 불일치는 실패로 처리한다.
- 프런트엔드 사이드바에 세무일정 달력을 추가했다. 이전·다음 달과 달력 아이콘/native 연월 선택(2000-01~다음 연도 12월), 일별 목록·원문 연결·재확인·미게시/오류/오래된 자료 안내 포함. 프로필의 고정 규칙 일정 목록은 공식 캘린더 진입 링크로 교체했다. 개인별 의무 자동판정은 구현하지 않았다.
- 현재 Ollama 구성으로 backend/frontend 재빌드·배포. 실제 인증 API에서 2026년 10월 국세청 실데이터 7건 조회(부가가치세 예정신고 10월 26일), 최신 이미지 전체 테스트 603 passed/2 skipped, 프런트엔드 11 passed/build(직접 연월 선택 포함), 웹 HTTP 200 및 미인증 API 401 확인.

## 2026-09-25 웹 접속 포트 3002로 변경

- Compose frontend 호스트 포트 3000 → 3002, FastAPI CORS 허용 origin·브라우저 테스트/실제 UI 캡처 기본 주소·README 동기화. Nginx 내부 80, Vite 개발 5173은 유지.
- 기존 Ollama 구성으로 backend/frontend 재빌드·배포. Windows `http://localhost:3002`와 `/api/health/ready` HTTP 200, CORS preflight origin 확인. 최신 이미지 pytest 595 passed/2 skipped. DB/벡터와 다른 프로젝트 컨테이너는 변경하지 않음.

## 2026-09-25 런타임 결함 6건 수정·배포

- 역사 라우팅을 의도+시점으로 변경, 계산/문서 연도 오분기 수정. XML structure 기반 항·호·목 조회, 상위 도입 조건 보존, 필수 근거 우선 예산 및 요청 범위 밖 Graph 인용 제외.
- JSON 도구 메타데이터에 법령/버전/기준일/조항을 저장하여 일반/SSE 후속 질문에 사용. 명시 법령명과 버전 ID 소속 검증. 생성/인용 검증 완료 전 ok 금지 및 프런트엔드 실패 구분.
- 현재 Ollama 구성으로 backend/frontend 재빌드·배포, 최신 이미지 595 passed/2 skipped, frontend 8 passed/build, HTTP ready/frontend 200 및 healthy 확인. 원본·임베딩·Graph 데이터 변경/재백필 없음.
- 실제 버전 309 제59조의4 제1항 제1호 추출·필수 근거 유지, 529+부가가치세법 충돌 거부, 529 제1조→제2조 시점 유지, 생성 실패 error 확인. 그래프 범위 제한 후 309 제1항 실제 생성·인용 검증 ok.
- 모델 인용 불일치에 의한 유보는 여전히 가능하다. 연도별 계산 세율 선택(tax_year)은 이번 라우팅 수정과 별개로 미지원. 상세 범위/한계: `docs/evaluation/2026-09-25-history-runtime-fixes.md`.

## 2026-09-25 채팅·과거 법령 런타임 결함 발견 (수정 전 기록)

- 임베딩 누락은 없지만 항·호 파싱, 연도 기반 의도 분기, 긴 조문 근거 선택, 대화 시점 유지에 재현되는 문제가 있다. 입력 법령명/버전 충돌과 생성 실패 상태 표시도 보완 필요.
- 이전 소규모 검색/전수 저장 감사 통과가 이 동작까지 보장하지 않는다. 제품 수정 없이 검토 결과를 `docs/evaluation/2026-09-25-history-runtime-review.md`에 기록했다.

## 2026-09-25 완료 임베딩 실제 검증

- DB 벡터 127,838/127,838·2,560차원, 누락 텍스트-청크 매핑 0. 과거 검색 관련 회귀 테스트 31 passed.
- 소규모 실제 의미 검색 3/3 기대 조문 top-5 포함(모두 1위), 없는 조문/연도만 지정 2/2 유보. GraphRAG 채팅 스모크에서 명시적 인용 1개 확장.
- PostgreSQL/Neo4j 전체 5,400 스냅샷 소속 감사 오류 0, `embedding_complete=true`, MENTIONS 86,552. 세부 방법·한계: `docs/evaluation/2026-09-25-history-embedding-validation.md`.

## 2026-09-25 과거 법령 임베딩 백필 완료

- DB 검증: 127,838/127,838 청크 임베딩, 실패 0, 미준비 텍스트 0. Graph 적재도 5,400/5,400 스냅샷.
- 작업 끝에 `ReadTimeout` 실패 8개를 `embed --retry-failed --limit 8`로 재처리했다. `law-history-indexer` 전체 단계를 재실행해 종료 코드 0과 동일한 완료 수치를 확인했다. 현재 배치 컨테이너는 정상 종료 상태.
- 이 완료는 수집한 법령 범위의 색인 완료를 뜻한다. 과거 법령 검색·답변의 법적 정확도 평가는 별도다.

## 2026-09-24 임베딩 재개 상태 점검

- 이전 진행 정지 후 배치에서 `ReadTimeout` 4개가 기록됐고 프로세스가 오류 종료했다. Docker가 다시 기동한 indexer는 20,532 → 20,632/127,838로 실제 증가 중임을 확인했다.
- 실패 4개는 기본 실행에서 제외되므로 전체 백필 후 `--retry-failed`로 별도 재시도해야 한다. 원인은 Ollama 요청 읽기 시간 초과이며 서버 `/api/tags` 응답은 200이다.

## 2026-09-24 과거 법령 임베딩 재개

- 사용자 요청으로 `bash dev/history-index-wsl.sh start` 실행. `tax_law_history_indexer` running, 재시작 0회 확인.
- 중지 시 저장량 10,292/127,838에서 재개 후 10,320/127,838로 증가, 실패 0. 전체 백필은 계속 진행 중.

## 2026-09-24 임베딩 일시 중지

- 사용자 PC 종료 요청으로 indexer만 중지. `exited`, `running=false` 확인. 저장 완료 10,292/127,838, 실패 0. 데이터 삭제 없음.
- 전체 백필은 미완료이며 사용자 요청 시 `bash dev/history-index-wsl.sh start`로 재개한다.

## 2026-09-24 과거 법령 GraphRAG 배포 — 전체 임베딩 진행 중

- Alembic 20260924_0004 적용, index_texts/search_chunks/text_chunks/graph_progress 추가. 원본/현행 검색 보존. 조문 고유 본문 84,529, 부칙 포함 90,935, 청크 127,838.
- History* Neo4j 5,400 스냅샷 적재 및 전수 소속/버전/hash 검수 통과. 명시적 MENTIONS 86,552. 과거 약칭 해석/법적 계열 적용 확정은 미구현.
- 날짜·법령버전 질의를 history_lookup으로 분리, 모호한 버전/미완료 색인 유보. backend HISTORY_GRAPH_RAG_ENABLED=true 실제 확인. 최신 backend/frontend 배포 및 561 passed/2 skipped, frontend 8 passed/build 성공.
- 실제 생성: 법령버전 1063 제16조 → 1012 제75조 그래프 확장 1건. 버전 529 전체 우선 임베딩 후 번호 없는 질문의 조문·부칙 벡터 검색 확인. 사용자 대화 저장 없는 스모크다.
- 전체 백필 tax_law_history_indexer 재개, 마지막 확인 6,224/127,838 및 실패 0. 완료 아님. dev/history-index-wsl.sh status로 최신 상태 조회. docs/HISTORY_RAG.md 참조.

## 2026-09-24 수집 실행 관리 보강 및 재개

- **완료 확인**: 00:24 KST 41개/5,400 버전 전체 저장, pending/failed=0. 00:27 KST 전수 검수 passed=true, 5,400 스냅샷 불일치 0, 공식 법/영/규칙 표본 3개 일치. worker exit 0. 조문 단위 1,163,620, 부칙 297,843. 보고서 docs/evaluation/2026-09-24-law-history-recovery.md 및 JSON.

- history profile 독립 law-history-worker 추가, dev/law-history-wsl.sh start/status/logs/stop. API 컨테이너 변경 없음. on-failure:3 제한 복구, PC/WSL 종료 후 자동 기동은 보장하지 않음.
- 2,898개 보존 후 pending 재개. 컨테이너 재생성 후 이어받기 확인: 9/23 23:55 KST 3,284/5,400, pending 2,116, failed 0. run 4/5 interrupted, run 6 running 및 실제 lock 확인. 수치는 이후 status 재조회 필요.
- 저장 상태와 lock/heartbeat 관측 상태 분리. 전체 수집 완료 후 evaluation.history_audit 전수 검사 및 공식 표본 3건 검수를 자동 실행, evaluation/runs/law-history에 시각별 JSON 보존.
- 최신 이미지 전체 테스트 543 passed/2 skipped. 별도 실제 수집 및 전수 검수도 완료했다. 법적 적용 시점 판정·구법 검색 연결은 아직 미완료다.

## 2026-09-23 과거 법령 데이터 검수

- 22:13 KST 읽기 전용 DB 검수: 41개/5,400 목록 중 2,898 원문 저장(53.7%), pending 2,502, failed 0. 8개 법령만 본문 목록 수 일치. 조문 단위 684,031, 부칙 단위 218,799(버전별 반복 포함).
- 저장된 모든 원문 해시/ID/시행일/공포일/공포번호 및 조문·부칙 재파싱 저장 대조 불일치 0. 공식 API 표본 3건 XML 해시/파싱 일치. 동일 파서 round-trip 검사이며 법적 적용 의미 검증은 아님.
- run 4 running 표시는 오래된 상태: heartbeat 9/22 21:10 KST, docker top에 수집 worker 없음. 수집은 중단 상태이며 이번 검수에서 재개·상태 수정하지 않음.
- 같은 법령/시행일의 복수 버전 묶음 474개. 단순 날짜 정렬로 법적 적용 버전을 확정하면 안 됨. 결과 docs/evaluation/2026-09-23-law-history-audit.md 및 JSON. 읽기 전용 검사 코드 evaluation/history_audit.py.

## 2026-09-22 조회 실패 판단 유보

- 최신 이미지 빌드 후 Compose 환경 일회성 컨테이너에서도 526 passed/2 skipped 확인. DB 설정 없는 단독 docker run에서는 DB 의존 계산기 테스트 2개가 503으로 실패했으며, Compose DB 환경에서 재검증 통과. 운영 API/수집 worker 재시작 없음.

- chat_service의 계산 실패 생성 차단을 법령/문서 도구에도 확장. invalid_arguments/needs_input/not_found/timeout/error 및 알 수 없는 실패 상태에서 고정 안내 반환, 일반/SSE 모두 최종 LLM·인용 보정 우회. 실패 문구를 자유 생성 근거로 쓰지 않음.
- 22개 회귀 테스트 추가, 전체 526 passed/2 skipped. 수집 작업을 보존하려고 서비스 컨테이너 재시작은 하지 않음. 실행 중인 API는 재시작 전 기존 import를 사용하며 변경 활성화는 수집 완료 후 재배포 필요.
- 수집 상태 확인: 5,400 중 1,574 저장/실패 0/run 4 running. 시점성 수치이므로 이후 실제 status 확인. 일반 RAG 빈 결과·구법 적합성·Judge 교정은 후속.

## 2026-09-22 과거 법령 아카이브 시작

- Alembic 20260922_0003 적용: 별도 law_history 스키마에 범위/법령/시행일 버전/원문 스냅샷/조문/부칙/수집 run 및 coverage·관측 버전 순서 뷰 추가. 기존 검색 테이블·임베딩·Neo4j 수정 없음.
- 현재 원문 수집 41개 법령을 scope로 고정. 공식 eflaw 전체 페이지 5,400개 버전 목록 확보, 41/41 discovery 완료. 연혁·현행·시행예정 합계이며 공식 ID 변경 전신 법령까지 완전 수집했다는 뜻은 아님.
- (law_id,MST,시행일)로 단계 시행을 구별. 전체 정제 XML과 삭제/표제 조문 및 부칙 보존. identity/시행일/공포일 대조. 동일 본문 재수집 멱등·정정 원문 추가 보존을 실제 DB transaction rollback으로 검증.
- 본문 10개와 최오래된 소득세법 1949-07-15 버전 저장 확인 후 전체 미수집 본문 수집 시작. 진행률은 scripts/collect_law_history.py status로 확인. 완료를 추정하지 말 것. 5회 연속 실패 시 중단, 재시작은 collect, 실패 재시도는 --retry-failed.
- 최신 Ollama backend 이미지 재빌드, 전체 504 passed/2 skipped. 실행/스키마/제한 docs/LAW_HISTORY.md. 버전 목록·원문 show·동일 법령 본문 diff 지원. 채팅 시점 검색·구법 임베딩·과거 Neo4j 관계·법적 조문 승계 자동 확정은 미연결.

## 2026-09-22 판례 5건 실제 답변 및 Judge 진단

- WSL venv + dev/docker-up-wsl.sh로 현재 Ollama 서비스 재빌드/기동. 컨테이너 Graph 설정은 false로 관측되어 과거 활성화 기록과 다름. 임의 변경 없음. 이번 실험은 Graph A/B가 아니다.
- evaluation/precedent_pilot.py: 실제 process_chat 5건 실행, 웹/대화 저장/클라우드 추적 차단, 정답 판결요지는 Judge에만 전달. 생성 5/5, 도구 입력 오류 2건·not_found 1건에도 생성이 지속됨. 나머지 2건은 일반 검색 5개씩.
- judge.assess의 명시적 diagnostic_draft 옵션만 초안 진단 허용; 기존 CLI 미승인 차단 및 인간 gate 유지. 16,384 컨텍스트/14,000 bytes 상한. 전체 공식 판결요지를 사용하며 본문 전체 평가가 아님.
- Judge 10항목 pass 6/fail 3/error 1이지만 모순된 답변을 pass 처리하는 의미 판정 오류 확인. 정답률로 해석 금지. 원시 결과 evaluation/runs/precedent-pilot-20260922, 분석 docs/evaluation/2026-09-22-precedent-pilot.md.
- 서비스 오류 처리는 수정하지 않음. 후속 우선순위: 조회 실패 시 유보/fallback → 구법 근거 검증 → 원자적 루브릭/반례로 Judge 교정. 최신 서비스 이미지에 평가 변경 파일을 복사한 컨테이너에서 496 passed/2 skipped, git diff --check 확인. LangSmith 업로드 없음.

## 2026-09-22 판례 검수용 읽기 문서

- 로컬 수집 10건/초안 5건 파일 존재 확인. evaluation/precedent_review.py로 해당 배치의 검수자료.html 생성. 사건 목록·질문/채점 초안·판시사항·요지·참조조문·판례내용 전체를 읽기 전용으로 제공한다.
- 별도 대시보드/서버/승인 기능은 추가하지 않았다. 원본 JSON과 draft 상태 유지, 외부 전송 없음. 산출 HTML도 sources 하위라 Git/Docker 제외.

## 2026-09-20 공식 판례 평가 후보 수집

- 법제처 prec API 실제 연결 성공, 대법원 출처/4개 참조법령 검색으로 목록·본문 10건 수집, 오류 0. 세무 8/민사 2건이며 후보 전체를 보존했다. 출처 ID/사건번호 일치 및 본문 길이 확인.
- evaluation/sources/precedents/2026-09-20-pilot: 원본 JSON, manifest, 검수 목록 README, draft-cards.json 5건. 소득세 주택 특례·예식 꽃 장식·외국납부세액·상한 초과 중개수수료·상속재산 시가 쟁점 선정. 모두 dev/draft, 승인 0, 스키마 검증 통과.
- evaluation/precedents.py 추가. 원본/초안은 Git·Docker 제외, OC URL 정제, 기존 파일 덮어쓰기 금지. 운영 DB/Neo4j/임베딩/모델 학습/서비스 재시작/LLM Judge 호출 없음.
- 사건의 사실관계 전체·귀속기간·구법/부칙·관련 심급과 후속 판결 검수는 미완료. 판시사항/요지로 만든 초안을 정답 인증으로 해석하지 말 것.

## 2026-09-19 마지막 질문 수정·답변 재생성

- 마지막 완료 턴에 질문 편집/다시 답변 버튼 추가. POST conversations/{id}/revise는 소유권·마지막 메시지 ID·완료된 user/assistant 쌍을 검증하고 직전 턴 이전 문맥만 새 대화에 복사한다. 원본은 수정하지 않는다. 기존 테이블 사용, 스키마 변경 없음.
- 메시지 API에 message_id 추가, 저장 완료 후 UI 재조회. 문맥·목록 메시지는 id 순서로 정렬하여 같은 타임스탬프의 순서 모호함을 제거했다. 생성/분기 요청 중 중복 클릭 차단 및 대화 이동 후 늦은 응답 무시.
- WSL venv + 기존 Ollama 실행 스크립트로 Docker backend/frontend 재빌드. 전체 backend 490 passed/2 skipped, frontend 8 passed/build 성공. Edge 합성 API 브라우저에서 편집·재생성·새 대화 라우팅 확인. 실제 PG 트랜잭션으로 복사/원본 보존 검증 후 테스트 데이터 rollback.
- 생성 LLM의 실제 재답변 품질은 이번 검증 대상이 아니다. 한 대화의 버전 넘기기 대신 별도 대화로 보존한다. 서버 전역 중복 요청 방지/idempotency는 미구현이며 여러 탭 요청은 별도 분기를 만들 수 있다.

## 2026-09-19 Judge 증거 ID 보정

- 직접 발췌 문자열 대신 A/R ID 선택·원문 복원, 중복/없는 ID 차단. 일반 paired와 기존 합성 정보 부족 사례의 behavioral 정책을 분리했다. omission/absence 모드와 최대 1회 형식 보정 추가.
- 같은 저장 답변 재평가: 기존 pass 1/error 2 → pass 3/error 0. 결과 evaluation/runs/judge-evidence-ids-01/judge.md. 1개 합성 행동 사례의 보조 평가이며 세무 정답률이나 Judge 전체 정확도는 아니다.
- 관련 테스트 43 passed. 운영 서비스/DB/원래 관측과 인간 gate 변경 없음. LangSmith 전송 없음.

## 2026-09-19 LLM Judge 초기 연결

- evaluation/judge.py와 CLI judge 추가. 기존 run/hash/관측 검증, 항목별 구조화 판정과 발췌 대조, 비밀 예외 비노출, draft/원문 부재 unknown 처리. 인간 gate/Adjudication은 변경하지 않는다.
- 로컬 현재 provider 모델 사용. 첫 저장 답변 평가는 입력 예산 초과 3 unknown, 예산을 6000 UTF-8 bytes/컨텍스트 8192로 조정해 재실행. 생성 답변을 자르지 않았다.
- 관련 테스트 40 passed. 서비스 재배포/DB 변경/외부 전송 없음. LangSmith 자동 Judge feedback 연결 및 미검수 5개 법령 카드의 실제 정확도 평가는 후속이다.
- 실제 로컬 Qwen3.5:9b로 과거 생성된 정보 부족 답변 1개/루브릭 3개 평가: judge-pilot-02 및 오류 종류 구체화 후 judge-pilot-03 모두 pass 1/error 2. 금액 미확정 항목만 통과, 나머지는 발췌 검증 오류로 답변 오답과 구분한다. 종합 정확도 산출 불가. 결과 evaluation/runs/judge-pilot-03/judge.md (Git 제외). 최종 관련 40 tests 및 diff check 통과.

## 2026-09-19 평가 기준 구체화

- evaluation/QUALITY_CRITERIA.md: 검색/Graph/답변/계산 11항목, 판정 상태·분모·중대 오류·Judge 교정·A/B 비교 규약 작성.
- datasets/answer_pilot.json: 기본공제/면세 포기/의료비 예외/과거 귀속/입력 부족 5개 dev/draft 카드. 기존 Dataset 규약, recorded 어댑터와 input.review_card를 사용한다. 후보 근거·필수/금지 주장·혼동 후보·교정용 오답을 분리했다.
- 공식 원문 적용 버전·부칙·인간 승인은 미완료. Judge 구현/실행 및 LangSmith 전송 없음. 서비스/Graph 설정과 DB는 변경하지 않았다.

## 2026-09-19 실제 채팅 GraphRAG 활성화

- 사용자 요청으로 LLM Judge 구현은 보류하고 로컬 `.env`의 GRAPH_RAG_ENABLED=true 적용. 기존 Ollama 유지, WSL venv + dev/docker-up-wsl.sh backend frontend neo4j로 재빌드했다. 코드/Compose 기본값 false는 유지한다.
- 그래프 확장 로그에 base/added 개수만 추가했다. 일반/SSE 채팅의 기존 hybrid_search 경로를 사용하며 원문 단독 조회·문서 도구 및 관계도 UI는 변경하지 않았다.
- 읽기 전용 감사: 조문 6,675/인용 8,387, 누락·중복·무결성 오류 0. 미해결 참조 6,275는 그대로이며 재수집/DB 변경 없음.
- 프런트 Nginx 경유 실제 회원가입→로그인→대화→SSE→저장 재조회 확인. 정상 한국어 질문에서 base=5 added=2, 약 15.1초, DONE 및 메시지 2개 저장. 답변에 부가가치세법 시행령 제57조·제58조 인용 포함. 브라우저 시각 검증이나 법적 정답 판정은 아니다.
- 검증 중 WSL 재기동 직후 Neo4j 미준비 요청은 ServiceUnavailable 후 기본 검색으로 정상 응답. 초기 PowerShell stdin 한글 손상 요청은 성공 사례에서 제외하고 Unicode escape로 재검증했다. 합성 스모크 계정/대화 3개는 보존했다.
- 로그 비노출 테스트 추가 후 최종 재빌드 이미지 전체 478 passed, 2 skipped, 26 warnings, 5 subtests passed. git diff --check 통과. 답변의 조건·설명 정확성과 전체 프롬프트 토큰 예산 검증은 여전히 필요하다.

## 2026-09-19 LangSmith 키 파일 변경

- .env.example을 현재 .env의 설정 항목과 Ollama 구성에 맞췄다. 미사용 llama.cpp/전환 예제를 제거하고 EMBED_MODEL·JWT_EXPIRE_MIN·외부 API 키 입력란을 반영했다. 비밀번호/JWT/외부 API는 예시값 또는 빈 값, 기존 LangSmith 키는 보존했다. 실제 .env는 변경하지 않았다.

- 사용자 요청으로 평가 publish의 키 입력 파일을 .env.example로 변경했다. .env.langsmith와 중복 키 예제 파일을 삭제했다. 실제 키는 출력하거나 복사하지 않았다.
- .env.example의 Docker 포함 예외를 제거했다. Git 추적은 그대로이므로 실제 키가 담긴 파일을 커밋하지 말 것. 아래 .env.langsmith 사용 안내는 과거 이력이다.

## 2026-09-19 LangSmith 평가 화면 전환

- 자체 대시보드 소스·실행기·전용 테스트 제거, 8765 프로세스 종료 확인. 아래 로컬 UI 내용은 과거 이력이며 현재 실행 경로가 아니다. Python 캐시만 남을 수 있다(캐시 디렉터리 재귀 삭제는 실행 정책에서 거부됨).
- evaluation/langsmith_bridge.py 및 CLI langsmith prepare/publish 추가. 기존 scorer 재계산/저장 report 대조, 기본 본문 제외, 본문/검수 큐 명시 선택, 전송 계획 hash 승인, 원격 base/graph 실험·feedback·선택 annotation queue 매핑, 부분 실패 receipt·중복 실험 방지 구현.
- langsmith==0.12.1 고정. .env.langsmith에 빈 API key 자리 마련(Git/Docker 제외, 서비스에는 로드하지 않음). production 추적·모델/DB 호출·GraphRAG 설정 변경 없음.
- 실제 retrieval-rescored 39문항/78결과로 metrics/review 계획 생성 성공(uploaded=false). API 키 미설정으로 원격 계정 연결·업로드·LangSmith UI 검증은 아직 수행하지 않았다.
- 로컬 평가 테스트 45 passed(신규 bridge 9개), 최신 Compose 이미지 전체 476 passed/2 skipped/26 warnings/5 subtests passed. SDK 메서드 규약 기반 mock 검증이며 실제 클라우드 검증은 아니다. git diff --check 통과.
- 사용법 evaluation/LANGSMITH.md. LangSmith 인간 검수의 자동 다운로드/로컬 Adjudication 변환은 미구현이며 수동 검수·재채점한다. 기존 runs/reviews는 보존했다.

## 2026-09-19 로컬 평가 대시보드 (이력: LangSmith로 대체)

- 명칭을 evaluation_dashboard로 통일했다. 패키지·import·테스트 파일·문서·CI/Docker 제외 경로를 함께 변경했으며 대시보드 테스트 8개 통과. 실행 명령과 포트는 동일하다.

- evaluation_dashboard(별도 FastAPI·정적 화면)와 scripts/evaluation_dashboard.py 추가. 127.0.0.1:8765에서 수동 실행하며 제품 프런트엔드/API/Compose에는 연결하지 않는다. UI 코드·검수 파일은 서비스 Docker 이미지에서 제외했다.
- 실행 목록·영역별 지표·질문별 실제 출력·검색 근거/답변 검수·변경 이력·JSON 다운로드·동일 조건 실행 비교 지원. 모델·DB 호출과 평가 실행 버튼은 없다.
- 원본 runs는 수정하지 않고 reviews에 해시 결합 리비전 저장. 낙관적 충돌 검사, Host/Origin/저장 토큰, CSP·텍스트 렌더링, 경로 탈출 차단 적용. 검수자 이름은 본인 기재이며 인증된 신원이 아니다.
- WSL 평가/UI 테스트 44개(신규 UI 8개) 통과. 최신 서비스 Docker 이미지 전체 467 passed/2 skipped(UI 테스트는 로컬 전용이라 이미지 제외). Edge에서 실제 검색 78행/231후보, 답변 양식, 모바일 가로 넘침 없음 검증. 실제 후보에 테스트 검수는 저장하지 않았다.
- 기존 서비스 컨테이너 재시작·DB 수정·GraphRAG 활성화 없음. 실행/검수 절차는 evaluation_dashboard/README.md.

## 2026-09-19 평가 실행 파일 정리

- scripts/evaluate.py는 얇은 실행 진입점으로 유지하고 기존 명령 처리를 evaluation/cli.py로 이동했다. validate/run/suite/score/compare와 기존 옵션을 보존했다.
- 안내만 출력하던 scripts/eval_rag.py·scripts/eval_graph_rag.py를 제거했다. 기존 질문·평가 결과와 데이터 수집·Docker 기동 스크립트는 보존했다. 아래 이전 평가 기록의 구 파일명은 당시 이력이다.
- CLI 실행·종료 코드·비밀 오류 내용 비노출 회귀 테스트 7개를 추가했다. WSL 평가 관련 테스트 36개 통과.
- 최신 Compose 이미지 일회성 컨테이너에서 전체 467 passed, 2 skipped, 합성 평가 22개 gate=pass. 서비스 컨테이너 재시작은 하지 않았다. 초기 독립 컨테이너는 토크나이저 다운로드 차단/DB 설정 부재로 실패했고 Compose 환경으로 재검증했다. git diff --check 통과.

## 2026-09-19 요소별 평가 파이프라인 재설계

- 최종 최신 Docker 검증: 460 passed, 2 skipped, 26 warnings, 5 subtests passed. 새 평가기 테스트 29개 포함. scorer 1.1의 합성 22사례/반례 통과, git diff --check 통과. CI 구성은 로컬에서 동등 명령을 검증했으며 원격 CI 실행 결과는 아니다.

- evaluation/schema.py·scoring.py·adapters.py·runner.py와 scripts/evaluate.py 추가. validate/run/suite/score/compare, 영역별 report JSON/Markdown, 실행별 정답/관측/검수 hash, 중복/group split 누출 검사, 반례 검증, 종료 코드 gate를 구현했다.
- contracts 22개 + 각 오답 반례, 기존 검색 39문항을 draft/dev로 이관(제안 hard negative 6개), component 7개 계약/검수 초안. 모델이 정답을 자동 확정하지 않는다. 공식 승인에는 출처·기준일·버전·인간 검수가 필요하다.
- 실제 검색 39문항 base/graph 비교 실행: 실행 오류 0, 공개 DB fingerprint 전후 동일, 검수 후보 231개 생성. 초안 기대 조문이 있는 38개 중 37개 발견했지만 공식 품질 점수는 아니며 gate=incomplete. 과거 정답 세목 필터를 준 38/38과 직접 비교 금지.
- 실제 계산 잘못된 입력 처리·모델 도구 선택 통과. 고정 컨텍스트 답변 생성 성공 후 인간 루브릭 미검수로 incomplete 유지. 모든 raw 결과는 evaluation/runs/에 보존(Git/이미지 제외).
- 기존 eval_rag.py/eval_graph_rag.py는 종료 안내로 대체했고 과거 결과는 삭제하지 않았다. CI에 스키마/반례/합성 계약 실행과 artifact 업로드를 추가했으며 원격 CI 자체를 실행한 것은 아니다.
- 현재 한계: 전문가 승인된 실제 세무 gold는 아직 없음. context/safety/performance는 recorded 관측 계약만 있고 전체 제품 trace 자동 계측은 후속. 신규 평가기가 답변 정답률을 인증하거나 GraphRAG를 활성화한 것은 아니다.
- 상세 판정 규약·검수·명령: evaluation/README.md. 운영 provider는 Ollama 그대로, GraphRAG=false, PG 스키마/벡터/법령 데이터 변경 없음.

## 2026-09-19 GraphRAG 연결·약칭 확장·실제 비교

- 9/13에 남긴 config/Compose/검색 메타데이터/Neo4j 의존성 불일치와 재정경제부 수집 필터를 복구했다. 일반 hybrid_search의 단일/멀티쿼리 뒤 선택형 그래프 확장이 연결됐다.
- 원문에 유일하게 정의된 법/영 약칭을 정의 이후 범위에서 해석한다. 정의 조문 버전도 저장·재검증한다. 인용은 양방향 1-hop, 역방향은 동일 계열만, 키워드 필터와 3 seed/24 후보/+2 조문/추가 4,000자/3초 제한이다.
- WSL venv + dev/docker-up-wsl.sh로 실제 Ollama 구성을 유지해 재빌드. 최신 Docker pytest 431 passed, 2 skipped, 26 warnings, 5 subtests passed. 격리 Neo4j 통합 2 passed. 프런트 경유 ready/dependencies HTTP 200.
- 6,675개 조문 CITES를 2,464→8,387개로 동기화. 감사 누락·중복·버전 무결성 오류 0, 미해결 6,275(대상 없음 3,198/호 확인 실패 2,953/항 확인 실패 124). TaxLaw 39개 보존, 관측 스냅샷 2개. PG 7,587행/벡터와 집계 해시 전후 동일.
- 신규 scripts/eval_graph_rag.py로 기존 라벨 38문항 실제 비교: 기본 top-5 38/38, 확장 전체도 38/38, 23문항에 보충, 평균 확장 0.118초. 질문 분류/답변 생성은 평가하지 않았고 새로운 정확도 향상 근거는 없다.
- GRAPH_RAG_ENABLED=false 유지. 같은 계열 내 부적절한 추가 근거도 남아 있어 복합 질문 정답셋·근거 정밀도·전체 토큰 예산·생성 답변 검증 후 활성화한다. 제품 UI는 아직 별도 연결하지 않았다.
- 상세: docs/GRAPH_RAG_VALIDATION_2026-09-19.md, docs/evaluations/graph_rag_2026-09-19.json. 이전 9/13 미복구/실패 기록은 당시 상태이며 위 결과가 현재 상태다.

## 2026-09-13 Neo4j 통합 테스트 정리

- dev/verify-graph-wsl.py를 제거하고 tests/integration/conftest.py 및 test_neo4j_graph.py로 전환했다. --run-neo4j 명시 시에만 격리 Docker DB를 생성하고 --graph-real-sample 추가 시 tax_backend 공개 법령 표본을 읽는다. 일반 실행은 두 테스트 skip.
- WSL venv 실제 통합 2 passed, 기본 실행 2 skipped. 테스트 이름으로 만든 임시 컨테이너/익명 볼륨 정리 확인. 기존 서비스/DB/이미지는 보존.
- 현재 로컬 전체 pytest: 414 passed, 10 failed, 2 skipped(26 warnings, 5 subtests). 기존 config의 GRAPH_RAG_ENABLED/NEO4J_DATABASE 누락 및 재정경제부 필터 미반영 등 작업 시작 시 상태와 그래프 테스트의 불일치가 확인됐다. 해당 애플리케이션 설정은 이번 범위에서 복원하지 않았다.
- 현재 작업 트리의 Compose에도 Neo4j가 없어 실행 중인 서비스와 다르다. 이번 작업에서는 서비스 재빌드/재시작하지 않았다. 전체 테스트 성공이나 배포 가능 상태라고 해석하지 말 것.

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
