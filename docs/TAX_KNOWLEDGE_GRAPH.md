# 버전별 세무 법령 Knowledge Graph

> 2026-09-26 검수 정정: 버전 3162·3163 제125조에서 보고된 XML/본문 불일치 2건은 원본 손상이 아니라, 같은 조문번호의 개정 지시문과 조문 본문을 마지막 행 하나에 대조한 검수기 오탐이었다. 이제 `source_article_id`로 원본 행을 대조한다. 관계 후보의 인간 검수 기준과 미승인 카드 생성법은 [KG 관계 검수](../evaluation/KG_RELATION_REVIEW.md)를 참고한다.

## 범위와 데이터 흐름

원본은 PostgreSQL `law_history`의 완성된 법령 버전·스냅샷·XML 구조다. Neo4j는 파생 색인이며 원문을 대체하지 않는다. 현재 **과거 법령 조회 경로**에 연결했다. 일반 현행법 채팅은 기존 조문 단위 CITES GraphRAG를 사용한다.

```text
HistorySnapshot ─HAS_KG_PROVISION→ TaxProvision(버전·조/항/호/목)
                                   └─CHILD_OF→ 상위 TaxProvision
TaxProvision ─SUBJECT_OF→ KnowledgeAssertion ─OBJECT→ TaxConcept | TaxReference
```

- `TaxProvision.key`는 스냅샷 ID와 정확한 조·항·호·목 참조로 만든다. 같은 조문번호라도 법령 버전이 다르면 별도 노드다. 같은 스냅샷에서 번호가 반복되면 발생 순서를 키에 추가해 서로 다른 원문이 덮어쓰이지 않게 한다. XML의 번호가 확인된 단위만 노드로 만든다.
- `TaxConcept`는 공식 법령 ID와 정의 용어로 구분한다. 현재는 해당 법령에서 따옴표로 명시한 `“용어”란` 형태만 정의 후보로 추출한다. 일반 키워드가 곧 법적 개념 관계라는 주장은 하지 않는다.
- `TaxReference`는 정식 법령명과 명시적 조문 인용을 담는다. 수집 단계에서 인용 대상의 시점·법적 적용을 확정하지 않는다. 검색 시 질문 기준일에 맞는 대상 버전을 다시 선택한다.
- `KnowledgeAssertion`은 `DEFINES` 또는 `CITES`, 정확한 출처 문구·해시·검수 상태를 가진다. 새 관계는 `candidate`이며 검색에 사용하지 않는다. `reviewed`만 검색 후보이고, 검색 시에도 PostgreSQL 원문·해시·XML 발췌를 다시 대조한다. `rejected`는 검색하지 않는다.
- 관계 검수 CLI는 원문 일치 여부를 기계적으로 확인하고 검수자 문자열을 기록한다. 이는 세법 전문가의 법적 의미 또는 사건 적용시점 검토를 대신하지 않는다.

## 적재와 검수

실행 중인 백엔드 컨테이너에서 수행한다. 수집 완료된 과거 버전 5,400개의 구조 노드·관계 후보 백필을 마쳤다. `sync`는 기본적으로 미리보기이고 `--apply`를 지정한 범위만 Neo4j에 기록한다. 기존 PostgreSQL 스키마는 바꾸지 않는다.

```bash
docker exec tax_backend python scripts/sync_tax_knowledge.py sync --version-id 306 --article '제1조의2'
docker exec tax_backend python scripts/sync_tax_knowledge.py sync --version-id 306 --article '제1조의2' --apply
docker exec tax_backend python scripts/sync_tax_knowledge.py candidates --version-id 306 --article '제1조의2'
docker exec tax_backend python scripts/sync_tax_knowledge.py review --key <assertion-key> --reviewer <reviewer-id> --approve
```

전체 과거 버전의 구조 노드와 관계 **후보**를 채울 때는 아래처럼 먼저 잔여 범위를 확인한다. `all --apply`는 버전별 원자적 `KnowledgeSync` 체크포인트를 기록하므로 중단 뒤 같은 명령으로 재개할 수 있다. 이 작업은 관계를 일괄 승인하지 않는다.

```bash
docker exec tax_backend python scripts/sync_tax_knowledge.py all
docker exec tax_backend python scripts/sync_tax_knowledge.py all --apply
docker exec tax_backend python scripts/sync_tax_knowledge.py audit
docker exec tax_backend python scripts/sync_tax_knowledge.py validate
docker exec tax_backend python scripts/sync_tax_knowledge.py repair-duplicates
# 범위를 확인한 뒤에만 중복 참조가 있는 스냅샷 재구성:
docker exec tax_backend python scripts/sync_tax_knowledge.py repair-duplicates --apply
```

`audit`는 수집 완료 스냅샷과 체크포인트의 집합, 기대/실제 노드·관계 수, 검수 상태를 비교한다. `validate`는 PostgreSQL 전체 원문을 다시 읽어 해시와 XML에서 추출한 발췌의 본문 포함 여부를 검사한다. 두 명령과 `repair-duplicates`의 기본 실행은 읽기 전용이다. 중복 보정은 승인 관계가 있는 스냅샷을 자동 교체하지 않는다. 자동 검사를 통과한 관계는 여전히 `candidate`이며 법적 의미를 검토해 승인한 관계만 RAG에 사용한다.

틀린 후보는 `review` 명령의 `--approve` 대신 `--reject`로 표시한다. 승인 전에는 실제 원문·인용 대상·정의 문맥을 사람이 검토해야 한다. 재동기화는 기존 검수 상태를 보존한다. 원문/해시가 바뀌면 검색 시 관계를 배제한다.

## 검색 연결 및 검증

`HISTORY_GRAPH_RAG_ENABLED=true`인 과거 법령 조회에서 선택된 버전의 검수된 정의를 질문 용어와 대조한다. 예를 들어 `비거주자`는 부분 문자열 `거주자` 정의와 혼동하지 않는다. 검수된 명시적 인용은 출처 문구가 실제 검색 발췌에 포함될 때만, 대상 법령의 동일 기준일 버전과 항·호·목이 확인되면 보충 근거로 사용한다. Neo4j 장애·시간 초과 때는 기본 과거법령 근거를 유지한다. 관계가 있다는 사실만으로 사건에 적용할 법령이라고 판단하지 않는다.

2026-09-25 전체 적재: 수집 완료된 스냅샷 **5,400/5,400**, 조문 레코드 **1,038,278**, 버전별 조·항·호·목 노드 **6,924,423**, 고유 정의·인용 관계 **1,313,901**. `audit`에서 누락/초과 체크포인트 0, 기대/실제 노드·관계 수 일치를 확인했다. 조문이 없는 개정 부칙·별표 중심 버전 1개도 조문 0건으로 정확히 기록했다. 같은 번호가 반복된 101개 스냅샷의 구조 단위 1,734개는 발생 순서를 분리해 재구성했다.

시범적으로 소득세법 버전 306의 `제1조의2`에서 `거주자`, `비거주자` 정의와 `법인세법 제2조 제1호` 명시적 인용 3개만 원문 일치 검수 후 승인했다. 다른 **1,313,898개는 candidate**로 남아 RAG 근거로 자동 사용되지 않는다. 버전 지정 검색에서 승인된 정의·인용 보충을 확인했지만 전체 세무 정답률을 평가한 결과는 아니다.

2026-09-26 수정 검수기로 전체 5,400개 버전을 다시 대조한 결과 해시·파싱 오류 0건, XML 발췌/원본 행 본문 불일치 0건이다. 이전에 보고된 버전 3162·3163 `제125조`의 2건은 조문번호만으로 마지막 행과 비교한 오탐이었다. 다만 같은 번호의 개정 지시문과 본문 조문이 공존하므로 승인·조회 시 모호한 원문을 임의로 고르지 않는다. 개정 지시문의 법적 효력은 별도 검수 대상이다.

현행 `law_articles`의 일부 조문은 역사 XML보다 항·호 본문이 적거나 갱신 시점이 달라, 현재 버전 Knowledge Graph로 무비판적으로 연결하지 않는다. 현행 원문 동기화·시점 대조를 먼저 보정해야 한다.
