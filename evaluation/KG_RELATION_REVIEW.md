# 과거 법령 Knowledge Graph 관계 검수

`kg_relation_review.py`는 PostgreSQL에 보존된 법령 버전·XML 구조에서 `DEFINES`(명시적 정의)와 `CITES`(명시적 인용) 후보를 추출해 검수 카드로 만든다. 카드의 `review.status=unreviewed`, `gold_labels=false`는 의도된 값이다. 추출 성공이나 원문과의 문자열 일치만으로 법적 관계를 정답으로 승인하지 않는다. 이 파일은 아직 평가 가능한 골든셋이 아니라 그 입력 자료다.

```bash
source venv-wsl/bin/activate
python -m evaluation.kg_relation_review \
  --scope '306:제1조의2' --scope '306:제2조' \
  --scope '306:제2조의2' --scope '306:제2조의3' \
  --scope '306:제3조' --scope '306:제4조' \
  --scope '3162:제125조' --scope '3163:제125조' \
  --max-per-kind 5 \
  --output evaluation/sources/kg_relation_review_pool.json
```

WSL 저장소 루트에서 실행하며 PostgreSQL 접속 설정이 필요하다. 컨테이너 안에서 실행하면 결과 파일도 컨테이너 안에만 남으므로 로컬 검수 파일 생성에는 위 명령을 사용한다. 같은 범위를 다시 실행하면 후보 선정은 assertion key의 SHA-256 정렬로 재현된다. `--max-per-kind`는 각 범위의 관계 종류별 최대 카드 수다. `evaluation/sources/`는 Git에 넣지 않는 원문·검수 작업 영역이다. 카드에 포함된 `version_id`, `snapshot_id`, `article_id`, `article_hash`, `reference`, `source_hash`, `source_url`, `quote`로 정확히 같은 출처를 다시 확인한다.

법령 종류와 시점을 넓히려면 자동 표본을 생성한다.

```bash
python -m evaluation.kg_relation_review --auto \
  --laws-per-level 2 --per-kind 2 --challenge-per-kind 4 \
  --old-before 2016-01-01 --as-of 2026-09-26 --seed kg-relation-v1 \
  --output evaluation/sources/kg_relation_stratified.json
```

법령명으로 법률·시행령·시행규칙을 구분하고, 각 법령에서 지정 날짜 이전의 버전과 최근 버전 중 실제 관계 후보가 있는 것을 선정한다. `--as-of`보다 시행일이 늦은 버전은 제외한다. 선택한 버전마다 `DEFINES`/`CITES`를 결정론적으로 뽑는다. `challenge` 카드는 같은 법령의 다른 후보 대상으로 바꿔 만든 **미검수 혼동 사례**다. 실제 오답·hard negative 여부는 인간 검수로 확정한다. 결과의 `coverage`에는 종류·시점·후보 수·빈 범위가 기록된다. 파일이 이미 있으면 덮어쓰지 않는다.

## 사람이 확정할 기준

1. 원문 무결성: 카드의 조문 행·버전·해시·출처 URL이 보존 원본과 일치하는가? 같은 `제N조`가 두 행이면 개정 지시문과 현행화 본문을 혼동하지 않았는가?
2. 관계 사실성: `DEFINES`는 해당 문구가 대상 개념을 실제로 정의하는가? `CITES`는 정확한 법령명·조/항/호/목을 명시적으로 인용하는가? 단어가 비슷한 것만으로는 부족하다.
3. 시점·효력: 출처 버전의 시행일과 인용 대상의 적용 버전을 확인했는가? 문자열 인용이 사실이어도, 대상 버전을 확정할 수 없다면 버전 간 유효 관계를 승인하지 않는다.
4. 질문 적합성은 별도: 관계가 원문에 존재한다는 G1 판정과, 특정 세무 질문의 정답 근거라는 G2 판정을 혼합하지 않는다.

최소 층화 목표는 `DEFINES`/`CITES`, 법률/시행령/시행규칙, 최근/과거 버전, 조/항/호/목, 인용 대상 해소/미해소, 중복 조문번호와 개정 지시문이다. 초기 세 범위는 파이프라인 점검용으로 이 목표를 모두 충족하지 않는다. 골든셋 승격 전에 각 층을 보강하고, 같은 법령 계열·동일 조문·유사 버전은 같은 그룹으로 묶어 dev/test 누출을 막는다.

각 카드에는 인간 검수자가 `supported`, `unsupported`, `uncertain` 중 하나와 이유·검수자·날짜를 기록한다. hard negative는 `wrong_date`, `wrong_level`, `branch_vs_paragraph`, `same_terms`, `wrong_subject` 등 혼동 이유와 *올바른 비교 대상*을 함께 기록하고, 근거가 부족하면 억지로 오답 처리하지 않는다. 두 사람이 독립 검수 후 불일치를 조정하는 방식을 권장한다. 검수 완료 전 카드는 기존 `evaluation.schema.Dataset`의 `approved` 케이스나 Neo4j `reviewed` 관계로 자동 변환하지 않는다.

평가 시에는 추출 정확도(종류별 precision/recall), 출처·시점 일치율, hard negative 오인율을 따로 집계하고, 채팅 답변 정확도와 혼동하지 않는다. 공식 원문이나 수집 파서가 달라져 해시가 변하면 기존 라벨은 재검수한다.

## 관계 전용 LLM Judge 자동화

`kg_relation_judge.py`는 카드의 원본 버전·행·해시·관계 키를 PostgreSQL XML에서 먼저 재구성한다. 불일치하면 모델을 부르지 않고 `source_blocked`로 기록한다. 일치하는 카드에만 관계의 **문구상 명시 여부**를 묻는다. Judge가 제시한 근거 문구는 원본 발췌의 정확한 부분 문자열이어야 한다. 기본 2회 실행의 판정이 다르면 합의값을 비워 인간 검수 대상으로 남긴다. 실행 결과는 `advisory_only`이며 시점상 법적 적용 여부는 `not_assessed`다.

전체 카드의 원본 연결만 먼저 확인하려면 `--verify-only`를 지정한다. 이 실행에는 모델 호출이 없다.

```bash
python -m evaluation.kg_relation_judge --verify-only \
  --input evaluation/sources/kg_relation_stratified.json \
  --output evaluation/runs/kg-relation-preflight.json
```

```bash
python -m evaluation.kg_relation_judge \
  --input evaluation/sources/kg_relation_review_pool.json \
  --output evaluation/runs/kg-relation-pilot.json \
  --max-cards 5 --repeats 2
```

평가용 설정을 별도로 지정하지 않으면 현재 `.env`의 채팅 provider/model을 사용한다. 모델 호출 비용과 외부 전송이 발생할 수 있다. 공개 법령 원문만 대상으로 하고 사용자 질문·PDF를 이 입력에 넣지 않는다. 출력 파일을 덮어쓰지 않는다. Judge 결과만으로 Neo4j의 `review_status`, 인간 골드 라벨, 서비스 RAG 설정은 변경되지 않는다. 동일 모델 반복 합의는 독립 전문가 합의가 아니다.

`KG_JUDGE_PROVIDER`, `KG_JUDGE_MODEL`, `KG_JUDGE_REASONING_EFFORT`, `KG_JUDGE_BASE_URL`, `KG_JUDGE_API_KEY`, `KG_JUDGE_TIMEOUT_SEC`, `KG_JUDGE_MAX_TOKENS`, `KG_JUDGE_INPUT_BUDGET_BYTES`, `KG_JUDGE_NUM_CTX`로 채팅 모델과 독립적으로 설정한다. 설정하지 않으면 현재 채팅 provider/model을 상속한다. 예시는 `.env.example`에 있다.

배치는 카드마다 `<출력파일>.progress.json`을 원자적으로 갱신한다. 중단되면 같은 입력·모델·프롬프트·실행 옵션으로 `--resume`을 지정한다. 실패 상태(`model_error`, `partial_model_error`, `source_blocked`)를 다시 실행하려면 `--resume --retry-failed`를 함께 지정한다. 완료된 파일은 재사용하거나 덮어쓰지 않는다. `--max-cards`와 `--repeats`로 Judge 요청 수를 제한하며, 진행 파일과 최종 보고서에는 재시도 포함 시도 횟수 및 제공자가 반환한 토큰·비용 숫자만 저장한다. 제공자 내부 재시도 때문에 실제 HTTP 요청은 Judge 시도 횟수보다 많을 수 있다. 제공자가 비용을 반환하지 않으면 비용은 알 수 없는 값이며 0원으로 취급하지 않는다.

```bash
python -m evaluation.kg_relation_judge \
  --input evaluation/sources/kg_relation_stratified.json \
  --output evaluation/runs/kg-relation-batch.json \
  --max-cards 10 --repeats 2

# 배치가 중단된 경우
python -m evaluation.kg_relation_judge \
  --input evaluation/sources/kg_relation_stratified.json \
  --output evaluation/runs/kg-relation-batch.json \
  --max-cards 10 --repeats 2 --resume
```

전문가가 별도 `evaluation/sources/kg_relation_gold.json`에 아래 형식으로 라벨을 확정한 뒤에만 비교 지표를 계산한다. `pool_hash`는 Judge 결과의 값과 동일하게 기입한다. `uncertain`은 이진 정확도 분모에서 제외하지만 라벨·판정 수에는 남는다.

```json
{
  "schema_version": "1.0",
  "purpose": "human_relation_gold",
  "pool_hash": "<judge 결과의 pool_hash>",
  "reviews": [{
    "assertion_key": "<검수 카드의 assertion_key>",
    "label": "unsupported",
    "reviewer_kind": "human",
    "reviewer": "<검수자 식별자>",
    "reviewed_on": "2026-09-26",
    "reason": "<원문에 근거한 판정 이유>",
    "hard_negative": true,
    "confusion": "same_terms"
  }]
}
```

```bash
python -m evaluation.kg_relation_score \
  --pool evaluation/sources/kg_relation_review_pool.json \
  --judge evaluation/runs/kg-relation-pilot.json \
  --gold evaluation/sources/kg_relation_gold.json \
  --output evaluation/runs/kg-relation-score.json
```

채점은 인간 라벨이 있는 카드에 대해서만 판정 커버리지·판정된 사례의 정확도·supported 정밀도/재현율·hard negative 오인율을 분리해 낸다. 현재는 인간 라벨 0건이므로 품질 점수를 발표할 수 없다. 이 경로는 기존 LangSmith 답변 Judge 업로드와 별도이며, LangSmith 실험 전송은 추후 데이터 전송 범위를 검토한 다음 연결해야 한다.
