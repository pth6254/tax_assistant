# 과거 법령 임베딩·GraphRAG

## 구현 범위

원본은 PostgreSQL `law_history`에 유지한다. 현행 `law_articles`와 기존 벡터·Neo4j 노드를 덮어쓰지 않는다.
Alembic `20260924_0004`가 파생 텍스트·청크·임베딩·그래프 체크포인트 테이블을 추가한다.

- 조문 1,038,278개 → 중복 제거 본문 84,529개. 편장절관 표제는 원본에 보존하되 검색 색인에서 제외한다.
- 부칙까지 포함한 고유 본문 90,935개 → 1,200자/100자 중첩 청크 127,838개.
- 동일 본문/청크는 벡터를 공유하지만 조문·부칙의 원래 버전별 소속은 보존한다.
- 모델 규격: 기존 provider-neutral embedding facade, 2560차원. 모델/provider/version/색인 규격을 model_key에 저장한다.
  같은 모델 태그 아래 가중치를 교체하면 history-body-v1 규격도 명시적으로 올리고 전체 재색인해야 한다. 가중치 자동 변경 감지는 아니다.
- 벡터는 배치마다 원자적으로 저장하고, 중단 시 미완료 청크부터 재개한다. 실패 배치는 기록 후 중단한다. 실패 재처리는 명시적인 `--retry-failed` 옵션이다.

## 그래프 구조

```text
HistoryLaw ─HAS_VERSION→ HistoryVersion ─HAS_SNAPSHOT→ HistorySnapshot
                            │                            │
                 PREVIOUS_OBSERVED_VERSION             HAS_UNIT
                            ↓                            ↓
                       이전 관측 버전                HistoryText
                                                        │ MENTIONS
                                                        ↓
                                                   HistoryLawName
                                                        │ IDENTIFIES (ID가 유일할 때)
                                                        ↓
                                                    HistoryLaw
```

`HAS_UNIT`은 조문번호·가지번호·제목·원문 순서·article/supplement 구분을 보존한다.
`MENTIONS`는 원문에 명시된 정식 법령명과 조·항·호·목 인용이다. 법적 위임/적용 확정 관계가 아니다.
`PREVIOUS_OBSERVED_VERSION`도 관측 순서일 뿐 법적 승계·효력 종료일의 확정이 아니다.
기존 TaxLaw와 공식 ID가 같은 HistoryLaw만 SAME_OFFICIAL_LAW로 연결한다.
기존 법률–시행령–시행규칙 계열 관계를 과거에도 유효한 관계로 자동 승격하지 않는다.

현재 과거 그래프는 정식 법령명 인용만 색인한다. `법`/`영` 약칭·같은 조·생략 참조의 과거 버전별 해석은 후속이다.

## 채팅 검색 경계

- 연도·날짜·법령버전 ID 또는 과거 법령 표현이 있으면 별도 history_lookup 경로를 사용한다.
- `2019-11-26 기준 지방세징수법 제16조를 설명해줘` 또는 `법령버전 1063 제16조 원문을 설명해줘`.
- 날짜 조회는 해당 일자 이전 공포·시행 목록 중 시행일이 가장 최근인 후보를 찾는다. 사건 적용 법령의 확정이 아니다.
- 같은 시행일 복수 버전은 공포일순으로 임의 선택하지 않고 후보 ID를 보여 주며 선택을 요청한다. 연도만 있거나 날짜가 여러 개면 정확한 기준일을 요청한다.
- 조문번호가 있으면 해당 스냅샷의 조·항·호·목을 직접 검증한다.
- 번호 없는 의미 검색은 선택한 버전의 **조문과 부칙 전체** 벡터가 준비된 경우만 실행한다. 미완료를 검색 실패나 규정 부재로 표현하지 않는다.
- 현재 버전/PDF/웹 검색을 섞지 않는다. 현행 질문은 기존 RAG 경로를 유지한다.
- 역사 그래프는 `HISTORY_GRAPH_RAG_ENABLED`로 제어한다. 코드 기본값 false, 사용자 요청에 따른 Compose backend 기본값 true. 기존 `GRAPH_RAG_ENABLED`와 분리한다.
- 그래프 후보는 같은 기준일의 대상 버전과 항·호·목 존재를 다시 확인한다. 원문 스냅샷 해시와 인용 문구도 PG에 대조한다. 최대 2개 추가, 시간 제한/오류 시 역사 기본 근거만 유지한다.
- 답변은 검증 가능한 원문 인용문과 source ID를 반환하는 구조화 생성이다. 인용문이 실제 근거에 없으면 요약을 보류한다. 설명의 법적 의미까지 자동 인증하지는 않는다.
- 프런트엔드는 history_lookup 카드를 표시하고 버전별 공식 링크를 사용한다. 현행 조문 뷰어 버튼으로 바꾸지 않는다.
- 역사 응답은 검증 완료 후 본문을 한 번에 전달한다. 도구 상태는 SSE로 전송하지만 토큰 단위 생성 스트리밍은 하지 않는다.

## 운영

WSL 프로젝트 루트에서 실행한다. 각 스크립트는 venv-wsl을 활성화하고 Windows Ollama 주소를 탐지한다.

```bash
bash dev/history-index-wsl.sh build
bash dev/history-index-wsl.sh migrate
bash dev/history-index-wsl.sh start
bash dev/history-index-wsl.sh status
bash dev/history-index-wsl.sh logs
bash dev/history-index-wsl.sh stop
```

indexer는 준비 → 그래프 → 임베딩 순으로 진행한다. 그래프는 벡터 없이 만들 수 있어 먼저 적재한다.
이미 완료한 원문/벡터/그래프 체크포인트는 재사용한다. PC/WSL 종료 후 start 명시 재개가 필요하다.
on-failure:3은 제한적인 프로세스 복구이며 OS 자동 부팅이나 무한 재시도 기능이 아니다.
12GB GPU에서는 대량 임베딩과 생성 모델의 동시 요청이 응답 지연·모델 교체를 유발할 수 있다. 배치는 비사용 시간에 실행하거나 stop으로 중지할 수 있다.

```bash
# 전체 그래프 소속 대조 (읽기 전용)
bash dev/history-index-wsl.sh audit
# 테스트 및 실제 로컬 모델 스모크 (대화 DB 저장 없음)
bash dev/history-index-wsl.sh test
bash dev/history-index-wsl.sh smoke
# 특정 버전 벡터를 우선 준비 (전체 indexer를 먼저 stop)
bash dev/history-index-wsl.sh embed-version 529
```

벡터 완성 판단은 `chunks == embedded`, `failed == 0`, `unprepared == 0`을 함께 확인한다.
PG의 graph_progress는 체크포인트다. Neo4j 데이터를 외부에서 삭제한 경우 그 값만으로 완성이라고 판단하지 말고 audit를 실행해야 한다.
외부 변경 후 그래프 재구축용 checkpoint 보정은 범위를 확인해 별도 진행한다. 현재 CLI는 원본/그래프 전체 삭제 명령을 제공하지 않는다.

## 2026-09-24 검증 결과

- Neo4j 5,400 스냅샷 전체 소속 집합/중복/버전 ID/원문 해시 대조 통과. MENTIONS 86,552개.
- 백엔드 최신 배포 이미지 561 passed/2 skipped, 프런트엔드 8 passed 및 Docker build 성공.
- 실제 GraphRAG: 지방세징수법 버전 1063 제16조 → 지방세기본법 버전 1012 제75조, 1개 추가 근거 및 로컬 생성 확인.
- 소득세법 1949년 버전 529 전체를 우선 임베딩, 번호 없는 납세의무 질의에서 제1조·제2조·제55조·제49조·부칙 검색 확인.
- 2026-09-25 전체 임베딩 127,838/127,838, 실패 0, 미준비 텍스트 0. 마지막 실패 8개를 `--retry-failed --limit 8`로 재처리하고 indexer 정상 종료 코드 0을 확인했다. 위 표본 성공과 백필 완료는 전체 검색 품질 평가가 아니다.
- 원시 그래프 검수: evaluation/runs/law-history-index/graph-20260923T160048.json. 스모크도 해당 폴더에 기록하며 backend 직접 실행분은 컨테이너 내부에 있다.
- 동일 시행일 474개 묶음의 법적 적용, 과거 법령 별표 첨부, 법령 ID가 바뀐 전신·후신 연결, 전문가 평가/골든셋 검증은 미완료다.
