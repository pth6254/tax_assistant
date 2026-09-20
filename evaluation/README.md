# 요소별 평가·검수 파이프라인

## 판례 수집 파일럿

`python -m evaluation.precedents --output evaluation/sources/precedents/NEW_BATCH`
는 .env의 LAW_API_KEY로 공식 대법원 출처 판례 후보 최대 10건을 조회한다.
법령별 최신 10개 목록 중 최대 3개씩 수집하며 통계적으로 대표성 있는 표본은 아니다.
법령 참조 검색은 민사도 포함한다. 원본은 OC를 제거한 API 응답이며 manifest의 해시는
재포맷 이전 정제 응답 기준이다. 상세 ID/사건번호/본문 최소 길이를 확인한다.
2026-09-20-pilot은 10건 수집, 그중 세무 5건의 draft-cards.json을 작성했다.
`--cards-only`는 해당 파일럿 ID 목록을 사용한 오프라인 초안 생성 옵션이며 범용 자동 정답 생성기가 아니다.
evaluation/sources는 Git/Docker 제외. 운영 DB·학습·외부 평가 업로드에 자동 연결하지 않는다.
원문 개인정보·출처 이용 조건·관련 심급·적용 법령·평가 정답 누출 검수 후 공유/승인할 것.

## 로컬 LLM Judge (보조 판정)

`python scripts/evaluate.py judge --run-dir evaluation/runs/RUN --output evaluation/runs/JUDGE`

기존 생성 관측과 승인된 고정 컨텍스트 루브릭을 현재 provider/model로 판정한다.
`judge.json` 및 `judge.md`를 별도로 저장하며 원래 보고서·인간 검수·gate는 변경하지 않는다.
종료 코드 2는 보조 결과로 인간 검수가 남아 있음을 뜻한다. 기존 출력 경로는 덮어쓰지 않는다.
draft/원문 없음/입력 예산 초과는 unknown, 호출·JSON·발췌 검증 오류는 error다.
8192 컨텍스트, 최대 768 출력 토큰, 요청당 120초, 순차 호출이며 Ollama는 호출 후 모델을 해제한다.
증거는 A/R 문장 ID로 선택하고 코드가 원문을 복원한다. 일반 기준은 답변/원문 쌍을 요구한다.
기존 answer-insufficient-context 합성 사례의 3개 행동 기준만 원문 발췌를 필수로 요구하지 않는다.
누락은 fail/omission, 금지 주장 부재는 pass/absence와 전체 답변 ID 검토 범위가 필요하다.
형식·ID 오류만 최대 1회 재평가하며 통신 오류나 유효한 fail/unknown은 재시도하지 않는다.
이 규칙은 근거 형식 검증이며 Judge가 실제 의미를 올바르게 판단했다는 보증은 아니다.
서비스의 기본 설정은 변경하지 않지만 동일 서버 자원을 쓰므로 사용량이 적을 때 실행한다.
생성 모델과 동일 모델일 수 있어 자기평가 편향이 있다. 모델 가중치 digest는 아직 기록하지 않는다.
현재 LangSmith Judge feedback 업로드와 전체 채팅 A/B 수집은 미연결이다.

평가 항목·Judge 판정 설계는 [품질 기준서](QUALITY_CRITERIA.md), 대표 질문 5개는
[초안 카드](datasets/answer_pilot.json)를 참고한다. 모두 dev/draft이며 아직 Judge 평가 대상 승인이 아니다.
`python scripts/evaluate.py validate --dataset evaluation/datasets/answer_pilot.json`으로 형식을 검사한다.
이 검사는 법적 정답 검수나 Judge 반례 판정이 아니다.

이 디렉터리는 **서비스 코드와 독립적인 평가 도구**다. 실행 명령은 `scripts/evaluate.py`, CLI 구현은 `evaluation/cli.py`이며
앱에서 import하지 않는다. 기존 RAG 평가의 조문번호 부분 문자열 매칭과
“기대 조문이 한 번 등장하면 답변이 정확하다”는 판정을 대체한다.

## 1. 무엇을 정답으로 인정하는가?

판정 전에 세 가지가 고정돼 있어야 한다.

1. **입력·적용 범위**: 질문, 기준일, 필요한 사용자 조건, 데이터/모델 버전.
2. **기대 결과**: 필수 근거, 허용 가능한 보조 근거, 잘못된 근거, 반드시 설명할 주장과 금지할 주장.
3. **근거와 검수 이력**: 원문 URL·발췌·버전, 검수자·검수일·이유.

`review.status=approved`인 공식 법령 사례는 인간 검수자, 기준일 `as_of`, 출처/발췌,
각 검색 라벨의 출처/발췌/버전 식별자가 필요하다. `grounded=true` 같은 과거 표시만으로
승격하지 않는다. 이 메타데이터는 검수 기록이지 검수자의 신원을 인증하는 시스템은 아니다.
팀의 리뷰 절차로 실제 검수 여부를 확인해야 한다.

합성 문법·산술 계약은 `basis=synthetic_contract`로 구분한다. 작성자가 문법/산술을
검수할 수 있지만 이 점수를 실제 세무 정답률로 합산하지 않는다.

### 검색 후보 라벨

| 라벨 | 의미 | 예시의 성격 |
|---|---|---|
| `required` | 이 질문에 반드시 필요한 근거 | 법률+시행령을 모두 요구하면 각각 지정 |
| `supporting` | 없어도 핵심 답변은 가능하지만 유용한 보조 근거 | 관련 절차·정의 |
| `irrelevant` | 질문의 답변에 도움이 되지 않는 근거 | 무관한 제도 |
| `hard_negative` | 정답과 닮았으나 이 질문에서는 잘못된 근거 | 같은 용어/조문번호, 다른 세목·대상·시점 |
| `unjudged` | 아직 라벨을 부여하지 않은 관측 후보 | 자동으로 오답이나 정답으로 간주하지 않음 |

hard negative에는 **왜 틀렸는지**와 혼동 유형(`wrong_tax`, `wrong_subject`, `wrong_date`,
`wrong_level`, `branch_vs_paragraph`, `wrong_exception`, `same_terms`)을 반드시 기입한다.
역방향 인용 관계가 정확하더라도 질문에 부적합할 수 있다. 같은 계열 전체를 일괄 negative로
만들거나, 정답 목록에 없다는 이유만으로 negative로 지정하지 않는다.

법령명·조문번호·항/호·버전으로 정확히 비교한다. `제1조`가 `제10조`에 포함됐다고
맞는 것으로 처리하지 않는다. `제59조의4`와 `제59조 제4항`도 다르다.
법령해석례 사건번호는 조문과 별도 `kind=interpretation`으로 지정한다.
조 전체 반환을 특정 항을 찾은 것으로 자동 인정하지 않는다. 항 단위 평가는 항 식별자가
있는 관측 자료를 제공해야 하며, 현재 live retrieval은 조 단위 결과다.

### 판정 상태

- `pass`: 선택한 사례의 모든 요구 조건 충족. **배포 승인이나 전체 시스템 품질 보증이 아니다.**
- `fail`: 필수 근거 누락, 허용치를 넘는 hard negative, 계산 오차, 루브릭 불충족 등.
- `incomplete`: 검수 전 라벨, 미판정 후보, 미수집 단계, 인간 답변 검수 누락.
- `error`: DB/모델 장애, 시간 초과, 잘못된 관측 형식. 정답률 계산에서 조용히 제외하지 않는다.

최상위 gate는 승인 사례 실패 또는 어떤 실행 오류라도 있으면 fail, 나머지 미검수/미판정이
있으면 incomplete다. draft의 실패를 확정된 세무 오답이라고 주장하지 않는다.
CI의 계약 테스트 gate와 실제 서비스 품질 gate는 구분한다.

## 2. 평가 영역과 실제 구현 범위

| 영역 | 수집/판정 방식 |
|---|---|
| 원문 데이터 | `source`: 실제 PG 조회 후 `exists`, 날짜, 버전, 본문 필드에 대해 명시적 checks 적용 |
| 참조 파싱 | `reference`: 실제 참조 파서의 조/가지번호/항/호/목을 기대 값과 비교 |
| 그래프 관계 | `relation`, `graph_index`: 실제 추출기/색인기를 실행하고 정확한 대상·미해결 여부 비교 |
| 검색·Graph 확장 | `retrieval`: 동일 기본 결과에서 base/graph 한 쌍 수집, 근거 집합·hard negative 판정 |
| 컨텍스트 | `recorded`: 실제 입력 직전 trace를 가져와 필수 근거 보존·잘림·길이 검사 |
| 계산 | `progressive_tax`: 합성 구간 산술; `calculator`: 실제 계산 모듈·입력 스키마와 수치/오류 계약 비교 |
| 도구 선택 | `tool_selection`: 실제 planner의 도구명·인자 비교. 도구 실행/사용자 문서 조회는 하지 않음 |
| 답변 | `answer_fixed_context`: 고정 근거로 실제 생성/인용 guard 실행. 의미·근거성은 인간 루브릭 판정 |
| 권한·안전·성능 | `recorded`: API/부하 테스트 관측 자료의 상태·호출 여부·정보 유출·시간/크기 계약 검사 |

`recorded`는 실제 관측 JSON을 `score` 명령에 제공하는 어댑터다. 입력의 기대 값을 관측 결과로
복사하지 않는다. 현재 context/safety/performance 제품 trace 자동 계측 및 브라우저 수집기는
연결하지 않았다. 관측이 없으면 반드시 incomplete다. 기존 pytest의 권한/오류 테스트는 계속 유지한다.

현재 신규 live 검색은 질문 1개와 명시된 입력 필터 또는 `ALL`을 사용한다. **정답 법령명을
필터로 주입하지 않는다.** 분류·멀티쿼리·웹·대화 이력·도구 실행을 포함한 전체 채팅 E2E가 아니다.
고정 근거 생성도 검색과 분리된 컴포넌트 평가이며, `process_chat`을 호출해 대화 DB에 쓰지 않는다.

### 검색 지표 정의

- `recall_at_k`: 필수 근거 중 top-K에 포함된 비율. `recall_all`은 전체 반환 기준.
- `mrr`: 첫 필수/보조 근거의 역순위. 정답 후보가 하나라도 있다는 지표이지 답변 정답률이 아니다.
- `judged_precision`: 라벨이 있는 반환 후보 중 required/supporting 비율.
- `precision_lower_bound`: 미판정 후보를 분모에 포함한 보수적 비율. 미판정을 확정 오답으로 부르지는 않는다.
- `judgment_coverage`: 반환 후보 중 라벨이 있는 비율. 미판정 후보가 있으면 검색 통과 불가.
- `ndcg_lower_bound`: required 이득 3, supporting 이득 1, 미판정/negative 0으로 계산한 순위 지표.
- hard negative 개수/정답보다 앞선 배치, 중복 수, 추가 근거의 정밀도·새 필수 근거 발견 수를 별도 기록한다.

기본 통과 기준은 필수 Recall@K=1, 판정된 후보 precision≥0.8, hard negative=0이다.
이는 초기 **정책값**이며 실측 최적값이 아니다. 사례별 변경은 데이터셋 버전을 올려 추적한다.
hard negative는 top-K 뒤에 붙더라도 모델에 전달되는 전체 결과에서 검사한다.
Graph는 기본 top-5를 유지하고 최대 7개를 반환하므로 동일 K와 전체 결과를 함께 보고,
추가 근거 발견을 동일 토큰 예산의 정확도 향상으로 주장하지 않는다.

### 답변·계산 판정

계산은 `number`와 기본 허용 오차 0을 사용한다. 정수 원 단위 차이, 단계별 값, 오류 코드,
실패 시 금액 필드 부재를 각각 검사한다. 비교할 기대 값은 독립 산술/공식 규정으로 작성하며
같은 운영 함수를 호출해 정답을 생성하지 않는다.

답변은 사실성·근거성·완결성·시점·유보·안전을 **각각** 루브릭으로 기록한다.
`contains` 같은 자동 검사는 문자열 신호일 뿐 의미상 정답 판정이 아니다.
모든 루브릭에 인간의 판단·이유·근거가 없으면 pass가 될 수 없다.
LLM-as-judge를 정답 판정기로 사용하지 않는다. 추후 추가하더라도 인간 검수와 분리된 보조 신호여야 한다.
검수는 `payload_hash`에 묶여 답변이 바뀌면 기존 검수가 무효화된다.

## 3. 제공 평가셋

- `datasets/contracts.json`: 합성 파싱·관계·산술 22사례, 각 사례에 의도적으로 틀린 출력 1개.
  validate 단계에서 그 반례가 실제로 fail인지도 검사한다. 법정 세율 검증은 아니다.
- `datasets/retrieval.json`: 기존 39문항을 모두 dev/draft로 이관. 법령명이 정답 필터로 유출되지 않는다.
  세목·대상·조문번호/가지번호 혼동 hard-negative 후보 6개를 제안했으며 공식 원문/인간 검수 전이다.
- `datasets/components.json`: 원문/실제 계산 입력 오류/도구 선택/고정 컨텍스트 생성과
  context/safety/performance 관측 계약 7사례. 합성 승인과 공식 검수 초안을 구분한다.

이것은 시작 평가셋이지 세무 전 영역을 대표하는 검증 완료 벤치마크가 아니다.
실제 날짜·예외·복합 법률/시행령 정답 근거 집합과 독립 전문가 검수는 계속 보강해야 한다.
시점 혼동은 평가기 테스트에서 합성 old/new 버전으로 확인하며 실제 과거법 정답으로 소개하지 않는다.

같은 질문의 변형·대조쌍은 `group`을 같게 두고 같은 split에 배치한다.
group과 정규화된 동일 질문의 dev/test 중복은 스키마 검증에서 차단한다.
의미가 같은 패러프레이즈의 그룹 지정은 사람이 검토해야 한다. 자동으로 모든 누출을 찾지는 못한다.
기존 질문은 이미 튜닝에 사용됐으므로 test/holdout으로 다시 이름 붙이지 않는다.

## 4. 실행

구 `scripts/eval_rag.py`·`scripts/eval_graph_rag.py`는 제거했으며 과거 결과는 보존한다.

- `scripts/evaluate.py`: 경로 설정과 공통 CLI 호출만 담당.
- `evaluation/cli.py`: 명령·인자 처리, 실행 제어, 안전한 오류 출력과 종료 코드.
- `evaluation/runner.py`: 관측 수집, 재현성 기록, 결과 파일 저장과 비교.
- `evaluation/adapters.py`·`scoring.py`·`schema.py`: 실제 기능 호출·판정·평가 규약.

WSL에서 가상환경을 활성화한다. 실제 실행은 기존 provider/Compose 환경을 사용한다.
새 라이브러리·모델·DB 마이그레이션이 필요하지 않다.

```bash
source venv-wsl/bin/activate
python scripts/evaluate.py validate --dataset evaluation/datasets/contracts.json
python scripts/evaluate.py run --split all

# 서비스 이미지 안에서 실제 검색. 미검수 라벨이므로 exit 2가 정상적인 검수 대기 결과.
docker exec tax_backend python scripts/evaluate.py run \
  --dataset evaluation/datasets/retrieval.json --mode live --include-draft

# 도구 선택/고정 컨텍스트 생성은 명시적 모델 호출 허용 필요
docker exec tax_backend python scripts/evaluate.py run \
  --dataset evaluation/datasets/components.json --mode live --stage answer --allow-generation --repeat 3

# 전체 선택 영역을 순서대로 실행: 누락 단계/미검수는 pass로 숨기지 않음
docker exec tax_backend python scripts/evaluate.py suite \
  --mode live --include-draft --output evaluation/runs/review-batch
```

`--limit`, `--stage`, `--split`, `--repeat`, `--timeout`으로 범위를 지정한다.
default split은 dev이며 test를 규칙 조정에 반복 사용하지 않는다.
생성은 `--allow-generation` 없으면 실행하지 않고 incomplete로 남긴다.
같은 이름의 output 디렉터리가 이미 있으면 덮어쓰지 않고 실패한다.

종료 코드: **0=선택 범위 통과, 1=판정 실패/사례 실행 오류, 2=미검수·미판정, 3=CLI 입력·실행 오류**.
잘못된 스키마·서로 다른 데이터셋의 결과·중복 관측은 거부한다.
전체 실행을 0으로 만들기 위해 draft를 임의 승인하거나 미수집 단계를 삭제하지 않는다.

## 5. 결과 파일과 검수 루프

파일 대신 화면에서 확인하려면 명시적으로 선택한 결과를 LangSmith에 전송한다.
자체 대시보드는 제거했으며 사용자 서비스에는 메뉴·라우트·자동 추적을 추가하지 않는다.
[LangSmith 설정·전송·검수 방법](LANGSMITH.md). 기존 `evaluation/reviews/` 이력은 보존하며
LangSmith 검수를 로컬 보고서/정답셋에 자동 반영하지 않는다.

기본 출력은 `evaluation/runs/<UTC시각>-<무작위ID>/`이며 Git과 Docker 빌드에서 제외한다.

- `dataset.json`: 실행 당시 정답 규약 사본
- `observations.json`: 실제 출력/오류·반복 번호·소요 시간·코드/설정/공개 데이터 fingerprint
- `report.json`, `report.md`: 영역·base/graph·합성/공식·검수 상태별 결과와 실패 이유
- `adjudications.json`: 재채점에 사용한 인간 검수 기록 사본. 미검수 실행은 빈 배열
- `evidence_review_queue.json`: 미판정/초안 검색 후보, 원문·버전·기존 제안 라벨. 최종 라벨은 null
- `review_queue.json`: 생성 답변 루브릭 검수 양식. 빈 reviewer/날짜/verdict는 승인으로 읽히지 않음

선택 단계의 의존성만 실행 전후 해시로 기록한다. 검색은 법령 본문·벡터·항 벡터·CITES,
계산은 계산 기준 테이블을 대상으로 한다. 고정 컨텍스트 답변/도구 선택에는 무관한 DB 접속을 요구하지 않는다.
실행 중 데이터가 바뀌면 통과 gate를 incomplete로 낮춘다. 사용자 문서/대화는 해시 수집 대상이 아니다.
로그에는 비밀 endpoint/key나 예외 원문을 저장하지 않는다. 모델 이름/provider와 코드 hash는 기록하지만
가변 모델 태그의 실제 가중치 digest, GPU 부하, 전체 OS 환경까지 고정한 재현성 보증은 아니다.

검수 절차:

1. 후보 원문과 공식 출처를 대조해 required/supporting/negative 및 이유를 검수한다.
2. 의미가 다른 후보를 hard negative로 지정하고 반례/대조 질문을 추가한다.
3. 인간 검수·기준일·원문 버전을 채우고 dataset version을 올린다. 관측 파일로 정답을 자동 덮어쓰지 않는다.
4. **바뀐 데이터셋으로 새 실행**한다. 기존 observations는 옛 dataset hash에 묶여 있어 새 gold로 조용히 재채점하지 않는다.
5. 답변 검수는 질문/확정 근거/출력을 함께 읽고 review_queue의 각 기준에 passed·rationale·evidence·reviewer·reviewed_on을 채운다.
6. observations와 같은 dataset 사본으로 아래처럼 재채점한다. 자동 생성 초안을 인간 검수자로 위장해 승인하지 않는다.

```bash
python scripts/evaluate.py score \
  --dataset evaluation/runs/RUN/dataset.json \
  --observations evaluation/runs/RUN/observations.json \
  --adjudications evaluation/runs/RUN/review_queue.json

python scripts/evaluate.py compare \
  --baseline evaluation/runs/BASE/report.json \
  --candidate evaluation/runs/CANDIDATE/report.json
```

재채점은 새 output에 저장된다. 관측 자료의 출처와 수집 방식(mode=recorded/live/offline)을 명시한다.
같은 dataset hash/scorer/split/선택 사례/반복 수/mode인 실행만 비교하며, metric별 하락과
pass→실패/미판정 전환을 기록한다. 데이터/모델 조건이 달라진 원인을 자동으로 코드 개선 효과로 단정하지 않는다.
표본 수가 작거나 반복 실행 편차가 있으면 통계적 우월성을 주장하지 않는다.

컨테이너 안의 reports는 컨테이너 재생성 시 없어질 수 있다. 필요한 실행 폴더만
`docker cp tax_backend:/app/evaluation/runs/<RUN> ./evaluation/runs/<RUN>`으로 보존한다.
공유 전에는 사용자 입력·답변에 개인정보가 없는지 확인한다. CI는 합성 계약 보고서만 artifact로 업로드한다.

## 6. 자동화와 남은 작업

CI는 스키마/누출 검사, 평가기 단위 테스트, 22개 합성 계약+반례 검증을 실행한다.
외부 DB·로컬 모델 없이 동작하며 실서비스 정확도를 평가했다고 표시하지 않는다.
실제 검색/모델 실행은 위 live 명령 또는 접근 가능한 별도 실행 환경에서 명시적으로 수행한다.
실제 데이터 평가를 GitHub-hosted runner에 무조건 연결하거나 사용자 자료를 업로드하지 않는다.

다음은 전문가가 검수한 복합 질문/기간/예외 평가셋 확장, 전체 채팅 trace 자동 계측,
동일 토큰 예산 비교, 부하/장애 시험 수집, 검수자 간 일치도와 독립 test셋 확보다.
현재 GraphRAG 기본 비활성 설정은 변경하지 않는다. 이 리팩토링은 검색 알고리즘 개선 작업과 별개다.
