# 평가 파이프라인 구현 검증 — 2026-09-19

## 구현 결과

- 구 eval_rag/eval_graph_rag 산출 로직을 통합 실행기 `scripts/evaluate.py`와 `evaluation/` 패키지로 교체.
- 파싱·관계·검색·계산·도구 선택·고정 컨텍스트 답변 수집 어댑터, 관측 자료 import, 단계별 판정/검수/회귀 비교 지원.
- required/supporting/irrelevant/hard negative/미판정 분리, 조·항·호·버전 정확 일치, 미정의 gold와 실제 누락 구분.
- 데이터/코드/관측/검수 hash, 검수자·기준일·출처 필수 규약, split 누출 검사, 반례 검증 및 CI 계약 실행 추가.

## 실행 검증

WSL venv 활성화 후 기존 Ollama provider를 보존해 backend/frontend를 재빌드했다.
DB/모델 교체, 법령/벡터 삭제·백필, 채팅 GraphRAG 활성화는 하지 않았다.

| 확인 항목 | 결과 |
|---|---|
| 최신 이미지 전체 pytest | 460 passed, 2 skipped, 26 warnings, 5 subtests passed |
| 신규 평가기 테스트 | 29개 포함: 오답/반례, 미판정, 버전, 누출, 오류, 검수 hash, 보고서 등 |
| scorer 1.1 합성 파싱·관계·산술 | 22사례 통과, 각 오답 반례를 fail로 판정 |
| 실제 검색 | 39문항 × base/graph, 실행 오류 0, 최종 gate=incomplete |
| 실제 계산 입력 검증 | 음수 소득을 invalid_input으로 처리하고 정상 0원 결과를 반환하지 않음 |
| 실제 모델 도구 선택 | 입력 부족 질문에 none 선택, 해당 계약 통과 |
| 실제 모델 답변 생성 | 고정 합성 근거로 생성 성공, 인간 루브릭 검수 전이므로 incomplete |
| 오프라인 전체 suite | 합성만 pass, 미수집/미검수 영역은 incomplete 유지 |
| 작업 검사 | git diff --check 통과 |

CI workflow를 수정하고 동등한 검증 명령을 로컬/컨테이너에서 실행했다. GitHub 원격 CI 실행을 주장하지 않는다.

## 실제 검색 결과 해석

기존 39문항은 전부 draft/dev로 이관했고, 기대 조문번호가 있는 항목은 38개다.
ALL 필터·질문 단일 쿼리 조건에서 그 기대 조문 중 37개가 top-5에 있었다.
이 수치는 초안 라벨의 진단 값이며 공식 검색 성능/세무 정답률이 아니다.
기존 정답 세목 필터를 제공한 38/38 결과와 동일 조건 비교가 아니다.

반환 후보 231개를 중복 제거한 검수 목록으로 만들었다. 대부분의 후보가 아직 미판정이므로
판정된 일부 후보만의 precision을 전체 정확도로 발표하지 않는다. Graph의 새 필수 근거 발견은
이번 초안 라벨 범위에서 0개였고, 그 자체로 GraphRAG가 불필요하다는 결론도 내리지 않는다.
복합 질문의 필수 근거 집합과 불필요한 보조 근거를 더 검수해야 한다.

공개 원문/벡터/계산 기준/그래프 fingerprint는 당시 수집 전후 동일했다.
초기 계산 검증에서는 무관한 Neo4j 준비 전후 차이가 전체 gate를 incomplete로 만들었다.
이후 스냅샷 의존성을 단계별로 분리하여 계산은 계산 기준 테이블만,
고정 컨텍스트 답변·도구 선택은 데이터셋/코드/모델 메타데이터만 사용하도록 수정했다.

## 보존 위치

아래 폴더는 로컬 `evaluation/runs/`에 있고 Git/Docker 빌드에서 제외된다.

- `contracts-verified`: 최초 컨테이너 합성 계약 실행
- `retrieval-verified`: 실제 검색 관측/정답 스냅샷/후보 검수 목록
- `retrieval-rescored`: 동일 관측을 scorer 1.1로 재채점한 보고서. gold 미정의를 오답과 구분
- `calculator-ready-verified`, `tools-ready-verified`: 실제 컴포넌트 실행 결과
- `answer-ready-verified`: 실제 답변과 미작성 인간 루브릭 검수 양식
- `suite-offline-verified`: 미측정 영역이 pass로 처리되지 않는 통합 실행 확인
- `verified-v1-1`: 최신 Docker의 최종 합성 계약 실행

과거 `tests/eval/golden_qa.json`과 과거 결과 파일은 삭제하거나 정답을 덮어쓰지 않았다.

## 남은 범위

1. 공식 원문·기준일·예외와 대조한 인간 승인 gold/hard negative 및 독립 test 질문셋.
2. context/safety/performance는 관측 계약만 지원한다. 실제 제품 trace 자동 수집기와 전체 채팅 E2E 계측은 후속.
3. 답변 의미·법적 적용 판정은 인간 검수 대기. 이번 작업에서 자동으로 승인한 실제 세무 정답은 없다.
4. 임베딩/생성 가중치 digest, 부하 조건, 동일 토큰 예산, 검수자 간 일치도까지 포함한 실서비스 평가 확대.

판정 기준과 실행법: [README](README.md).
