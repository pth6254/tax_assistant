# 선택형 Neo4j GraphRAG (1차 구현)

평가 실행기는 후속 리팩토링으로 `scripts/evaluate.py`에 통합됐다.
`python scripts/evaluate.py run --dataset evaluation/datasets/retrieval.json --mode live --include-draft`로
후보 검수를 진행한다. 아래 과거 검증 기록의 38/38은 당시 정답 세목 필터를 제공한 검색 결과이며,
새 평가의 ALL 필터·draft/unknown/hard-negative 판정과 직접 비교하지 않는다. [평가 규약](../evaluation/README.md)

## 2026-09-19 검색 연결 고도화

누락된 config·검색 결과 메타데이터·기본 Compose Neo4j 서비스·Python 의존성을 복구했다.
일반 hybrid_search의 단일/복수 쿼리 모두 기본 순위 확정 뒤 선택형 Graph 확장을 호출한다.
코드 기본값은 false이며, 2026-09-19 사용자 요청으로 로컬 `.env`를 true로 설정하고 앱을 재배포했다.
일반/SSE 채팅의 검색 근거에 반영한다. 원문 단독 조회·문서 도구는 기존 분리 경로를 유지한다.
별도 관계도 UI는 없으며 활성화 자체가 정확도 개선을 검증했다는 뜻은 아니다.

```text
pgvector 검색 + 직접 조문 조회 → 기본 상위 5개 유지
  → 상위 3개 공식 조문의 버전 검증
  → Neo4j CITES 인용 / 같은 법령 계열의 역방향 인용 1-hop
  → 후보 최대 24개 → 현재 원문·약칭 정의 버전 + 키워드 관련성 검증
  → 최대 2개 / 추가 본문 합계 4,000자 → 기존 생성·인용 검증
```

약칭은 원문 전체에서 유일한 `「법령명」(이하 "법"/"영"이라 한다)` 정의를 찾고
저장된 법률·시행령·시행규칙의 정확한 계열명과 대조한다. Neo4j의 예전 계열 노드만 믿고
추측하지 않는다. 정의 조문의 뒤부터 적용하며 중복/지역적 정의는 보수적으로 제외한다.
관계에 정의 조문번호·법령명·버전 해시를 저장하고 검색 시 PostgreSQL 원문과 다시 대조한다.
`같은 법`, `같은 조`, `전항`, 범위·생략 목록, 위임/준용의 법적 의미는 여전히 추론하지 않는다.

역방향은 다른 계열을 제외한다. 키워드는 단순 문자열 필터이며 의미 기반 리랭커가 아니다.
긴 추가 조문은 조건을 중간에서 자르지 않고 제외한다. 4,000자는 **추가** 본문 제한이지
기본 RAG와 프롬프트를 합친 전체 모델 토큰 예산 보증이 아니다.
원문 조회 도구가 일반 RAG를 생략하는 경로와 제품 UI 관계도는 이번 변경 대상이 아니다.

저장 결과: 6,675개 조문 / 8,387개 고유 CITES / 26개 시행령·시행규칙 약칭 지원.
기존 2,464개에서 늘어난 관계는 약칭 인용이며 법적 위임 확정 관계로 표시하지 않는다.
2026-09-19 관측 스냅샷을 추가했고 기존 계열/과거 스냅샷은 삭제하지 않았다.
미해결 참조 6,275건은 대상 미수집 또는 항·호 본문 확인 실패 등을 포함한다.
검색 실험 및 활성화 판단은 [검증 기록](GRAPH_RAG_VALIDATION_2026-09-19.md)을 참고한다.

## 법령 계열 관계

전체 저장 계열은 `python scripts/sync_law_family.py --all`로 점검하고 `--apply`로 저장한다.
이름이 정확히 대응하는 법률/시행령/시행규칙 3종을 Neo4j에서 탐색하고 공식 API로 검증한다.
목적 조문의 `「상위법」 및 같은 법 시행령`/`동법 시행령`, 명시적 법/영 약칭 정의도 증거로 허용한다.
목적 근거는 purpose_verified, 약칭 정의 근거는 alias_verified로 구분한다. 이 계열 CLI 자체는 일반 본문 생략 참조를 해석하지 않는다.
완전한 3종 계열이 아닌 자료는 unmatched로 보고하며 없는 법령 원문을 자동 수집하지 않는다.
2026-09-13 전체 적용: 13계열/TaxLaw 39개/계열 관계 39개/HAS_ARTICLE 6,546개, 실패·중복 0.
국세청·관세청 직제 시행규칙은 상위 직제 원문 미저장으로 미연결(129개 조문). 기존 소득세법만 적용했던 상태를 대체한다.

`scripts/sync_law_family.py --law '소득세법'`은 공식 API의 정확한 이름·법령ID·제1조 목적을 확인하는 미리보기다.
`--apply`로 검증된 계열을 저장한다. 이름만 일치하거나 목적 조문에 상위 법령 인용/위임 문구가 없으면 실패한다.
이 규칙은 모든 법령 형식의 범용 판정기가 아니며 미확정 계열은 수동 검수가 필요하다.

- `TaxLaw(law_id)`는 버전과 독립적인 법령 식별자다. `HAS_ARTICLE`은 기존 `TaxArticle` 버전 노드의 소속이며 현행성 보증은 아니다.
- 법률→시행령 `HAS_ENFORCEMENT_DECREE`, 법률→시행규칙 `HAS_ENFORCEMENT_RULE`, 시행령→시행규칙 `HAS_IMPLEMENTING_RULE`.
- 관계에 목적 원문, 공식 출처/MST, 증거 버전 공포·시행일, 기록시각, `purpose_verified` 상태를 저장한다.
- 이는 개별 조문의 위임/준용 연결이나 법적 적용기간 확정이 아니다. 증거 버전 날짜를 계열 관계 전체의 유효기간으로 사용하지 않는다.
- 최초 소득세법 1계열 적용 이후 전체 13계열로 확대했다(위 전체 적용 기록 참고).
- 계열 관계 자체는 시점 스냅샷/채팅 탐색에 포함하지 않는다. 별도의 원문 약칭 검증기가 CITES를 추가한다.
- 법령 원문 갱신으로 새 조문 버전이 생기면 해당 계열 CLI를 명시적으로 재실행해야 한다. 전체 graph sync는 계열을 자동 갱신하지 않는다.

Neo4j Browser에서 계열 조회:

```cypher
MATCH p=(l:TaxLaw {law_name:'소득세법'})-[:HAS_ENFORCEMENT_DECREE|HAS_ENFORCEMENT_RULE|HAS_IMPLEMENTING_RULE*1..2]->(:TaxLaw)
RETURN p
```

## 시점 관리 1단계: 관측 스냅샷

`sync_law_graph.py --all --apply`는 기존 현행 CITES 동기화 후 한국시간 당일의 전체 그래프 스냅샷도 저장한다.
`--law` 부분 동기화에는 스냅샷을 만들지 않는다. 두 저장은 별도 트랜잭션이며 스냅샷 실패 시 CLI가 실패로 종료된다.
재실행은 안전하지만 기존 현행 그래프가 먼저 갱신됐을 수 있다. PostgreSQL 스키마/임베딩 변경은 없다.

- `TaxGraphSnapshot`: 관측일 `observed_on`, 최초 기록시각 `recorded_at`, 범위, 개수, 콘텐츠 해시.
- `TaxTemporalArticle`: 스냅샷별 조문 메타데이터 사본, 원문 버전 해시 `version_key`, 공포일 `published_on`, 법령 버전 시행일 `effective_on`.
- `HAS_VERSION`/`CITES_AT`: 해당 스냅샷의 조문과 인용 관계. 기존 `TaxArticle`/`CITES`와 분리하여 이후 동기화가 과거 관계를 지우지 않는다.
- 동일 날짜·동일 내용은 중복 저장하지 않는다. 같은 날짜에 내용이 달라지면 별도 스냅샷을 보존하고 조회 시 그날 마지막으로 새로 기록된 스냅샷을 선택한다.
- 공포일/시행일이 없거나 잘못됐거나 관측일 이후이면 제외한다. 공포일이 시행일보다 늦은 소급입법도 공포 전에는 관측하지 않은 것으로 처리한다.

```bash
docker exec tax_backend python scripts/query_law_graph.py --as-of 2026-09-13 --law '소득세법' --article '제26조'
```

조회 결과는 UI 연결용 nodes/edges JSON이다. 지정한 날짜의 기록이 없으면 `status=unknown`,
`reason=no_snapshot_for_date`이고 가까운 날짜/현재 그래프로 대체하지 않는다. 최대 100개 인용, 기본 50개이며 잘림 여부를 반환한다.
연결 없는 조문도 반환한다. 조회는 조 단위·출발 조문의 outgoing 1-hop이며 제품 UI/채팅에는 아직 연결하지 않는다.

**관측일은 법적 적용기간이 아니다.** `basis=observed_snapshot`, `legal_applicability_verified=false`를 항상 반환한다.
현재 DB의 현행 표시나 법령 단위 시행일만으로 조문별 valid_from/valid_to를 만들어내지 않는다.
기록 없는 과거의 원문, 개별 조문 시행 특례, 폐지일, 부칙 경과조치는 별도 수집/검증이 필요하다.
스냅샷은 원문 전문을 복제하지 않으므로 과거 원문 뷰어에는 PostgreSQL의 버전 보존/조회 강화도 필요하다.
매일 자동 수집/스냅샷을 실행하는 스케줄러는 추가하지 않았다. 저장량 증가에 대한 보존 정책도 후속 과제다.

기존 PostgreSQL·pgvector 검색을 유지하고 Neo4j의 명시적 인용 관계를 한 단계 탐색한다.
기본값은 비활성이다. Microsoft GraphRAG의 LLM 추출·커뮤니티 요약 방식이 아니라,
고정 Cypher를 사용하는 도메인 특화 검색 확장이다.

## 실행

2026-09-13부터 Neo4j는 기본 `docker-compose.yml`에 포함된다(`tax_neo4j`).
일반 `bash dev/docker-up-wsl.sh`로 전체 실행하면 Neo4j도 시작한다.
별도 Graph Compose나 전용 실행 셸 없이 기본 Compose를 사용한다.
서비스를 지정해 `... backend`만 실행하면 Neo4j는 새로 시작하지 않는다.
**기본 Compose 설정 해석에도 NEO4J_PASSWORD가 필요하다.** 기존 컨테이너는 설정 파일 수정만으로 바뀌지 않는다.

`.env`에 강한 별도 `NEO4J_PASSWORD`를 설정한다. 값을 Git에 올리거나 터미널 출력에 남기지 않는다.
`GRAPH_RAG_ENABLED=false`로 먼저 시작해 동기화 결과를 확인한다.

```bash
source venv-wsl/bin/activate
bash dev/docker-up-wsl.sh
docker exec tax_backend python scripts/sync_law_graph.py --all
# 위 명령은 읽기 전용 미리보기. 범위를 확인한 뒤에만 아래 실행:
docker exec tax_backend python scripts/sync_law_graph.py --all --apply
```

특정 법령만 시험하려면 `--all` 대신 `--law '소득세법'`을 사용한다.
이 경우 범위 밖 법령 참조는 미해결로 집계되고 연결되지 않는다.
CLI는 PostgreSQL에 쓰거나 임베딩 모델을 호출하지 않는다.

현재 Compose의 Windows Ollama 별칭은 `OLLAMA_WINDOWS_IP` 환경변수를 요구한다.
직접 Compose를 실행하려면 현재 WSL Windows 게이트웨이를 export해야 한다. 스크립트는 이를 자동 처리한다.
검토 후 `.env`의 `GRAPH_RAG_ENABLED=true`로 변경하고
`bash dev/docker-up-wsl.sh backend`로 백엔드를 재생성한다.
중단은 `bash dev/docker-down-wsl.sh`: 그래프 볼륨도 보존한다.
즉시 검색 확장만 해제하려면 false로 변경하고 실행 스크립트로 backend를 재생성한다.

Neo4j Browser는 로컬 `http://localhost:7474`에서 제공한다. 사용자명은 `neo4j`다.
그래프 보기는 다음 읽기 전용 쿼리로 가능하다. 제품 프런트엔드 관계도는 아직 구현하지 않았다.

```cypher
MATCH (s:TaxArticle)-[r:CITES]->(t:TaxArticle)
RETURN s, r, t LIMIT 50
```

## 저장과 검색

- 노드: 법령명·조문번호·시행일·개정일, 제목/본문/버전으로 계산한 해시 키.
- 관계: `CITES`, 원문 근거 문구·정규화된 참조. 항·호·목 참조는 기존 본문 파서로 존재 확인.
- 인용 추출: 전체 법령명 인용과 위에서 설명한 검증된 법·영 약칭을 지원한다.
- 조 가지번호와 항·호·목은 기존 파서를 재사용한다. 법률·시행령·시행규칙 모두 동일하게 처리한다.
- 현행 행 중 유효한 시행일이 있고 이미 시행된 데이터만 색인한다.
- 기존 상위 결과 3개 중 공식 조문만 시작점으로 사용한다. PDF는 제외한다.
- 후보 관계 최대 24개, 중복 없는 추가 조문 최대 2개/총 4,000자. 기존 결과 순서를 유지한다.
- 추가 조문은 벡터 점수를 위조하지 않고 0으로 표시하며 컨텍스트에 관계 근거임을 명시한다.
- 검색 시 양쪽 원문 해시를 PostgreSQL과 대조한다. 갱신/삭제된 대상은 건너뛴다.
- 총 확장 시간 3초. 오류 시 기존 결과 유지, 취소는 전파한다. 예외 원문은 로그에 출력하지 않는다.
- 과거/특정 연도 질문은 보수적 패턴으로 확장을 생략한다. 완전한 시점 판정기가 아니다.

## 동기화 정책·제한

동일 원문 버전의 재동기화는 관계를 중복 생성하지 않으며 해당 버전의 outgoing 관계만
트랜잭션으로 교체한다. 바뀐 원문은 새 노드가 된다. 예전 노드는 자동 삭제하지 않지만
검색 시 현행 원문 해시 대조를 통과하지 못하므로 사용하지 않는다. Browser에는 과거 노드도 보인다.
전체 동기화는 메모리 내에서 후보를 만들고 단일 트랜잭션으로 저장하므로 대규모 자료에는
스냅샷 단위 배치/활성화 방식이 후속 과제다. PostgreSQL 스키마 변경은 없어 Alembic revision은 없다.

미해결 참조는 현재 개수만 보고하며 별도 보관 UI는 없다. 같은 법·전항·조문 범위·생략 목록,
위임·준용의 법적 의미, 원문 정의로 확인되지 않은 별칭, 과거 시점의 적용 법령은 추론하지 않는다.
원문에 대한 인용 관계는 해당 질문에 적용된다는 의미가 아니다. 오래된 원문 누락도 해결하지 않는다.
자동 법령 수집과 동기화 스케줄 연결, 제품 UI, 독립 graph dependency 상태 API,
복합 질문용 검색 정답셋과 답변 품질 A/B 평가는 후속 작업이다. 기존 골든셋 검색 비교만으로 정확도 개선이나 운영 준비 완료를 주장하지 않는다.

## 검증

최초 전체 적재 결과와 검수 한계: [2026-09-13 검수 기록](GRAPH_AUDIT_2026-09-13.md).
저장 후 전체 읽기 전용 감사: `docker exec tax_backend python scripts/audit_law_graph.py`.

```bash
pytest -q tests/test_graph_rag.py tests/test_docker_down_script.py
source venv-wsl/bin/activate
python -m pytest -q tests/integration --run-neo4j
python -m pytest -q tests/integration --run-neo4j --graph-real-sample
```

통합 테스트는 tests/integration/test_neo4j_graph.py와 같은 폴더의 conftest.py에 있다.
일반 pytest에서는 skip하며 Docker를 호출하지 않는다. WSL 호스트에서 --run-neo4j를 명시하면
별도 임시 Neo4j에 합성 법령을 저장하고 실제 조회·중복 방지·관계 교체를 확인한다.
무작위 비밀번호는 프로세스에만 유지한다. 자신의 임시 컨테이너·익명 볼륨은 종료 시 제거하며
다운로드한 Neo4j 이미지는 보존한다. 기존 PostgreSQL·다른 프로젝트는 변경하지 않는다.
`--graph-real-sample`은 실행 중인 `tax_backend`에서 공개 법령을 읽어 관계 최대 20개만 임시 Neo4j에 검증한다.
Docker CLI와 접근 권한이 있는 WSL 호스트에서 실행하며 backend 컨테이너에 Docker 소켓을 마운트하지 않는다.
기존 dev 검증 스크립트는 통합 테스트로 대체하여 제거했다. 원본 DB 데이터와 임베딩은 수정하지 않는다.

구현 참고: [Neo4j 비동기 드라이버](https://neo4j.com/docs/python-manual/current/concurrency/),
[Docker 실행 문서](https://neo4j.com/docs/operations-manual/current/docker/introduction/).
