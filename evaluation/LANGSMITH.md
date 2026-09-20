# LangSmith 평가 결과·검수

자체 evaluation_dashboard 대신 LangSmith를 사용합니다. 기존 평가셋·scoring·CLI·실행 결과는 유지합니다.
이번 연결은 **저장된 결과를 LangSmith 실험으로 가져오는 기능**입니다. 새로운 LLM 추론이나
실서비스 추적을 실행하지 않으며, LangSmith 평가 모델 호출 비용을 발생시키지 않습니다.
LangSmith 자체 이용·보관 비용과 검수 기능 제공 범위는 계정 플랜을 확인하세요.

## 1. 계정 설정

1. LangSmith 계정/워크스페이스를 준비하고 API key를 생성합니다.
2. 프로젝트 루트의 `.env.example`에 `LANGSMITH_API_KEY=` 값을 입력합니다.
   사용자 요청에 따라 이 파일에서 직접 읽습니다. 실제 키가 든 상태로 Git에 커밋하지 마세요.
3. 평가 키는 publish 명령에서 읽습니다. 프로세스 환경변수 전체로 로드하지 않으며 `.env.example`은 Docker 빌드에서 제외합니다. 제품 `.env`와 Compose에는 키/추적 설정을 추가하지 않습니다.
4. 계정 리전에 맞춰 prepare의 `--region us` 또는 `--region eu`를 사용합니다.

`TAX_EVAL_LANGSMITH_API_KEY` 환경변수로 키를 전달할 수도 있습니다. 일반 서비스의
LANGSMITH_TRACING/LANGCHAIN_TRACING_V2는 켜지 않습니다. SDK는 langsmith==0.12.1로 고정했습니다.

## 2. 전송 계획 생성 (네트워크 없음)

WSL 프로젝트 루트에서:

```bash
source venv-wsl/bin/activate

# 기본: 사례 ID·검수 상태·숫자 지표·해시만. 질문/답변/원문/자유형 메타데이터 제외.
python scripts/evaluate.py langsmith prepare \
  --run-dir evaluation/runs/retrieval-rescored \
  --output evaluation/runs/langsmith-metrics-plan.json --region us

# 질문·기대 근거·원문·답변을 보며 검수하려는 경우에만 본문 포함.
python scripts/evaluate.py langsmith prepare \
  --run-dir evaluation/runs/retrieval-rescored \
  --output evaluation/runs/langsmith-review-plan.json --region us \
  --include-content --annotation-queue
```

계획 파일 전체를 열어 전송할 데이터와 리전을 확인합니다. 본문 포함 시 검수자 이름·조건·출처·발췌도
포함될 수 있습니다. 마스킹/익명화가 자동으로 완료됐다는 뜻이 아닙니다. 공개 법령·합성 사례부터 사용하세요.
실제 사용자 질문/PDF/개인정보는 전송 허용 범위를 별도로 확인해야 합니다.
기존 파일을 덮어쓰지 않으므로 새 계획을 만들 때는 다른 이름을 사용합니다.

현재 scorer로 재계산한 report와 저장 report가 다르면 거부합니다. 과거 scorer 결과는 score로 새 폴더에
재채점한 후 준비하세요. `prepare`의 성공은 전송 성공이나 평가 통과를 의미하지 않습니다.

## 3. 확인한 계획만 명시적으로 전송

prepare 출력의 sha256을 사용합니다. 아래 HASH는 실제 확인한 값으로 바꿉니다.

```bash
python scripts/evaluate.py langsmith publish \
  --plan evaluation/runs/langsmith-review-plan.json \
  --approved-sha256 HASH \
  --receipt evaluation/runs/langsmith-review-receipt.json
```

- 해시가 다르거나 키가 없으면 전송하지 않습니다. 같은 receipt 파일을 재사용하지 않습니다.
- LangSmith의 Datasets & Experiments에서 `tax-eval-<dataset_key>`를 찾습니다.
- 같은 평가셋을 참조하는 `tax-eval-base-...`, `tax-eval-graph-...` 실험을 선택해 비교합니다.
- reference outputs에는 검수 상태와 (본문 포함 시) 정답 규약, outputs에는 관측 결과가 표시됩니다.
- `approved.*`와 `diagnostic.*` 지표를 분리합니다. draft 성적은 확정된 세무 정확도가 아닙니다.
- `evaluation_status`의 incomplete/error를 오답률 0/1로 강제 변환하지 않습니다.
- **실제 소요 시간은 observed_elapsed_seconds**입니다. 화면 기본 latency는 가져오기용 시간이며
  실서비스 실행 속도로 해석하면 안 됩니다. 단계별 실시간 span은 이번 범위에 없습니다.

동일 plan의 실험이 이미 있으면 추가 업로드를 거부합니다. 원격 dataset 내용이 수정된 경우에도 거부하며
덮어쓰지 않습니다. 여러 API 호출은 트랜잭션이 아니므로 장애 시 일부 dataset/experiment가 남을 수 있습니다.
receipt에 partial_or_failed와 생성된 ID가 기록됩니다. 이를 확인하고 원격 상태를 정리한 뒤 재시도하세요.
자동 삭제/롤백은 하지 않습니다. 로컬 원본 결과는 항상 보존됩니다.

## 4. 사람 검수

`--include-content --annotation-queue`로 준비했다면 Annotation Queues에
`tax-eval-review-...`가 생성됩니다. 원문·시점·질문·관측을 대조해 검수하고 이유/수정 제안을 기록하세요.
정답셋 rubric을 기준으로 필요한 feedback key를 LangSmith UI에서 구성할 수 있습니다.

- 검색 라벨: required/supporting/irrelevant/hard_negative, 혼동 유형과 판정 근거.
- 답변: 사실성·근거성·완전성·시점·유보·안전성.
- LangSmith 검수는 로컬 gold를 자동 승인하거나 로컬 gate를 변경하지 않습니다.
- 검수 결과를 내보내 사람이 기존 Dataset/Adjudication 규약에 맞춰 반영한 뒤 재채점합니다.
  자동 다운로드·변환·양방향 동기화는 아직 구현하지 않았습니다. payload_hash를 유지해야 합니다.
- 기존 evaluation/reviews의 검수 이력은 삭제하지 않았으며 필요하면 수동 이관합니다.

## 5. 검증 및 제한

```bash
python -m pytest tests/test_evaluation_langsmith.py tests/test_evaluation_cli.py -q
```

테스트는 실제 SDK 메서드 규약을 따르는 mock으로 외부 전송 차단·해시 검증·실험/지표 매핑·실패 기록을
검증합니다. 계정 API 연결/웹 UI까지 성공했다는 뜻은 아닙니다. API 키를 설정하고 공개/합성 데이터로
첫 전송을 확인해야 합니다. CI는 LangSmith에 업로드하지 않습니다.

공식 문서: [평가 방식](https://docs.langchain.com/langsmith/evaluation-types),
[reference dataset 실험](https://reference.langchain.com/python/langsmith/client/Client/create_project),
[지표 기록](https://reference.langchain.com/python/langsmith/client/Client/create_feedback),
[민감정보 보호](https://docs.langchain.com/langsmith/mask-inputs-outputs).
