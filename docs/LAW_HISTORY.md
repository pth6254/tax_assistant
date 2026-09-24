# 과거 법령 수집과 버전 관리

## 범위와 저장 원칙

현재 law_articles에서 is_current이며 공식 lsiSeq 원문 출처를 가진 법령을 최초 실행 시
law_history.scope에 고정한다. 법령해석례에 등장하는 타법 이름은 포함하지 않는다.
2026-09-22 확인: 41개 법령, 시행일 기준 목록 5,400개(연혁·현행·시행예정 합계).
API 제공 목록과 같은 수를 확보했는지를 검사하며 대한민국 전체 법령이나 모든 전신 법령 ID의
완전성을 보장하는 수치는 아니다. 공식 ID가 바뀐 전신·후신의 연결은 추가 검수 대상이다.

- Alembic revision: 20260922_0003. PostgreSQL law_history 스키마만 추가한다.
- scope: 대상·공식 ID·목록 예상 수·수집 상태. laws: 법령 식별자.
- versions: (law_id, MST, 시행일) 유일 키. 동일 공포본의 단계별 시행을 구분한다.
- snapshots: 정제 XML 원문·SHA256·수집일·파서 버전. 같은 본문은 멱등, 변경된 본문은 추가 저장.
- articles: 버전 스냅샷별 조문 번호/가지번호·제목·본문·XML 구조 JSON. 삭제 조문과 편장절관도 source_order로 보존.
- supplements: 부칙 원문·구조. 별표 링크/개정문/개정이유는 전체 XML에 보존하지만 첨부 PDF/HWP 다운로드는 미구현.
- runs: 실행·heartbeat·성공/실패 개수. coverage: 법령별 발견/저장/미수집/실패 뷰.
- version_sequence: 같은 법령의 시행일/공포일 순서상 이전 관측 버전. 법적 승계·적용 종료일의 확정이 아니다.

기존 law_articles와 임베딩, 현행 Neo4j 노드는 보존한다. 2026-09-24부터 별도 역사 임베딩 색인과
History* 그래프·버전 지정 채팅을 추가했다. 전체 임베딩은 진행 중이다. [역사 GraphRAG](HISTORY_RAG.md) 참고.
법률/시행령/시행규칙의 과거 관계 적용 확정·부칙 적용 판단은 후속 작업이다.
현행 검색에 과거 원문을 섞지 않는다. 시행일만으로 사건 적용 법령을 자동 확정하지 않는다.

## 실행

### 독립 수집기 및 자동 검수 (권장)

WSL 프로젝트 루트에서 `bash dev/law-history-wsl.sh start`로 실행한다.
WSL 가상환경을 활성화하고 독립 `law-history-worker` 이미지 빌드/기동만 수행한다.
DB 및 Alembic 스키마는 먼저 준비되어 있어야 한다. 채팅 API/모델을 재시작하지 않는다.

- `bash dev/law-history-wsl.sh status`: 실제 잠금, heartbeat, 수집 범위 및 실행 상태 확인.
- `bash dev/law-history-wsl.sh logs`: 최근 진행 로그. `stop`: 명시적 중지.
- 기본적으로 pending만 수집. 완료 건 보존, failed 자동 재수집 없음.
- 전체 목록 수 일치 및 pending/failed=0 확인 후 `evaluation.history_audit` 전체 검수 자동 실행.
- 보고서는 `evaluation/runs/law-history/audit-*.json`에 시각별 보존(Git/Docker 제외).
  `passed=true`는 저장 무결성 및 공식 표본 3개 대조 통과이며 법적 적용 정확도 인증이 아니다.
- opt-in `history` profile 사용. 일반 서비스 기동만으로 수집하지 않는다.
- 비정상 종료 시 Docker `on-failure:3` 정책으로 제한 재시작. 완료 시 종료한다.
  PC/WSL/Docker 자체 종료 또는 수동 stop 후 자동 부팅/재개는 보장하지 않는다.
  환경 복구 후 `start`로 이어받는다. 반복 실패는 원인을 확인하고 수동 조치한다.
- 상태의 `status`는 저장 기록, `observed_status`는 잠금/heartbeat 기반 관측값이다.
  잠금 없는 running은 interrupted, 잠금 있으나 180초 이상 진행이 없으면 unresponsive.
  unresponsive를 근거로 잠금을 강제로 해제하지 않는다. 조회는 DB 상태를 변경하지 않는다.
- 수집 종료 후 검수 중에는 수집 run이 complete여도 컨테이너는 실행 중이다.
  최종 완료는 최신 검수 보고서와 컨테이너 종료 코드로 확인한다.

WSL 프로젝트 루트에서 `source venv-wsl/bin/activate` 후 실행한다.
현재 Ollama 개발 서비스는 `bash dev/docker-up-wsl.sh`로 최신화한다.

```bash
docker exec tax_backend alembic upgrade head
# 최초에는 범위를 고정하고 전체 페이지를 탐색. 재실행은 미완료 법령만 처리.
docker exec tax_backend python scripts/collect_law_history.py discover
# 신규 개정 목록 확인: 기존 버전은 삭제하지 않음
docker exec tax_backend python scripts/collect_law_history.py discover --refresh
# 미수집 본문 순차 처리. 과거/현행 우선, 시행예정은 마지막.
docker exec tax_backend python scripts/collect_law_history.py collect
docker exec tax_backend python scripts/collect_law_history.py collect --limit 10
docker exec tax_backend python scripts/collect_law_history.py collect --retry-failed
# 정정 여부 확인. 기존 원문을 덮어쓰지 않고 변경 스냅샷 추가.
docker exec tax_backend python scripts/collect_law_history.py collect --refresh --version-id 1
# 진행 상황과 원문·비교 조회
docker exec tax_backend python scripts/collect_law_history.py status
docker exec tax_backend python scripts/collect_law_history.py versions --law-id 001565
docker exec tax_backend python scripts/collect_law_history.py show --version-id 1
docker exec tax_backend python scripts/collect_law_history.py diff --left 1 --right 2
```

diff는 같은 법령의 수집된 서로 다른 버전만 허용한다. 위 번호는 예시이며 versions 결과에서 선택한다.
비교 결과는 조문 본문 텍스트 차이이며 조문 이동/분할/통합의 법적 연속성이나 부칙 비교가 아니다.

백그라운드 시작: `docker exec -d tax_backend python scripts/collect_law_history.py collect`.
WSL이 유휴 종료되는 환경에서는 Windows에서 숨김 wsl 프로세스로 전경 `docker exec`를 유지하거나
WSL 터미널을 열어 두어야 한다. 이번 최초 전체 수집은 Windows 숨김 프로세스로 실행했다.
진행 상태는 status의 최신 runs와 coverage에서 확인한다. 전경/백그라운드 중복 실행은 DB advisory lock으로 차단한다.
컨테이너/WSL 재시작으로 작업이 중단되면 같은 collect 명령으로 재개한다. 자동 재시작 데몬은 아니다.
중단된 run은 다음 worker 실행 시 interrupted로 표시된다. heartbeat가 오래됐다고 임의 성공 처리하지 않는다.

API 요청 간 0.5초 간격, 통신/일부 HTTP 오류 최대 3회 재시도, 연속 본문 실패 5회면 중단한다.
개별 실패의 원문 예외/인증값은 출력하지 않고 오류 타입만 보존한다. 실패 건은 명시적 retry로 재시도한다.
CLI 코드 0은 해당 패스 종료(전체 완수 아님), 2는 부분 실패, 1은 실행 오류다.
전체 완료 판단에는 scope 전체 discovery_status, 예상/발견 개수 및 pending/failed=0을 함께 확인한다.

## DBeaver에서 확인

기존 PostgreSQL 연결을 새로고침하면 law_history 스키마가 보인다.

```sql
SELECT * FROM law_history.coverage ORDER BY law_name;
SELECT * FROM law_history.runs ORDER BY id DESC;
SELECT * FROM law_history.versions WHERE law_id='001565' ORDER BY effective_date;
```

## 공식 API 근거

- [시행일 기준 목록: LID, nw, 페이지](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdListGuide)
- [시행일 기준 본문: MST + efYd](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsEfYdInfoGuide)
- [연혁 API는 HTML 제공](https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=lsHstInfoGuide)

수집에는 eflaw XML을 사용한다. law/MST는 기존 수집 법령의 공식 ID를 확인할 때만 사용한다.
공식 ID·시행일·공포일을 목록과 대조하며 불일치/빈 응답은 실패 처리한다.
인증 OC가 포함될 수 있는 링크는 원문 저장 전에 정제한다.
