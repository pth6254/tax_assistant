# 운영·데이터 작업 CLI

이 디렉터리는 FastAPI 요청 처리 코드가 아니라 개발자·운영자가 프로젝트 루트에서 직접
실행하는 배치 작업의 진입점만 포함합니다. 핵심 로직은 `app/services/`에 두고, 스크립트는
인자 처리·진행 상황 출력·리소스 정리·종료 코드만 담당합니다.

## 데이터 수집·동기화

- `python scripts/collect_law_history.py discover|collect|status|versions|show|diff`: 현재 수집 법령의 과거 버전 아카이브. 기존 검색 데이터와 분리하며 실행·재개·한계는 [과거 법령 관리](../docs/LAW_HISTORY.md)를 참고한다.
- 독립 수집·자동 전수 검수는 `bash dev/law-history-wsl.sh start`로 기동한다. `scripts/run_law_history_worker.py`는 해당 컨테이너의 배치 진입점이며 보고서는 `evaluation/runs/law-history/`에 보존한다.
- 역사 임베딩/그래프는 `scripts/index_law_history.py prepare|graph|embed|all|status`와 `dev/history-index-wsl.sh`로 별도 실행한다. 실행·준비 상태·재개 규칙은 [역사 GraphRAG](../docs/HISTORY_RAG.md)를 참고한다.

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

백필을 실행하기 전에 반드시 `alembic upgrade head`가 완료돼 있어야 합니다. 백필 스크립트는
스키마를 만들지 않으며 Alembic revision을 대신하지 않습니다.

## 품질 평가

- `python scripts/evaluate.py langsmith prepare ...` / `langsmith publish ...`: 자체 대시보드 대신 LangSmith에서 평가 조회·비교·검수. 기본 전송 계획은 본문 제외이며 확인한 해시에 한해서 업로드합니다. [사용법](../evaluation/LANGSMITH.md)

- `python scripts/sync_law_graph.py --all`: Neo4j 인용 동기화 미리보기. `--apply`만 그래프에 저장하며 PG/임베딩은 변경하지 않습니다.
- `python scripts/audit_law_graph.py`: 저장 관계·항/호·원문 및 약칭 정의 버전의 일관성 검사.
- `python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft --limit 10`: 동일 시작 결과의 기본/Graph 비교. draft는 공식 통과 점수에서 제외하며 기본 필터는 ALL(정답 세목 주입 없음)입니다.
- Graph 확장의 추가 정답 발견을 동일 개수의 검색 정확도 향상으로 해석하지 않습니다. top-5 유지 여부와 추가 근거의 적합성은 구분합니다.

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
