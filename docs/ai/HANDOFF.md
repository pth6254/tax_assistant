# 세션 인수인계

## 2026-09-26 관계 블라인드 검수 인계
- `evaluation/sources/kg_relation_blind_review_20260926.json`에 56건 블라인드 양식을 생성했다. Judge 예측·추출/혼동 생성 유형을 포함하지 않으며 `review` 필드는 전부 비어 있다. 파일은 Git 제외이며 기존 풀·결과는 보존했다.
- 실제 법령 검수자가 문구상 관계 라벨, 원본 확인, 대상 버전 시점 상태, 이유·검수자·날짜를 직접 기록해야 한다. 완성본을 새 파일로 저장한 뒤 `python -m evaluation.kg_relation_human_review finalize`로 엄격 검증하고 `kg_relation_score.py`로 비교한다. 정확한 명령은 `evaluation/KG_RELATION_REVIEW.md`.
- 아직 인간 골드 0건, 품질 점수 없음, Neo4j 승인/서비스 반영 없음. 모델이 스스로 인간 라벨을 채워서는 안 된다. 양식의 reviewer는 인증된 사용자 계정이 아니므로 전문가 검수·이중검수·불일치 조정은 운영 절차로 남는다.
- 새 백엔드 이미지는 빌드했지만 실서비스 컨테이너는 교체하지 않았다. Compose 환경의 일회성 최신 이미지 컨테이너에서 전체 테스트 716 passed/2 skipped. 단독 `docker run`은 기존 DB/모델 설정 의존 테스트 3건이 실패했으나 Compose 환경에서는 통과했다.

## 2026-09-26 관계 Judge 전수 진단 후 인간 검수
- 56건 전수 2회 진단의 최종 로컬 결과는 `evaluation/runs/kg-relation-final-20260926.json`이다. 모두 `advisory_only`; 추출 48건은 `supported`, 대상 교환 혼동 8건은 `unsupported`로 합의했다. 총 Judge 시도 144회(429 및 원문 인용 검증 오류 재시도 포함), 제공자 반환 총 65,245토큰·0.0100509 USD. 성공률이나 법적 정답률로 발표하지 않는다.
- 인간 검수자는 Judge 판정이 없는 `evaluation/sources/kg_relation_stratified.json`에서 원문·출처·시점·관계 의미를 독립 검토하고 별도 `human_relation_gold`에 검수자·날짜·이유를 기록해야 한다. 골드 0건이며 Neo4j 승인/서비스 변경은 없다. 자세한 인계는 `evaluation/KG_RELATION_REVIEW.md`.
- 완료된 보고서의 실패 카드만 새 결과 파일에 재시도할 수 있도록 `--retry-from`과 요청별 `--delay-sec`를 추가했다. 후속 과제는 인간 라벨 확보, `kg_relation_score.py` 비교, 시점상 적용 및 실제 질문 적합성 평가다.

## 2026-09-26 관계 평가 표본·배치 확장
- `evaluation/kg_relation_review.py --auto`로 기준일 2026-09-26 이전 시행 버전만 포함한 6개 법령·56개 후보 카드 생성. 법률/시행령/시행규칙 19/19/18, 과거/최근 27/29, DEFINES/CITES 28/28, 대상 교환 혼동 후보 8건. 결과 `evaluation/sources/kg_relation_stratified.json`은 Git 제외. 최초 초안에는 미래 시행 버전이 섞였으나 기준일 필터 추가 후 초안·해당 진단 파일을 제거했다.
- 전체 56건 원본 재검증 결과 `source_verified=56`; 저장 결과 `evaluation/runs/kg-relation-preflight-asof-20260926.json`. OpenRouter Luna 2건 실호출 결과 `advisory_only=2`, 시도 2회, 제공자 보고 727 입력/141 출력 토큰·cost 0.0001432. 결과 `evaluation/runs/kg-relation-asof-smoke-20260926.json`. 모두 모델 의견이며 인간 골드 라벨은 0건.
- `KG_JUDGE_*` 전용 설정과 카드별 원자적 체크포인트, 동일 설정 재개/명시적 실패 재시도, 제공자 사용량 기록을 구현했다. 아직 LangSmith 관계 평가 업로드, 전문가 라벨, 실제 법적 적용 판단 비교는 없다.
- 2026-09-26 최신 backend 이미지를 `dev/docker-up-wsl.sh backend`로 재생성했고 `docker exec tax_backend pytest -q`: 705 passed/2 skipped. 체크포인트 중단·재개와 미래 시행 버전 배제·재시도 호출 수 회귀 테스트를 포함한다.

## 2026-09-26 관계 LLM Judge 평가 경로 추가
- `evaluation/kg_relation_judge.py`: 원본 재대조가 통과한 미검수 관계 카드만 provider 중립 `structured()` 호출로 진단한다. 2회 기본 반복, exact 원문 인용 검증, 입력 예산·오류 유보가 있으며 결과를 로컬 JSON으로 저장한다. Neo4j 승인/채팅 경로는 변경하지 않는다.
- `evaluation/kg_relation_score.py`: 별도 인간 검수 gold의 출처 풀 해시·검수자·날짜를 확인한 뒤에만 커버리지/정확도/정밀도/재현율/hard negative 오인율을 계산한다. 실제 인간 gold는 아직 0건이고 LangSmith 업로드도 아직 연결하지 않았다. 문서: `evaluation/KG_RELATION_REVIEW.md`.
- 남은 일: 법률·시행령·시행규칙과 시대별 층화 카드 확장, 전문가 라벨 확보, Judge vs 인간 골드 비교, 시점상 적용 판단 평가, LangSmith 전송 범위 검토. 현재 관계 Judge를 실제 법적 정확도나 자동 승인 장치로 취급하면 안 된다.
- WSL 실호출 스모크: OpenRouter `openai/gpt-6-luna`로 소득세법 관계 카드 1건을 2회 진단했고 두 실행이 모두 `supported`로 일치했다. 저장 위치는 Git 제외 `evaluation/runs/kg-relation-smoke-20260926-final.json`. 이것은 모델 의견일 뿐 정답률·전문가 승인 결과가 아니다. 최초 스키마의 선택 필드는 OpenRouter strict JSON 요청이 거절되어, 모든 출력 필드를 필수로 고친 후 성공했다.
- 최신 backend 이미지를 `dev/docker-up-wsl.sh backend`로 재생성했고 컨테이너 healthy, 전체 테스트 698 passed/2 skipped를 확인했다. 이 테스트는 전문가 골드와의 실제 품질 비교를 대체하지 않는다.

## 2026-09-26 과거 법령 XML 검수 오탐 및 관계 검수 카드
- 버전 3162·3163의 제125조에는 같은 조문번호의 개정 지시문과 조문 본문이 별도 `law_history.articles` 행으로 보존되어 있다. 두 행의 XML `조문내용`은 각각 자신의 본문에 포함된다. 기존 `validate_all_sources()`가 조문번호로 본문을 사전화하면서 마지막 행만 남겨 2건을 오탐했다. 이제 `source_article_id`로 정확한 원본 행을 비교한다. 원본 DB·Neo4j 데이터는 변경하지 않았다.
- `tests/test_tax_knowledge.py`에 중복 조문번호 오탐 방지와 진짜 XML/본문 불일치 감지 회귀 테스트를 추가했다. 전체 5,400개 버전(조문 1,038,278행, 구조 단위 6,924,423개) 재검수 결과 해시·파싱 오류 0, XML/본문 불일치 0이다. 중복 구조 단위 1,734개/101버전은 그대로 보존·모호성 차단 대상이다. 최신 backend 이미지 `pytest -q`: 689 passed, 2 skipped.
- `evaluation/kg_relation_review.py`와 `evaluation/KG_RELATION_REVIEW.md`를 추가했다. 실제 원본의 정의·인용 관계에서 재현 가능한 미검수 카드를 만들며, `evaluation/sources/kg_relation_review_pool.json`에 초기 13건(DEFINES 5, CITES 8)을 생성했다. 모두 소득세법 버전 306의 후보이고 골든 라벨은 0건이다. 버전 3162·3163 제125조는 관계 후보가 없어 카드 0건이 정상이다. 검수자 선정, 법률/시행령/시행규칙·시대별 층화, hard negative 라벨링, dev/test 분할은 미완료다. Neo4j 승인 상태와 채팅 검색 경로는 바꾸지 않았다.

## 2026-09-25 과거 Knowledge Graph 전수 적재 이후 남은 검수

- `scripts/sync_tax_knowledge.py all` 미처리 0, `audit` 5,400/5,400 및 노드 6,924,423/6,924,423·고유 관계 1,313,901/1,313,901 일치. 중복 참조 101개 스냅샷의 1,734개 구조 단위는 순서 식별자로 분리했다. 새 자료를 수집하면 `all --apply`로 추가분만 재개하고 `audit`/`validate`를 다시 실행한다.
- 당시 보고된 버전 3162·3163 제125조의 XML/본문 불일치 2건은 위 2026-09-26 조사에서 검수기 오탐으로 해결됐다. 원본/색인 재생성은 필요하지 않다. 같은 번호의 개정 지시문과 본문 조문은 계속 공존하므로 임의의 조문 선택이나 자동 관계 승인은 금지한다.
- 후보 1,313,898개는 기계적 원문 추출 결과일 뿐 법률 전문가의 관계 의미·사건 적용시점 검수는 안 됐다. 승인 3개만 과거 RAG에 사용한다. 검수자 인증·이중검수와 관계 정답셋 평가가 다음 단계다. 일반 현행 채팅은 기존 CITES 그래프를 사용한다.

## 2026-09-25 버전별 Knowledge Graph 시범 단계 후속 — 전수 적재 항목은 위 결과로 대체

- 구현·시범 적용 범위와 검수 명령은 `docs/TAX_KNOWLEDGE_GRAPH.md`. 소득세법 버전 306 `제1조의2`에서 3개 관계를 원문 일치 검수했다. 나머지 버전은 위의 전수 적재로 후보 생성까지 완료됐지만, 이를 전체 법령 관계의 법적 검수 완료라고 표시하면 안 된다.
- 과거법령 전 범위의 조·항·호·목 적재와 체크포인트는 위에서 완료했다. 검수자 권한/이중검수, 누락·오탐 계량, 정의 문형 확장, 관계 골든셋 평가는 미완료다.
- 현행 `law_articles` 일부에서 역사 XML 대비 항·호 본문 누락 또는 갱신 시점 차이가 확인됐다. 현행 원문 동기화·개정 시점 정합성 검수 후에만 검수된 Knowledge Graph를 일반 채팅에 확대한다. 지금 일반 채팅은 기존 CITES GraphRAG다.
- 최신 backend 이미지 전체 테스트 682 passed/2 skipped. 시범 과거법령 조회에서 정의·인용 근거 추가를 확인했지만 실제 세무 정답률 검증은 아니다.

## 2026-09-25 AI 작업별 설정 후속

- 6개 작업은 기본 OpenRouter Luna. 각 작업은 `LLM_TASK_<NAME>_*`로 독립 전환 가능하며 예시는 README와 `.env.example`에 있다. 기존 `ROUTING_LLM_*`는 더 이상 사용하지 않는다.
- 실제 세무 골든셋에서 작업별 reasoning effort·모델 변경의 도구 선택 정확도, 검색 Recall, 인용 정확도, 지연, 비용을 비교한다. 합성 스모크는 도구 선택·검색어 형식만 확인한다.
- LangSmith 월간 추적 할당량 429는 별개 문제로 남아 있다.
- 최신 backend 이미지 전체 676 passed/2 skipped, 6개 작업 상태 ok 확인. 실제 세무 답변 품질의 전후 비교는 아직 미실시다.

## 2026-09-25 채팅 모델 역할 분리 후속 검증

- `dev/probe_chat_routing.py`는 비식별 합성 질문의 smoke test일 뿐이다. 실제 세무·법령 질의 골든셋에서 Luna 단일 모델과 nano routing의 도구 선택 정확도, 검색 Recall, 지연시간, 비용을 비교한다.
- 당시 `ROUTING_LLM_*` 옵션은 ADR-043 작업별 설정으로 대체됐다. 현재 로컬 도구 선택은 `LLM_TASK_TOOL_SELECTION_PROVIDER=ollama`와 `LLM_TASK_TOOL_SELECTION_MODEL=qwen3.5:9b`로 설정한다.
- LangSmith 월간 추적 한도 429는 별도로 해결해야 하며, routing 점검 스크립트는 추적을 끄고 수행한다.
- 분리 배포 후 backend 전체 테스트 666 passed/2 skipped, 두 LLM 상태 ok를 확인했다. 프런트엔드 실사용 전 과정의 품질 비교는 미실시다.

## 2026-09-25 장문 이어쓰기·실서비스 LangSmith 추적

- 생성 출력 `length` 이후 원문·근거를 유지한 최대 2회 이어쓰기 및 반복 방지 구현. 완결 후 인용/계산 검증·저장, 미완료는 저장하지 않는다. 일반·SSE·재생성 공통이며 Nginx 900초 read timeout을 배포했다.
- Compose 실서비스의 `CHAT_TRACING_ENABLED=true`, LangSmith 루트 채팅 추적과 하위 단계 전송을 설정했다. SDK 스트림 장식자가 연결 종료 시 검색 작업 취소를 막아 명시적 trace 문맥으로 교체했다.
- 최신 이미지 pytest 661 passed/2 skipped. LangSmith 합성 trace 전송/읽기 검사는 계정 월간 unique traces 초과 HTTP 429로 원격 저장 실패. 키·프로젝트·tracing 설정은 적용됐으며 한도 복구 또는 증액 전에는 새 추적이 LangSmith 이력에 보이지 않는다. 재확인: `docker exec tax_backend python -m dev.probe_langsmith_chat`. 실패 중 생성된 추적의 자동 재전송은 없다.

## 2026-09-25 유료 생성 안정화

- 목적별 추론/출력 예산, 제한적인 HTTP 429 재시도, deadline, 안전한 API 오류, 숫자 usage 로그, 단일 조문 선택 우회, 일반 후속 질문 오탐 완화, Compose tracing opt-in을 구현했다. 기존 DB·벡터·대화 버전 기능은 보존했다.
- 실제 Luna 호환성 검사 6종(일반/stream/JSON/도구 인자/인용 스키마/과거법령 스키마)은 합성 입력으로 성공했다. 세무 판단·계산 정답률이나 실제 사용자 UI 전체 시나리오를 검증한 것은 아니다.
- 최종 WSL 최신 backend 이미지: 652 passed/2 skipped, backend healthy 및 3002 dependencies ready. git diff --check 통과. LangSmith 자동 tracing 런타임 false/false를 확인했고 최종 테스트에서 월간 추적 한도 경고가 사라졌다.
- 남은 과제: 골든셋으로 법령 적용시점·인용·계산 품질 평가, 질문당/사용자당 비용·동시 요청 제한, 민감정보의 OpenRouter 전송 정책, 혼합 의도 및 tool=none(불필요/입력부족) 분리. 긴 맥락은 입력 토큰 예산을 별도로 설계해야 한다.
- 재검증: WSL 가상환경에서 dev/docker-up-wsl.sh backend → docker exec tax_backend pytest -q. 유료 스키마 점검은 docker exec tax_backend python -m dev.probe_openrouter_model openai/gpt-6-luna --pipeline.

## 2026-09-25 GPT-6 Luna 생성 전환

- 실제 `.env`와 예시 설정을 `openai/gpt-6-luna`로 변경하고 Luna 전용 요청 파라미터 및 회귀 테스트를 추가했다. 기존 대화·법령 DB는 변경하지 않았다.
- 비식별 일반/JSON Schema/스트리밍 API 실호출은 모두 성공했고 WSL backend 재빌드·health 확인 및 전체 632 passed/2 skipped를 완료했다. 후속: 세무 골든셋 인용·계산 품질, 요청당 비용과 장기 429 발생률을 확인한다. 개인 세무 서류 외부 전송 정책은 별도 검토가 필요하다. LangSmith 월간 추적 한도 429는 별도 이슈다.

## 2026-09-25 Qwen3.8 무료 모델 사용자 직접 실험

- 로컬 `.env`에서만 Qwen3.8 27B 무료 생성 모델을 선택하고 WSL backend 재빌드·재시작 완료. 실행 컨테이너 설정 일치·health 확인. `.env.example`/운영 권장 모델은 변경하지 않았다.
- 직전 비식별 실호출은 일반/스트리밍/구조화 모두 429였으며 이번 턴은 사용자 직접 채팅 실험을 위해 설정만 전환했다. 별도 실제 생성 호출은 하지 않았다. fallback 없음.

## 2026-09-25 재생성 오류와 Gemma 무료 모델 실험

- 재생성 저장 시 발생한 `get_pool` 지역 변수 충돌을 수정하고 스트림 최종 커밋 회귀 테스트를 추가했다. 일반·재생성 SSE의 미처리 예외는 안전한 오류 이벤트로 전달한다.
- Gemma 4 26B-A4B 무료 엔드포인트 실호출 결과 일반/스트리밍 429, 엄격한 JSON Schema 404. `CHAT_MODEL`은 Dots3로 유지. 무료 모델 한도·구조화 출력 지원 변화 시 비식별 재검증 필요.
- WSL `dev/docker-up-wsl.sh backend`로 재배포, 백엔드·프런트엔드 health 및 Alembic head 확인. 최신 이미지 전체 631 passed/2 skipped. 실제 사용자 대화의 재생성 버튼은 별도 수동 확인이 가능하며, 자동 테스트는 합성 데이터로 동작한다.

## 2026-09-25 동일 대화 답변 버전

- `20260925_0005_answer_versions` 마이그레이션, 마지막 답변 재생성 SSE/버전 선택 API 및 UI를 추가했다. 마지막 질문 수정은 기존 분기 방식 유지.
- 새 모델 출력의 정답성 자체는 이 기능으로 검증하지 않는다. 후속 질문이 이미 작성된 턴의 버전 전환은 의도적으로 지원하지 않는다.
- 백엔드 628 passed/2 skipped, 프런트엔드 14 passed/빌드 및 합성 API Edge 브라우저 통과. 실제 OpenRouter 생성·실제 계정 UI의 수동 클릭 검증은 별도이며 이번 자동 검증은 생성 모델의 답변 품질을 뜻하지 않는다.

## 2026-09-25 내 정보 화면 수정

- `ProfileScreen.jsx`의 세로 flex 카드 축소/내용 잘림을 고치고 `profile.css`로 공통 UI 스타일에 맞췄다. WSL Compose 재빌드 완료.
- `frontend/tests/profile.browser.cjs`는 합성 API로 데스크톱/모바일 카드 가시성, 가로 넘침, 프로필 저장, 비밀번호 변경을 검증하며 Edge headless에서 통과했다. 실제 계정 데이터는 변경하지 않았다. 프런트엔드 14 passed/빌드 성공, 백엔드 623 passed/2 skipped.

## 2026-09-25 채팅 액션 아이콘·공유

- 사용자 마지막 질문의 수정, AI 마지막 답변의 재생성을 아이콘 버튼으로 정리하고 완료된 각 답변에 공유 아이콘을 추가했다. Web Share API 미지원 시 텍스트 복사이며 공유 URL·서버 저장은 없다. 프런트엔드 테스트 14 passed/빌드 성공/재배포 완료. 합성 브라우저 테스트 코드는 수정했지만 Playwright 패키지가 로컬에 없어 실제 브라우저 실행은 후속 확인이 필요하다.

## 2026-09-25 출처 제목 교정 후속 검증

- 일반·스트리밍 채팅의 현행 법령 출처 제목을 DB 원문으로 교정하도록 변경했다. Dots3가 생성하는 제목의 오탈자 사례를 재현하는 테스트와 SSE `replace` 처리 테스트가 있다. 재빌드 후 백엔드 623 passed/2 skipped, 프런트엔드 13 passed이며 컨테이너에서 실제 소득세법 제101조 제목 교정도 확인했다.
- 실제 사용자 질문의 답변·인용 정확도는 아직 검수되지 않았다. 재배포 후 생성 출처의 제목·법령명·조문번호 및 과거 법령 경로를 샘플 검수한다. 스트리밍에서는 교정 직전의 생성 문구가 잠시 보일 수 있다.

## 2026-09-25 Dots3 무료 모델 활성화 — 세무 품질 미검증

- `.env`/`.env.example` 생성 모델을 `dots-studio/dots-3-note-preview:free`로 변경하고 backend 재빌드·재기동. health ready, 일반·JSON Schema·SSE 비식별 실호출 성공, 최신 Docker 전체 pytest 619 passed/2 skipped.
- Qwen3.8 무료 엔드포인트는 ModelRun upstream 공유 처리량 429로 중단된 이력. Dots3는 현재 연결되지만 무료 Preview 모델이라 장기 가용성·한국어 세무 답변/인용 정확도는 별도 골든셋/전문가 검수가 필요하다.

## 2026-09-25 Qwen3.8 27B 무료 모델 고정 후 실제 생성 제한

- `.env`/`.env.example` `CHAT_MODEL=qwen/qwen3.8-27b:free`; backend 재빌드·재기동 완료. health 카탈로그 조회 ok, Ollama 임베딩 ok.
- 실제 비식별 생성은 OpenRouter HTTP 429 `Provider returned error`. 오류 메타데이터는 ModelRun upstream의 `qwen/qwen3.8-27b:free` 일시 rate limit이라고 명시했다. 인증 키 조회 200/무료 계정 확인. 유료 모델이나 다른 무료 모델로 자동 fallback하지 않았다.
- 무료 제한이 풀린 뒤 일반·JSON Schema·SSE 실제 호출을 재검증하고, 그 다음 세무 검색/인용 품질을 평가해야 한다. 지금 사용 가능하다고 표시하지 말 것. 최신 컨테이너 pytest 619 passed/2 skipped.

## 2026-09-25 OpenRouter 무료 생성 배포 완료 — 품질 평가 필요

- 사용자 키 입력 후 최신 backend 재빌드·기동. health에서 생성 `openrouter/free`/임베딩 `ollama` 모두 ok. 비식별 일반·구조화·SSE 생성 스모크 통과. 최신 이미지 전체 테스트 619 passed/2 skipped.
- 요청마다 무료 모델이 달라지고 초기 구조화 응답에서 빈/비JSON 사례가 관찰됐다. `require_parameters`와 형식 오류 1회 재시도 추가 후 스모크는 통과했지만 지속 안정성은 아직 미검증이다. 무료 요청 한도/429와 실제 세무 답변의 근거·인용 품질을 평가해야 한다.
- 실제 키는 `.env`에만 있으며 출력·커밋 금지. 개인정보가 포함된 사용자 질문은 외부 제공자 데이터 정책 검토 전 테스트하지 않는다.

## 2026-09-25 OpenRouter 무료 모델 연결 — 사용자 키 대기

- `.env`/`.env.example`은 OpenRouter 무료 라우터를 생성 provider로 선택했으나 `OPENROUTER_API_KEY`는 비어 있다. 사용자만 실제 `.env`에 키를 입력한다. 기존 Docker 컨테이너는 재배포하지 않았으므로 지금 웹 서비스는 여전히 이전 Ollama 구성이다.
- 키 입력 후 WSL `venv-wsl` 활성화 → `bash dev/docker-up-wsl.sh backend` → `/api/health/dependencies` 확인 → 비식별 질문으로 일반/구조화/SSE 실제 호출 테스트. 무료 한도/429, JSON Schema 호환, 스트리밍 완료, 인용 품질을 기록할 것. 테스트용 질문에 실제 개인정보를 포함하지 않는다.
- `openrouter/free`는 모델이 고정되지 않아 재현 가능한 법률 품질 평가에는 부적절할 수 있다. 결과 비교 시 응답 모델 ID를 별도 기록하거나 고정 `:free` 모델을 선택하고 다시 평가한다.

## 2026-09-25 `num_ctx=8192` 임시 실험 후 4,096 복구

- 동일 비식별 복합 질문 실제 파이프라인에서 8,192 입력 3,815/출력 1,220토큰, `done_reason=stop`, 23.8초로 생성 완료. 4,096에서는 입력 3,815/출력 281에서 `length` 중단했다.
- 8,192 완료 직후 두 모델 모두 100% GPU였으나 VRAM 여유는 120MiB뿐. 답변이 요청 제59조의4와 하위법령 대신 다른 소득세법 조문으로 이탈했다. 생성 완료를 법적 정확성으로 해석하지 말 것. 반복·동시 요청/OOM 평가 없이 기본값을 8,192로 전환하지 않는다.
- 실험용 프로세스만 설정을 바꿨고 `.env`/Compose/DB는 보존. 종료 후 Ollama에 4,096 요청을 보내 `ollama ps`에서 4,096 복구를 확인했다. 다음 우선순위는 다법령 근거 검색과 필수 조문 우선 프롬프트 예산, 그다음 단계적 컨텍스트 성능 실험이다.

## 2026-09-25 실제 복합 질문 중단 재현

- 실제 Ollama+DB+검색 채팅 스트리밍(저장·웹·LangSmith 차단)에서 소득세법 제59조의4 제1항 제1호 및 관련 하위법령 비교 질문이 입력 3,815 + 출력 281 = 컨텍스트 4,096토큰에 도달해 `done_reason=length`로 중단됐다. 수정된 어댑터가 실패로 표시하고 미완성 답변을 저장하지 않았다.
- 검색 근거는 5건·4,326자이고 모두 소득세법이었다. 요청한 시행령·시행규칙은 입력에 없었다. 종료 원인과 근거 부족을 별도 결함으로 다룰 것. 시스템 프롬프트 2,300자도 예산에 포함된다.
- 다음 구현은 검색 결과 전체 5건을 그대로 프롬프트에 넣는 경로의 토큰 예산과 위계/필수 근거 우선 선택. 법적 조건을 문장 중간에서 자르는 단순 문자열 절삭은 피하고, 불가 시 명시적 유보. 실제 사용자 질문을 받으면 별도로 재현해 비교할 것.

## 2026-09-25 복합 질문 답변 중단 — 종료 사유 검출 추가

- Ollama 생성 어댑터가 `done_reason`과 토큰 수를 기록하고 `length` 등 미완료를 예외로 전환한다. 채팅 라우터는 스트리밍 오류 이벤트(정상 `[DONE]` 없음), 비스트리밍 502를 반환한다. 미완료 일부 출력은 저장하지 않는다.
- 강제 짧은 출력의 실제 Ollama 요청에서 `done_reason=length`를 확인했다. 사용자가 겪은 원인과 동일하다는 증거는 아직 없다. 사용자 재현 질문으로 `Ollama completion` 로그의 `reason`, `prompt_tokens`, `output_tokens`를 확인해야 한다. 민감한 질문·답변 원문은 진단 로그에 넣지 말 것.
- 다음 작업: 4,096토큰 내에서 필수 법령/질문 우선 입력 예산과 답변 여유를 계측·평가한다. 단순히 컨텍스트를 올리면 12GB GPU 공존 설정이 깨질 수 있다. GPT/Claude 교체 여부는 이 오류와 분리해 평가한다.
- Ollama backend 이미지 재빌드·healthy 확인, 최신 이미지 전체 pytest 612 passed/2 skipped(추적 비활성), 프런트엔드 12 passed. 첫 Docker 전체 pytest에서 기존 LangSmith 추적 설정이 원격 429를 출력했으므로 추후 테스트는 `LANGCHAIN_TRACING_V2=false` 등으로 외부 추적을 끄고 수행해야 한다. 평가 업로드를 테스트 성공으로 간주하지 말 것.

## 2026-09-25 결함 6건 수정 완료 — 품질 평가는 후속

- `history_context.py`: 의도/시점 라우팅과 서버 메타데이터 상속. `history_structure.py`: 보존 XML의 정확한 항·호·목 추출. `history_search.py`: 버전 소속 대조/질문 범위 Graph 인용. `history_answer.py`: 필수 근거 예산/생성·검증 상태.
- backend/frontend 최신 배포. 전체 595 passed/2 skipped, frontend 8 passed/build, healthy/HTTP 200 확인. `tests/test_history_runtime_regressions.py` 34개 사례. 원본 데이터·127,838개 임베딩·Graph 재작성 없음.
- 실제 모델은 구법 제2조 인용을 바꿔 실패하기도 했고 이제 error로 정확히 표시된다. 실패를 숨기거나 검증을 약화하지 말 것. 구법 후속 질문은 올바른 529 버전/1949-07-15를 유지했다. 추가 모델 인용 재현율 및 전문가 법률 검수가 필요하다.
- 계산기 스키마에는 tax_year가 없다. 연도 질문이 역사 경로에 잘못 진입하는 문제만 해결됐으며, 연도별 세율/공제 자동 적용을 주장하면 안 된다. 별도 적용연도 규격/검증 작업 필요.
- 모델별 전체 토큰 예산·긴 항 처리·다중 의도/법령 비교·구조 메타데이터 없는 옛 대화의 자동 복원은 후속. 지금은 모호하면 재확인을 요청한다.
- 상세 검증/한계: `docs/evaluation/2026-09-25-history-runtime-fixes.md`. 아래 미수정 기록은 이전 관측 이력이다.

## 2026-09-25 런타임 리뷰 — 수정 전 결함 기록

- 읽기 전용 재현으로 연도만 있는 계산/문서 질문의 역사 경로 오분기, 과거 법령 후속 질문의 일반 검색 진입, 명시 버전/법령명 충돌 무시를 확인했다.
- 과거 본문 `①\n①` 중복: 고유 본문 53,466개, 발생 행 583,010개. 버전 309 제59조의4 제1항 조회가 `①`만 선택하고 존재하는 제1호를 없다고 처리한다.
- 같은 조의 항 질문에서 10,000-byte 예산으로 질문 대상 조문이 빠지고 조세특례제한법 그래프 근거 2개만 남는 동작도 확인했다. 생성 실패 주입 시 최종 도구 상태가 ok인 문제 포함.
- 제품 코드/DB는 수정하지 않았다. 상세 재현/개선 순서: `docs/evaluation/2026-09-25-history-runtime-review.md`. 관련 기존 테스트 31개는 통과했으므로 이 사례들을 회귀 테스트에 추가해야 한다.

## 2026-09-25 임베딩 완료 후 검증

- DB 저장 127,838/127,838, 실패 0. 전수 Neo4j 감사 5,400/5,400 및 관련 회귀 테스트 31 passed.
- 실제 의미 검색 소규모 진단 3/3, 유보 2/2, GraphRAG 채팅 스모크 통과. 진단 코드 `evaluation/history_retrieval_pilot.py`, 결과 해석은 `docs/evaluation/2026-09-25-history-embedding-validation.md`.
- 독립 검수한 다법령·다시점 정답셋, hard negative, 인간 법적 적용 검수는 아직 필요하다. 위 3건을 전체 검색 품질이나 세무 정답률로 해석하지 않는다.

## 2026-09-25 과거 법령 임베딩 완료 — 후속 평가 필요

- 최종 DB 상태: 청크 127,838/127,838 임베딩, 실패 0, 미준비 0, History* 그래프 5,400/5,400. indexer 최종 종료 코드 0.
- 이전에 기록된 `ReadTimeout` 실패 8개는 `embed --retry-failed --limit 8`로 재처리해 해결했다. 아래의 4개 실패/진행 중 수치는 과거 관측 이력이다.
- 다음 작업: 여러 연도·동일 시행일 모호성·부칙/hard negative 검색 평가, 법적 적용 시점 및 답변 검수. 전체 벡터 완료를 정답률 검증으로 해석하지 않는다.

## 2026-09-24 임베딩 일시 정지 진단 및 재개 확인

- 배치의 마지막 오류는 `ReadTimeout` 4개였다. 작업 프로세스는 한 차례 종료됐으나 컨테이너가 재기동했고, DB 임베딩이 20,532 → 20,632/127,838로 증가하는 것을 확인했다. 현재 실패 4개.
- 진행 중인 worker를 중복 실행하지 않는다. 나머지 완료 후 worker 종료/락 해제를 확인하고 `python scripts/index_law_history.py embed --retry-failed --limit 4` 등으로 실패 4개를 재처리한 뒤 `failed=0`, `embedded=chunks` 검수 필요. 재시도 전에 Ollama 지연 원인을 점검한다.

## 2026-09-24 사용자 요청으로 임베딩 재개

- `bash dev/history-index-wsl.sh start` 실행 후 컨테이너 running 확인. 저장량 10,292 → 10,320/127,838로 증가, 실패 0.
- 전체 백필 진행 중. 최신 수치는 `bash dev/history-index-wsl.sh status`로 확인하고, 완료는 chunks=embedded/failed=0/unprepared=0 및 배치 종료로 판정한다.

## 2026-09-24 사용자 요청으로 임베딩 중지

- PC 종료를 위해 `bash dev/history-index-wsl.sh stop` 실행. 컨테이너 `exited`, `running=false` 확인.
- 중지 후 DB: 10,292/127,838 청크 임베딩 저장, 실패 0. 원본 및 Graph 5,400개 보존. 전체 임베딩 미완료.
- 사용자가 재개를 요청하면 Docker/DB 실행 상태 확인 후 `bash dev/history-index-wsl.sh start`로 남은 작업 재개. 임의 자동 재개하지 않는다.

## 2026-09-24 과거 법령 GraphRAG — 백필 완료 추적 필요

- 서비스/Graph 적재/전수 소속 검수는 완료. 전체 벡터는 6,224/127,838에서 진행 중, 실패 0. tax_law_history_indexer를 최신 코드로 재개했고 docker wait로 WSL 연결을 유지했다. PC/WSL 종료 후 dev/history-index-wsl.sh start 필요.
- `bash dev/history-index-wsl.sh status`의 chunks=embedded, failed=0, unprepared=0 및 종료 코드를 확인해야 백필 완료다. 성공으로 미리 표시하지 말 것. 모델 tag 내부 가중치를 바꾸면 색인 규격 버전도 올리고 재색인한다.
- 5,400 Neo4j snapshot audit 통과/MENTIONS 86,552. docs/HISTORY_RAG.md에 구현/실험/한계 기록. 생성 및 벡터 검색은 소수 스모크이며 전체 정답률 평가 아님.
- backend/frontend 재배포로 과거 조회 및 이전 조회 실패 유보 코드도 실행 이미지에 반영됨. 전체 561 passed/2 skipped, frontend 8 passed. 역사 답변은 현행 뷰어 대신 공식 MST+efYd 링크를 사용한다.
- 다음: 전체 임베딩 완료/오류 점검 → 여러 연도·동일 시행일 모호성·부칙/hard negative 평가 → 법적 적용 검수. 현행 Graph 설정은 유지하고 HISTORY_GRAPH_RAG_ENABLED만 true로 활성화했다.

## 2026-09-24 독립 수집기 및 전수 검수 완료

- **최종 상태**: 5,400/5,400, pending/failed=0. 전수 검수 passed=true, 공식 표본 3개 일치, 컨테이너 정상 종료 0. 추가 수집 2,502개. docs/evaluation/2026-09-24-law-history-recovery.md 및 JSON 참고. 아래 3,284는 진행 중 관측 이력이다.
- 다음 작업: 동일 시행일 복수 버전 474묶음 및 부칙/사건 기준일 적용 검수, 구법 검색·Graph 연계 설계. 수집 완료를 법적 적용 정확도 인증으로 해석하지 말 것. 현행 검색/Neo4j에는 아직 구법 미반영.

- 사용자 승인으로 미수집 2,502개 재개. tax_law_history_worker가 수집 후 자동 전수 검수까지 실행한다. 최신 관측 3,284/5,400, 실패 0. API/현행 검색/Neo4j 변경 없음.
- bash dev/law-history-wsl.sh status 및 logs, evaluation/runs/law-history/audit-*.json 확인. 보고서 passed=true + 전체 coverage + 컨테이너 exit 0을 함께 확인해야 완료.
- 543 passed/2 skipped. 독립 worker 재생성 후 정상 이어받기 실증. PC/WSL 종료 후에는 start 명시 재실행 필요; 실패 데이터는 자동 무한 재시도하지 않는다.

## 2026-09-23 검수 결과 — 수집 재개 필요

- 실제 수집 중단 확인: 2,898/5,400 저장, pending 2,502, 실패 0. run 4는 running으로 남았지만 마지막 heartbeat 9/22 21:10 KST, 수집 프로세스 없음. 이번 요청은 검수이므로 재개하지 않음.
- 저장 원문 전체 무결성 및 법/영/규칙 표본 3건 공식 원문 대조 통과. 동일 시행일 복수 버전 474묶음의 적용 의미는 미검증. docs/evaluation/2026-09-23-law-history-audit.md 참고.
- 다음: 사용자 지시에 따라 collect 재개, 완료 후 재검수. 구법 채팅/Graph 연결은 아직 불가. DB 수정·API 재배포 없음.

## 2026-09-22 판단 유보 구현 — 활성화 대기

- app/services/chat_service.py _failed_tool_answer: 법령/문서 도구 실패 시 고정 안내로 최종 생성 차단. 일반/SSE, 저장 도구 상태 유지. tests/test_lookup_abstention.py 22개 추가, 전체 526 passed/2 skipped.
- 수집 worker를 유지하려고 tax_backend 재시작하지 않음. 변경 파일 복사 후 별도 pytest 프로세스로 검증했으나 현재 API 프로세스에는 미활성화. 수집 완료 후 dev/docker-up-wsl.sh backend로 재배포하고 실제 질문 확인 필요.
- 일반 검색 빈 결과, 구법 버전 적용 확인, Judge 교정은 이번 변경 범위 아님. 수집 마지막 확인 1,574/5,400, 실패 0; 실제 최신 상태를 재조회할 것.

## 2026-09-22 과거 법령 수집 진행 중

- law_history 스키마와 20260922_0003 적용, 41개 대상/5,400개 목록 확보. 본문 전체 수집은 진행 중이며 status를 실제 조회할 것.
- Windows 숨김 wsl 프로세스로 `docker exec tax_backend python scripts/collect_law_history.py collect` 실행. stdout history-collection.20260922.log, stderr history-collection.20260922.error.log (Git/Docker 제외). WSL 유지용 전경 docker exec이며 PC/WSL/컨테이너 재시작 때 자동 복구하지 않는다.
- 중복 작업은 DB advisory lock 차단. 중단 후 같은 collect로 미수집 재개, 실패는 collect --retry-failed. 기존 실행 running 표시만으로 살아 있다고 간주하지 말고 heartbeat/프로세스도 확인.
- 전체 504 passed/2 skipped, DB 멱등·정정 스냅샷·시점 불일치 rollback 검증, 1949-07-15 소득세법 원문 저장 성공. 채팅/임베딩/Neo4j에는 미반영.
- 후속: 수집 완료/실패 사유·원문 품질 감사 → 부칙/조문 시점 검수 → 구법 임베딩/과거 Graph 투영. 법령 ID가 바뀐 전신/후신 연결, 별표 첨부 다운로드는 미구현.

## 2026-09-22 검수 자료 열기

- evaluation/sources/precedents/2026-09-20-pilot/검수자료.html을 브라우저로 열면 수집 10건과 미승인 기준 5건을 함께 볼 수 있다. 읽기 전용이며 메모 저장/승인 UI는 없다.
- 재생성은 python -m evaluation.precedent_review --batch BATCH. 기존 HTML은 덮어쓰지 않는다. 원본에 비해 HTML 태그만 제거한 텍스트 표시이므로 원문 서식은 공식 출처에서 확인한다.

## 2026-09-20 판례 후보

- evaluation/sources/precedents/2026-09-20-pilot/README.md와 draft-cards.json부터 검수. 10건 원문/5건 초안, 운영 DB 적재 없음. sources 전체 Git/Docker 제외.
- 초안 선정 ID: 623075/619463/622927/621977/622257. 판시사항·요지 중심이므로 실제 사실관계 정리, 구법 적용 범위, 상급심/후속심 연결, hard negative 구체화 후 승인 필요.
- 최신순 제한 표본으로 대표성 없음. 민사 후보 2건은 제외 삭제하지 않고 보존. API 인증값은 .env에서 읽고 출력/저장 금지.

## 마지막 턴 재생성/수정

- chat_revision_service.py + conversations/{id}/revise, ChatArea/MessageBubble 연결 및 Docker 반영 완료. 원본 대화 유지/별도 대화 생성 방식이다.
- 490 backend/8 frontend tests, Edge 합성 브라우저, 실제 PG rollback 검증 완료. frontend/tests/revisions.browser.cjs는 PLAYWRIGHT_MODULE 지정 후 실행 가능.
- 서버 idempotency/다중 탭 중복 생성 차단, 중간 턴 수정, 버전 탐색 UI는 미구현. 새 분기 생성 뒤 답변 실패하면 빈 분기/복사 문맥이 남을 수 있고 원본은 보존된다.

## Judge 증거 오류 수정 완료

- 최신 judge schema 1.1/evidence_policy_version 1. A/R ID 기반, 일반 paired/특정 합성 행동 기준 behavioral. 형식 오류만 한 번 재평가.
- judge-evidence-ids-01은 같은 저장 답변 3항목 모두 pass, 이전 2개 발췌 오류 해소. 인간/독립 모델 교정 완료가 아님. 관련 테스트 43 passed.
- 신규 행동 항목 정책은 현재 호환 함수 evidence_policy를 명시적으로 확장해야 한다. 법적 기준의 원문 필수 조건을 일괄 해제하지 말 것. 전체 5개 법령 카드는 여전히 미승인이다.

## LLM Judge 초기 구현

- scripts/evaluate.py judge --run-dir RUN --output NEW_DIR로 저장된 고정 컨텍스트 답변 평가 가능. local judge.json/md만 생성, 인간 판정/원래 gate는 그대로다.
- 실제 첫 대상은 answer-ready-verified의 정보 부족 응답 1개다. 전체 GraphRAG/법령 정확도 평가로 소개하지 않는다. 5개 pilot은 draft라 unknown을 유지한다.
- LangSmith feedback 연계, 독립 Judge 모델/가중치 digest, 공식 카드 승인 및 전체 채팅 A/B는 후속. 동일 로컬 모델 자원 경합·자기평가 편향 주의.

## 다음 작업: 평가 기준 카드 검수

- evaluation/QUALITY_CRITERIA.md와 datasets/answer_pilot.json의 5개 초안을 검수한다. 공식 원문 버전·발췌·귀속기간·부칙과 hard negative의 정확한 조항을 확보한 후 승인할 것.
- input.review_card.calibration_examples는 모델 교정용 초안이지 기존 counterexamples 자동 통과 자료가 아니다. Judge 결과 스키마/실행기는 아직 미구현, 인간 Adjudication과 분리해야 한다.
- 5개 전수 검수 후 20개로 확대하고 실제 답변 관측·Judge 교정·LangSmith 항목별 업로드 연결 순으로 진행한다.

## 2026-09-19 GraphRAG 로컬 채팅 활성화

- LLM Judge는 사용자 우선순위 변경으로 미구현/보류. 로컬 GRAPH_RAG_ENABLED=true, Ollama 유지. 일반 채팅 검색에 기존 그래프 확장을 활성화했다. 관계도 UI는 없다.
- 실제 Nginx/SSE 질문에서 base=5 added=2 및 답변/대화 저장 확인. 법적 정답률 검증이 아니며 답변의 조건 누락·잘못된 설명은 별도 검수 대상이다. 모델 답변을 세무 정답으로 문서화하지 말 것.
- WSL이 마지막 foreground 프로세스 종료 뒤 자동 종료될 수 있다. 재기동 직후 Neo4j가 준비되지 않으면 안전하게 기본 RAG로 돌아간다. 서비스를 확인할 때 WSL 터미널을 유지하고 Neo4j 준비 상태도 확인한다.
- 테스트 계정 graph-smoke-* 3개와 각 대화는 보존. 첫 질문은 stdin 인코딩 손상으로 무효, 두 번째는 기동 중 fallback, 세 번째만 그래프 추가 근거 확인 사례다. 기존 사용자 데이터/법령/벡터는 수정하지 않았다.
- 롤백: 로컬 .env GRAPH_RAG_ENABLED=false 후 bash dev/docker-up-wsl.sh backend. .env.example에는 실제 키가 있으므로 내용/diff 출력 금지.

## 2026-09-19 키 입력 파일 최종 변경

- 사용자 명시 요청으로 .env.example의 LANGSMITH_API_KEY를 publish에서 읽는다. .env.langsmith와 evaluation/langsmith.env.example은 삭제했다. 아래 이전 키 위치 안내보다 이 항목을 우선한다.
- .env.example에는 실제 키가 있으므로 내용/diff를 출력하지 말 것. Docker 빌드에서 제외했지만 Git 추적 파일이므로 실제 키를 커밋하면 안 된다. 자동 추적·평가 업로드는 별도 명시 동의 경계를 유지한다.

## 2026-09-19 LangSmith 전환 인계

- 현재 명령은 scripts/evaluate.py langsmith prepare/publish. 자체 dashboard 소스·실행기 제거, 포트 8765 종료. 아래 UI 실행 지침은 당시 이력이다. runs/reviews는 삭제하지 않았다. 제거한 UI는 미추적 파일이었으므로 Git에서 복구할 수 없으며 캐시 디렉터리는 정책상 삭제 거부로 남을 수 있다.
- .env.langsmith의 LANGSMITH_API_KEY는 빈 상태. 사용자가 직접 입력하고 계정 region을 확인해야 한다. 키를 출력하거나 서비스 .env/Compose에 넣지 말 것. production tracing은 활성화하지 않는다.
- 평가 결과 전송 계획 2개: evaluation/runs/langsmith-metrics-plan.json(본문 제외), langsmith-review-plan.json(본문 포함·검수 큐 요청). 실제 39문항 base/graph 78결과이며 uploaded=false. 사용자에게 내용을 확인받고 계획 hash를 publish --approved-sha256에 지정해야 한다. 아직 원격 전송 권한 확인/계정 성공 검증 없음.
- 최신 Docker 476 passed/2 skipped, 로컬 평가 45 passed. 새 테스트 9개는 SDK autospec 기반 mock이며 클라우드 성공으로 소개하지 않는다. 첫 공개/합성 데이터 전송과 실제 LangSmith UI 확인이 남았다.
- LangSmith는 저장된 artifact import이며 새 추론/실서비스 trace가 아니다. 기본 latency 대신 observed_elapsed_seconds를 볼 것. draft는 diagnostic 지표이고 로컬 gate는 그대로 유지한다.
- 원격 장애 시 receipt와 부분 생성 리소스를 확인한다. 자동 롤백/삭제하지 않는다. 원격 검수의 로컬 자동 동기화는 후속이며 현재 수동 규약 변환·재채점 필요. 상세 evaluation/LANGSMITH.md.

## 2026-09-19 로컬 평가 UI 인계 (과거 이력)

- WSL venv에서 python scripts/evaluation_dashboard.py → http://127.0.0.1:8765. 사용자 서비스와 별도이며 기본 배포 이미지/Compose에서 제외. 코드·데이터 삭제 없음.
- 검수 저장은 evaluation/reviews에 추가 전용 JSON. 원본 결과/정답셋/점수는 변경하지 않는다. 답변 JSON은 score --adjudications로 사용하고 근거 제안은 공식 검수 후 새 정답셋 버전으로 수동 반영할 것.
- 테스트: 로컬 평가/UI 44 passed, 서비스 Docker 467 passed/2 skipped, 실제 파일 기반 Edge 조회·필터·모바일 검사 통과. browser-check.cjs는 라벨을 저장하지 않는다.
- 남은 범위: 독립 전문가 라벨 승인, 실제 채팅 trace 수집, 대용량 목록 페이지네이션. 다중 사용자 인증/원격 접속/평가 실행 버튼은 의도적으로 구현하지 않았다. 단일 신뢰 PC에서만 사용하고 외부 프록시로 공개하지 말 것.

## 2026-09-19 실행 파일 정리 후 검증

- scripts/evaluate.py → evaluation/cli.py로 명령 처리를 분리하고 구 평가 stub 2개 삭제. 최신 Compose 이미지 일회성 컨테이너 전체 467 passed/2 skipped, 합성 22개 통과. 실행 중인 서비스는 재생성하지 않았으므로 변경된 CLI 사용 시 새 이미지로 실행할 것.
- 별도 무네트워크 컨테이너에서는 PDF 토크나이저 최초 다운로드가 실패했다. DB 설정 없는 독립 컨테이너에서는 계산기 API 2개 및 합성 평가 gate가 실패했다. Compose 환경에서는 통과했다. offline 합성 평가의 DB 스냅샷 의존성을 분리하는 후속 점검이 필요하며, 완전 무의존 CI 실행을 이번 결과로 보장하지 않는다.

## 2026-09-19 평가 시스템 인계

- 최종 Docker pytest 460 passed/2 skipped(기존 경고 26개), 합성 계약 22개 통과. scorer 1.1은 gold 미정의 사례를 오답이 아니라 incomplete로 처리한다. 다른 scorer 버전의 report는 compare가 거부한다.

- 새 진입점 scripts/evaluate.py, 구현은 evaluation/cli.py. evaluation/README.md를 먼저 읽을 것. 과거 eval_rag/eval_graph_rag 점수는 새 scorer와 직접 비교하지 않는다. 두 구 실행 파일은 제거했으며 원래 질문/결과는 보존했다.
- 실제 세무 라벨 승인자는 아직 없다. retrieval.json 39개는 모두 draft/dev, 제안 hard negative 6개도 재검수 대상. 기존 grounded=true를 승인 이력으로 승격하지 말 것.
- 우선 작업: evaluation/runs/retrieval-rescored/evidence_review_queue.json의 231개 후보를 공식 원문과 대조하여 필수·보조·무관·hard negative로 검수하고, 기준일/버전/검수자를 채울 것. 라벨 변경 시 버전·dataset hash가 바뀌므로 새 실행 필요.
- evaluation/runs/answer-ready-verified에 실제 모델 생성과 빈 인간 검수 양식이 있다. 인간 검수 없이 자동 pass로 바꾸지 말 것. outputs는 Git ignore되며 공유 전 비식별 확인 필요.
- 전체 채팅/컨텍스트/권한/성능 trace 자동 수집은 미구현. components.json의 recorded 계약에 관측을 넣어 score할 수 있지만 실제 계측 없이 기대 값을 관측으로 복사하면 안 된다.
- 라이브 검색은 ALL 또는 명시 입력 필터의 단일 쿼리 비교, 고정 컨텍스트 생성은 검색·웹·대화 저장과 분리된 평가다. E2E 품질 검증으로 소개하지 않는다.
- 합성 계약 CI만 연결했다. 실제 법령·기준일·예외·복합 근거 test셋과 검수자 간 일치도, 동일 토큰 예산 비교는 후속이다. GraphRAG 기본 false는 그대로 유지했다.
- source snapshot 초기 구현은 무관한 Neo4j 준비 상태가 계산 gate에 영향을 줬다. 현재는 검색/원문/계산 단계별 의존성만 해시하고 고정 컨텍스트/도구 선택은 DB를 요구하지 않도록 수정했다.

## 2026-09-19 GraphRAG 후속 작업

- 구현·동기화·검증 완료, 아직 채팅 확장 플래그 false. 아래 9/13의 설정 누락과 10개 실패는 복구됨. 최신 Docker 431 passed/2 skipped, 격리 통합 2 passed.
- 다음 우선순위: 법률/시행령/시행규칙 복합 질문별 필수 근거 집합을 별도 검수하고, 추가 근거 정밀도·동일 토큰 예산 재현율·실제 생성 인용 평가. 기존 38개 라벨은 기본 검색도 모두 성공하므로 추가 가치 측정에 부족하다.
- 남은 사례: inc-02 종합소득 기본공제 질문에 같은 계열의 양도소득 관련 시행령이 추가된다. 단순 키워드 필터의 한계이며 활성화 전에 해결해야 한다. 기본 RAG 자체의 긴 본문도 전체 컨텍스트 예산을 초과할 수 있다.
- 6,275개 미해결 참조는 자동 수집/수정하지 않았다. 특히 호 확인 실패 2,953, 항 확인 실패 124는 저장 원문과 공식 XML을 대조해 누락/버전/파서 문제를 분리해야 한다. 대규모 재수집은 범위 승인 후 진행.
- Graph 관계 UI와 독립 dependency 상태 API는 미구현. 원문 도구가 RAG를 생략하는 경로는 그래프 확장을 실행하지 않는다.
- scripts/eval_graph_rag.py는 stdout JSON Lines, DB 쓰기 없음. 전체 결과는 docs/evaluations/graph_rag_2026-09-19.json. docs/GRAPH_RAG_VALIDATION_2026-09-19.md에 실행·한계를 기록했다.
- 기존 추론 provider는 Ollama로 보존. 현재 Compose에는 OLLAMA_WINDOWS_IP 필수 extra_hosts가 남아 있으므로 WSL 스크립트 사용 또는 명시 export 필요. 과거의 셸 선택형 bootstrap은 이번 Graph 작업에서 재연결하지 않았다.
- WSL이 foreground 프로세스 없이 종료되는 환경에서 명령 사이 자동 재시작이 관찰됐다. Neo4j 준비 전 조회가 일시 실패했다가 준비 후 성공했다. 운영 시 WSL 유지/부팅 정책과 dependency 관측을 분리해 검토할 것.

## 2026-09-13 Neo4j 통합 테스트 인계

- 기존 dev 검증 스크립트를 tests/integration으로 이전/제거. WSL venv에서 python -m pytest -q tests/integration --run-neo4j --graph-real-sample: 2 passed. 옵션 없으면 2 skipped. 임시 컨테이너 잔존 0.
- 주의: 작업 시작 시 기존 tracked Graph 설정/Compose/수집 필터 변경이 사라지고 Graph 파일들만 untracked로 남아 있었다. 사용자 상태를 보존했으며 서비스 재빌드는 하지 않았다.
- 전체 로컬 테스트 10개 실패(414 passed): tests/test_graph_rag.py 7, test_graph_temporal.py 2, test_law_coverage.py 1. 대표 원인은 GRAPH_RAG_ENABLED/NEO4J_DATABASE 없음과 재정경제부 필터 미반영. 서비스 설정/현재 브랜치 의도를 확인한 뒤 별도 복구해야 한다.

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
# 2026-09-22 판례 실험 후속

- 판례 5건 실험 완료: evaluation/runs/precedent-pilot-20260922/report.md와 experiment.json. 분석은 docs/evaluation/2026-09-22-precedent-pilot.md. 원시 Judge pass 6/fail 3/error 1을 정답률로 쓰지 말 것(명백한 의미 판정 오류 존재).
- 법령 도구 invalid_arguments 2건/not_found 1건에서 일반 검색 없이 정상 생성으로 흘러감. chat_service.py의 법령/문서 tool_run 분기에서 실패 처리 구분 필요. 이번 요청은 평가이므로 서비스 수정은 하지 않음.
- 구법 질문에 현행 검색 자료가 섞임. 시점 버전 확인과 부족 시 유보, 전체 프롬프트 토큰 계측 필요. 컨테이너 GRAPH_RAG_ENABLED=false 관측(과거 문서 true와 다름), 설정 변경하지 않음.
- 현재 생성/Ollama 설정 보존. 평가 전용 assess diagnostic_draft 옵션은 인간 승인 변경 없이 허용하며 일반 CLI gate 유지. 실제 평가 모델도 Qwen3.5:9b여서 자기평가 편향. 별도 검수 및 반례 교정 필요.
- 관련 회귀 테스트 포함 backend 496 passed/2 skipped. 실험 원문/결과 외부 전송 없음. 컨테이너 /tmp/precedent-source와 /tmp/precedent-pilot-20260922에도 복사본이 남으며 호스트 결과는 보존됨.
# 국세청 공식 일정 캘린더 후속 검토 (2026-09-25)

- 국세청 공개 HTML 구조가 바뀌면 `/api/tax-schedule/official`이 503을 반환한다. 표 구조·연월 검증을 유지하며 파서를 수정하고, 장기 운영 시 페이지 변경 감시/알림을 추가한다.
- 현재 전체 공식 일정만 표시한다. 개인별 신고 의무 판정은 사업자 유형만으로 불가능하며 과세기간, 업종, 신고 구분, 성실신고 대상 여부 등 별도 검증된 프로필과 규칙이 필요하다.
- `/api/tax-schedule`은 과거 고정 날짜 레거시 API로 남았다. 외부 사용 여부 확인 후 제거하거나 공식 일정 기반으로 별도 마이그레이션한다. 채팅용 일정 조회 도구는 아직 연결하지 않았다.
# 국제세무 파일럿 후속 (2026-09-25)

- `evaluation/sources/international-tax/pilot-2026-09-25/` 17개 공식 원본은 수집/해시 검사만 통과했다. 17개 모두 `unreviewed`이며 시행·적용일 검증, 본문 영역 정제, 원문 언어 대조가 남았다.
- 한–일 조약 원본 PDF에 OCR을 적용하고 추출 조문을 스캔본과 대조한다. 일본 재무성 MLI 통합 참고문은 법적 원문이 아니다. 미국 USCODE-2024 판본은 현행 2026년 답변에 자동 적용하지 않는다. 중국 영문 자료는 중국어 원문과 대조한다.
- 관할·과세연도·거주지/원천지 질의 스키마 및 3개 양자 조약 관계를 설계한 뒤, 국가별 분리 검색과 유보 테스트를 먼저 추가한다. 그 전에는 현재 한국 중심 RAG/Graph/계산기·서비스 DB로 이 자료를 적재하지 않는다.
