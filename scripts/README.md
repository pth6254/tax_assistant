# 운영·데이터 작업 CLI

이 디렉터리는 FastAPI 요청 처리 코드가 아니라 개발자·운영자가 프로젝트 루트에서 직접
실행하는 배치 작업의 진입점만 포함합니다. 핵심 로직은 `app/services/`에 두고, 스크립트는
인자 처리·진행 상황 출력·리소스 정리·종료 코드만 담당합니다.

## 데이터 수집·동기화

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

```bash
python scripts/eval_rag.py --build
python scripts/eval_rag.py --eval
python scripts/eval_rag.py --eval --with-answer --repeat 3
```

평가 결과는 `tests/eval/results/`에 저장됩니다. `--build`는 후보만 수집하며 골든 정답을
자동 확정하지 않습니다.

## 실행 원칙

- 프로젝트 루트에서 실행합니다.
- DB를 사용하는 작업 전 `alembic upgrade head`를 적용합니다.
- `--embed` 또는 `--with-answer` 작업은 Ollama와 필수 모델이 준비돼 있어야 합니다.
- 자동화 대상은 종료 코드가 실패를 나타내는 `sync_laws.py`를 우선 사용합니다.
- `backfill_*`, `embed_clauses.py`는 일회성 또는 모델 변경 후 재처리용입니다.
