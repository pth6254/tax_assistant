# 운영·데이터 작업 CLI

현행 기준: 2026-10-01. 생성/계획/Judge는 OpenRouter GPT-6 Luna, 임베딩은 Ollama Qwen3 v1이다.
서비스 기동은 WSL의 `bash dev/docker-up-wsl.sh backend frontend`, 전체 실행 규칙은 [AGENTS.md](../AGENTS.md)를 따른다.
DB CLI는 최신 백엔드 컨테이너의 `/app`에서 실행하는 것을 권장한다. 아래 `python ...` 명령을
호스트에서 실행할 때는 해당 가상환경·DB 주소·모델 설정을 별도로 확인한다.
완료 수치·백업 위치는 [최신 인수인계](../docs/ai/HANDOFF.md)에 기록하며, 이 안내만으로 데이터 작업을 자동 실행하지 않는다.

이 디렉터리는 FastAPI 요청 처리 코드가 아니라 개발자·운영자가 프로젝트 루트에서 직접
실행하는 배치 작업의 진입점만 포함합니다. 핵심 로직은 `app/services/`에 두고, 스크립트는
인자 처리·진행 상황 출력·리소스 정리·종료 코드만 담당합니다.

## 데이터 수집·동기화

- `python scripts/collect_international_tax.py --output evaluation/sources/international-tax/NEW_BATCH`: 한–미·한–일·한–중 공식자료 소규모 파일럿을 제품 DB와 분리해 수집한다. `--resume`은 실패 항목 재시도와 기존 해시 검증, `--audit`은 읽기 전용 전수 검사다. [수집 결과·한계](../docs/evaluation/international-tax-pilot-2026-09-25.md).

- `python scripts/collect_law_history.py discover|collect|status|versions|show|diff`: 현재 수집 법령의 과거 버전 아카이브. 기존 검색 데이터와 분리하며 실행·재개·한계는 [과거 법령 관리](../docs/LAW_HISTORY.md)를 참고한다.
- 독립 수집·자동 전수 검수는 `bash dev/law-history-wsl.sh start`로 기동한다. `scripts/run_law_history_worker.py`는 해당 컨테이너의 배치 진입점이며 보고서는 `evaluation/runs/law-history/`에 보존한다.
- 역사 임베딩/그래프는 `scripts/index_law_history.py prepare|graph|embed|all|status`와 `dev/history-index-wsl.sh`로 별도 실행한다. 실행·준비 상태·재개 규칙은 [역사 GraphRAG](../docs/HISTORY_RAG.md)를 참고한다.
- 버전별 조·항·호·목 및 정의·명시적 인용 후보는 실행 중인 backend에서 `python scripts/sync_tax_knowledge.py sync|all|audit|validate|repair-duplicates|candidates|review`로 관리한다. 기본 미리보기, 범위 지정 `--apply`, 버전별 재개 체크포인트, 읽기 전용 전수 감사를 제공한다. 검수된 관계만 과거 법령 검색에 사용한다. [검수 절차](../docs/TAX_KNOWLEDGE_GRAPH.md).

| 명령 | 용도 | 실행 시점 |
|---|---|---|
| `python scripts/ingest_laws.py` | 세법 법률·시행령·시행규칙 수집 | 최초 구축·수동 수집 |
| `python scripts/ingest_interpretations.py --query 소득세` | 법령해석례 수집 | 수동·정기 수집 |
| `python scripts/sync_laws.py --embed` | 기존 법령 개정 감지와 최신화 | cron·작업 스케줄러 |

## 유지보수·백필

| 명령 | 용도 | 안전장치 |
|---|---|---|
| `python scripts/backfill_law_type.py` | 과거 빈 `law_type` 데이터 점검·보정 | 기본 dry-run, `--run`일 때만 반영 |
| `python scripts/embed_clauses.py` | 항 단위 임베딩 대상 확인 | 기본 dry-run, `--run`일 때만 반영 |
| `python scripts/compare_embedding_providers.py` | Ollama v1과 llama.cpp v2 벡터 cosine 호환성 비교 | DB 변경 없음 |
| `python scripts/backfill_embeddings_v2.py` | 법령·항·PDF `embedding_v2` 백필 | 기본 dry-run, `--run`일 때만 반영 |
| `python scripts/repair_law_indexes.py preview --plan /tmp/law-repair-NEW/plan.json --scope all --include-clauses --graph-backup` | 동일 시행본 보정 후보/고정 계획·현행 그래프 사본 | DB 쓰기 없음, 새 출력 경로 사용 |
| `python scripts/repair_law_indexes.py apply --plan /tmp/law-repair-NEW/plan.json` | 고정 plan의 원문/부모·항 벡터 보정 | 기본 20행; 임베딩 준비·영속 백업·행 잠금/대조·transaction |
| `python scripts/repair_law_indexes.py rollback --plan /tmp/law-repair-NEW/plan.json` | 해당 실행의 원본·벡터·항 복원 | plan/backup/state 필요, 후속 수정 덮어쓰기 거부 |

`apply --limit 0`은 고정 plan 전체의 명시적 적용이다. 보정은 같은 MST·법령명·시행/공포일·XML 해시가 확인된
원문만 사용하며 다른 버전으로 자동 교체하지 않는다. 완료된 2026-10-01 보정을 반복하지 않고 새 대상·계획을 확인한다.
보정/rollback 후에는 `python scripts/sync_law_graph.py --all --apply`와 `python scripts/audit_law_graph.py`로
현행 그래프를 맞춘다. 전체 동기화의 범위를 확인하고 별도 역사 그래프는 보존한다.
컨테이너 재생성 전에 plan/모든 backup/state를 호스트에 보존한다.

백필을 실행하기 전에 반드시 `alembic upgrade head`가 완료돼 있어야 합니다. 백필 스크립트는
스키마를 만들지 않으며 Alembic revision을 대신하지 않습니다.

## 품질 평가

- `python scripts/evaluate.py langsmith prepare ...` / `langsmith publish ...`: 자체 대시보드 대신 LangSmith에서 평가 조회·비교·검수. 기본 전송 계획은 본문 제외이며 확인한 해시에 한해서 업로드합니다. [사용법](../evaluation/LANGSMITH.md)

- `python scripts/sync_law_graph.py --all`: Neo4j 인용 동기화 미리보기. `--apply`만 그래프에 저장하며 PG/임베딩은 변경하지 않습니다.
- `python scripts/audit_law_graph.py`: 저장 관계·항/호·원문 및 약칭 정의 버전의 일관성 검사.
- `python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft --limit 10`: 동일 시작 결과의 기본/Graph 비교. draft는 공식 통과 점수에서 제외하며 기본 필터는 ALL(정답 세목 주입 없음)입니다.
- Graph 확장의 추가 정답 발견을 동일 개수의 검색 정확도 향상으로 해석하지 않습니다. top-5 유지 여부와 추가 근거의 적합성은 구분합니다.

### 현재 쟁점 검색·답변 진단

다음은 백엔드 컨테이너 안에서 실행하는 읽기/공개 예제 진단이며 사용자 대화 DB에 결과를 저장하지 않는다.
실제 검색/생성 예제는 모델 호출·원격 비용이 발생할 수 있다. 결과 파일은 실행마다 새 경로를 지정한다.

```bash
python evaluation/issue_retrieval_probe.py /tmp/issue-baseline-NEW.json --all --no-algorithms
python evaluation/issue_retrieval_probe.py /tmp/issue-algorithms-NEW.json --all
python evaluation/search_algorithms_probe.py /tmp/typos-exact-NEW.json
python evaluation/index_repair_audit.py
python dev/probe_reliable_answer.py /tmp/answer-NEW.json general --warm-bm25
```

`compound`도 공개 복합 예제에 사용할 수 있다. 표시 재현은 결과의 `presentation_input`과
`frontend/tests/answerPresentation.browser.cjs`를 사용한다. 최종 JSON/PC·mobile PNG 위치는 HANDOFF를 따른다.
기존 39문항은 draft/dev다. 전용 Reranker는 아직 없으며 도입 설계는 [RAG_IMPROVEMENT_PLAN.md](../docs/ai/RAG_IMPROVEMENT_PLAN.md)에만 기록한다.

```bash
python scripts/evaluate.py validate --dataset evaluation/datasets/contracts.json
python scripts/evaluate.py run --split all
python scripts/evaluate.py suite --mode live --include-draft --output evaluation/runs/review-batch
```

평가 결과는 `evaluation/runs/`에 저장됩니다. 정답 파일은 자동으로 수정하지 않습니다.
종료 코드 0=선택 범위 통과, 1=실패, 2=미검수/미판정, 3=입력·실행 오류입니다.
구 평가 진입점 `eval_rag.py`·`eval_graph_rag.py`는 제거했습니다. `evaluate.py`는 얇은 진입점이며
인자 처리·실행 제어·종료 코드 처리는 `evaluation/cli.py`에 모았습니다. 과거 tests/eval 결과는 이력으로 보존합니다.
판정 규약과 검수 방법은 [evaluation/README.md](../evaluation/README.md)를 참고하세요.

## 실행 원칙

- 프로젝트 루트에서 실행합니다.
- DB를 사용하는 작업 전 `alembic upgrade head`를 적용합니다.
- `--embed`, 평가 `--mode live`, `--allow-generation` 작업은 해당 DB·서빙 엔진과 필수 모델이 준비돼 있어야 합니다.
- 자동화 대상은 종료 코드가 실패를 나타내는 `sync_laws.py`를 우선 사용합니다.
- `backfill_*`, `embed_clauses.py`는 일회성 또는 모델 변경 후 재처리용입니다.
