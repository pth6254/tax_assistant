# 세션 인수인계

맨 위의 "현재 인계"는 항상 최신 하나만 둔다. 세션을 마칠 때 덮어쓰고, 이전 내용은 아래 날짜별 세션 기록으로 내린다.
작성 형식과 다른 문서와의 역할 구분은 [AGENTS.md](../../AGENTS.md#문서-역할과-작성-형식)를 따른다.

## 현재 인계 — 2026-10-08

**현재 상태**: 세 작업(날짜+법령명 질문의 경로, 질문 사실에의 적용 지시, 사건 당시 법령 버전 연결)이 `main`(`4ca5af3`,
`bf3c83a`, 문서 커밋)에 커밋되고 이미지로 재빌드돼 서비스에 반영돼 있다. 원격 `origin/main`은 `c2affff`로, 푸시하지 않았다.
이 변경들이 실제 답변을 좋게 하는지는 실모델로 확인하지 않았다. 사용자는 웹에서 10-07 변경 후 답변이 "전보다 많이 좋아졌다"고
판단했다(정성, 질문 수 미기록). 검증 수치는 [CURRENT_STATUS.md](CURRENT_STATUS.md), 결정은 [DECISIONS.md](DECISIONS.md)에 있다.
커밋은 `main`에 직접 하고 푸시는 요청이 있을 때만 한다.

### 다음 작업

| # | 작업 | 실모델 비용 |
|---|---|---|
| 1 | 웹에서 확인한다(이미지는 재빌드돼 있다). 확인점: ① 날짜와 법령명이 있는 분석 질문이 쟁점 계획으로 가는지(예: "2024년 6월 거래, 소득세법 기준으로 … 설명해 주세요") ② 사실관계를 준 질문에서 일반 규칙과 별도로 사실 적용 주장이 나오는지 ③ 과거 연도 사건(예: 2024년 6월 1일 증여)에서 "사건일에 시행 중이던 법령 시행본" 안내와 함께 법적 결론이 나오는지, 근거 목록에 "(YYYY-MM-DD 시행본)"이 보이는지 | 있음(질문 몇 개) |
| 2 | 사건 당시 버전 연결의 남은 범위: 부칙의 적용례·경과조치·조문별 시행일, 조문 번호가 바뀐 경우(현행 조문 번호로만 찾음), 계획 단위 날짜(한 질문에 취득·양도처럼 날짜가 여럿이면 모든 날짜를 덮어야 해서 결론이 막힌다)를 주장 단위 날짜로 바꾸는 설계 | 없음(설계·구현) |
| 3 | (선택) Judge가 `server_flags`를 신호별로 명시 답변하게 하고 답하지 않으면 차단(`flag_checks`) | 없음(구현), 효과 확인은 있음 |
| 4 | 같은 고정 카드 3개를 **새 출력 폴더**에서 `auto run` → `auto compare`·`auto blocks`·`auto filters`로 수정 전후 비교 | 있음(질문 3개) |
| 5 | 자동 카드 기본 30개(6세목 × 5유형) 실제 생성·평가, 이후 `auto filters --judge` | 있음(큼) |
| 6 | 독립 정확성: R2 혼동 근거 라벨, G1 관계 원문 감사, T1 독립 숫자 기대값, 전문가 holdout, Judge 오답 통과/정상 차단 검수 | 일부 |
| 7 | 데이터·검색 잔여: 원문 의심 27행, 연결 보류 인용 4,952개, 빈 벡터 metadata 입력 이력, Reranker([제안](RAG_IMPROVEMENT_PLAN.md)), `auto blocks`의 `repeats` 집계, 법 이름 라벨("소득세"/"국세기본법") 통일 | 없음 |

### 알려진 결함·미확인

- 사실 적용(3번 작업)은 계획·생성·판정 지시만 바꿨다. 모델이 따르는지, 판정이 적용 주장을 얼마나 인정하는지는 미확인이다.
- 사건 당시 버전은 현행 검색이 찾은 조문 번호로만 과거 저장소를 조회한다. 그 사이 조문 번호가 바뀌었거나 사건 당시에만 있던 조문은 찾지 못한다(결론은 이전처럼 막힌다).
- 계획 모델이 전체 세법에서 법을 고르는 변경의 실제 선택 정확도는 미확인이다. 법령명이 명시된 조문은 쟁점의 법 필터와 무관하게 후보에 들어오므로 다른 주체의 법이 근거에 섞일 수 있다(근거 충족 판정이 관련성을 가린다).
- 10-04 고정 카드 결과(전부 fail)는 그 이후 모든 수정 이전의 답변이다. 소득세 사례의 R1 fail 원인(평가기와 DB 버전 대조)은 확인하지 않았다(가설).
- 합성 오류 주입은 코드 검사 탐지만 측정했고 Judge의 의미 오류 탐지는 측정하지 않았다.

### 보관 결과 위치(Git/Docker 제외)

- `evaluation/runs/auto-evaluation-20261004/`: `pipeline-v2/cards/`(고정 카드), `rejudge-final/`(저장 답변 재판정), `live-final/`(새 실제 실행), `verification-final.json`, `langsmith-readback-final.json`. LangSmith Dataset/Experiment ID는 아래 2026-10-04 기록에 있다.
- 컨테이너를 재생성하거나 다른 환경으로 인계할 때 이 폴더를 호스트에서 따로 보존한다.

## 2026-10-08 참고 계산 재시도 피드백과 근거 중복

사용자가 "금융소득으로 1억을 벌게 된다면 금융종합소득과세로 세금 얼마나 납부하게 될까?"를 다시 답변(대화 기록 722의 4번째 버전,
10-08 11:02)했는데 금액 없이 원문 설명만 나왔다. 저장된 검증 기록과 코드로 확인했다.

**원인(확인한 것)**

- 참고 계산이 두 번 모두 거부됐다(`formula_review_incomplete`, 마지막 오류 `missing_prepaid_or_balance`). 산식 엔진은 기납부세액(prepaid)이 있으면 차감 납부·환급액(balance)도 요구하는데(`formula_engine.execute`), 모델이 balance 단계를 빠뜨렸다. 재시도에 전달된 피드백은 이 코드 문자열 하나뿐이었고, 계획 지시도 "필요하면 … prepaid 한 개와 balance 한 개"로 짝을 이뤄야 한다는 점이 모호했다.
- 이 대화의 9-28 버전 1~3도 계산에 실패했다(입력 부족 안내). 기록의 1,588만원 성공 사례는 이 대화가 아닌 시험 실행이었다. 따라서 이번 실패를 10-07·10-08 변경 탓으로 볼 근거는 없다(계산 경로 `formula_workflow`는 그 변경과 별개). 모델 출력의 변동은 배제하지 못한다.
- 근거 패널에 소득세법 제14조가 두 번 나왔다(근거 4건, 실제 조문 3개). 같은 DB 행(`version_id` 동일)이 계산 경로와 쟁점 검색 경로에서 머리말만 다르게 들어와 서로 다른 근거 ID가 됐다.

**변경**: `formula_engine.complete_balance`가 기납부세액(prepaid)은 있는데 차감 납부·환급액(balance)이 없는 계획에 "총세액 − 기납부세액" 뺄셈 단계를 보통 단계로 추가한다(근거 rule은 두 단계의 것을 잇고 이름에 "서버 산출" 표시). 실행 전에 넣으므로 근거 연결 검사·실행·산식 심사·표시를 그대로 거친다. 의미가 하나로 정해지지 않는 경우(balance만 있음)는 보완하지 않고 엔진이 거부한다. `app/services/calculator/formula_feedback.py`가 산식 규칙 코드마다 의미와 고칠 방법을 붙여 재시도에 전달한다(뒤에 값 ID가 붙는 코드 포함, 규칙 자체는 그대로 거부). 계획 지시는 "prepaid와 balance는 함께 쓰거나 둘 다 빼고, prepaid를 쓰면 total-prepaid step을 balance로"로 명확히 했다. 검증 보고서의 근거 목록은 같은 저장 원문(`version_id`)을 한 번만 싣는다(`claim_verification.distinct_sources`).

**검증**: WSL 전체 백엔드 **1,145 passed, 2 skipped**. 신규 `tests/test_formula_feedback.py`(6: 차감액 보완과 보완하지 않는 경우, 보완으로 재시도 없이 계산 성공, 엔진·근거 규칙 코드 전부에 설명이 있음, 보완할 수 없는 규칙은 두 번째 시도가 설명을 받음), `test_answer_panel` 1개(정리 코드를 끄면 실패함을 확인). 실모델 호출은 하지 않았다. 같은 질문의 수정 후 계산 성공 여부는 미확인이며, 모델이 balance 단계를 쓰는지는 웹에서 확인해야 한다.

## 2026-10-08 날짜+법령명 경로, 사실 적용, 사건 당시 법령 버전

결정은 [DECISIONS.md](DECISIONS.md)의 2026-10-08 항목. 커밋 `4ca5af3`(경로), `bf3c83a`(사실 적용·사건 당시 버전).

**1. 날짜+법령명 질문의 경로** `history_context.lookup_shaped`: 과거 법령 원문 경로는 조회형 요청(원문·조문·보여·조회·뭐라고가 있거나, 날짜·법령명·조문·"기준"을 빼면 남는 문장이 4자 이하)일 때만 탄다. 버전 번호는 그대로 과거 경로. 날짜와 법령명이 있어도 사실관계를 묻는 분석 질문과 "증여 당시 시가"처럼 "당시"가 들어간 일반 질문은 쟁점 계획으로 간다. `tests/test_routing_variants.py`의 strict xfail 6건이 정상 통과로 바뀌어 표시를 제거했고, 날짜+법령명·과거 연도·"당시" 변형과 조회형 7개(계속 과거 경로)를 고정했다. 기존 과거 경로 고정 사례(`2010년 소득세법`, `2025년 소득세법 제55조`, `구법 기준`, 버전 번호, 후속 질문)는 그대로다.

**2. 질문 사실에의 적용** (지시만 변경): 계획은 구체적 상황을 묻는 쟁점 question에 "질문의 사실관계에 대한 적용"을 적는다. 쟁점별 생성은 일반 규칙과 별도로 질문 사실에 적용한 주장을 쓰고, 질문에 실제로 적힌 사실만 전제로, 빠진 사실(신고 여부·금액·시점)은 조건으로 적는다. "거래 시점이 없으면 일반 설명으로 한정" 문장은 적용까지 쓰도록 바꿨다. Judge는 질문 사실만 전제하고 빠진 사실을 조건으로 밝힌 적용을 supported로 볼 수 있고, 질문에 없는 사실을 전제·단정하면 applicability contradicted다.

**3. 사건 당시 법령 버전** `app/services/historical_evidence.py`, `temporal_scope`: 검색이 찾은 현행 조문이 사건일을 덮지 못하면 같은 조문의 사건 당시 텍스트를 `law_history`에서 가져와 근거에 붙인다(`attach_event_versions`, 계획 직후와 재검색 뒤). 사건 구간에 시행된 모든 보관 버전(공포일이 구간 끝 이전)에 그 조문이 있고 본문이 같으며 SHA-256이 저장 해시와 맞을 때만 쓴다. 같은 시행일 버전이 여러 개여도 조문 본문이 같으면 확정한다. 시행 범위는 첫 버전의 시행일부터 다음 버전 시행일 전날까지(`effective_to`). 날짜 판정은 "시행일~오늘"에서 "시행일~`effective_to`(없으면 오늘)"로 일반화해, 당시 버전을 인용한 legal 주장을 허용한다. 조회 실패·미확정이면 아무것도 붙이지 않는다(결론은 이전처럼 막힘). 질문당 조회 최대 12건. 답변의 근거 목록에는 당시 버전을 `소득세법 제81조의5 (2024-01-01 시행본)`처럼 대괄호 없이 표시한다(웹이 `[법률] …`을 현행 조문 보기 버튼으로 바꾸기 때문). 적용 시점 안내는 "사건일에 시행 중이던 법령 시행본을 기준으로 판단, 부칙 적용례·경과규정과 조문별 시행일은 별도 확인"으로 바꿨다. 재생성 안내는 사건 당시 시행본(`governs_event_dates` true)을 인용하게 한다.

**실제 저장소 확인(읽기 전용)**: 2024-06-01 소득세법 제81조의5 → 2024-05-17~2024-06-30 버전, 2024년 전체 → 2024-01-01~2024-12-31(그해 모든 버전에서 본문 동일), 2015-06-01 국세기본법 제47조의2 → 2015년 버전, 2023-06-01 소득세법 제95조, 2025-06-01 상속세 및 증여세법 제53조 모두 확정됐다. 확인 중 이 파일 하나를 실행 중 컨테이너에 임시 복사했으며 서비스 경로에서는 아직 쓰지 않는다(재빌드 시 대체).

**검증**: WSL `venv-wsl` 전체 백엔드 **1,138 passed, 2 skipped**(xfail 0), `git diff --check` 통과. 신규 `tests/test_historical_evidence.py`(7), `test_routing_variants` 추가 사례, `test_answer_structure` 지시 계약 1개. 이후 재빌드한 이미지 전체 백엔드도 **1,138 passed, 2 skipped**, 웹 200, readiness ready. 실모델 호출·프런트엔드 변경은 없다.

## 2026-10-07 쟁점 범위 분리와 반복 진단

법 선택이 고쳐진 뒤 같은 질문이 답변됐지만(주장 4개 중 3개 공개) 사용자와 함께 남은 결함을 점검했다. 이번 변경은 이 질문 전용이
아니라 두 법에 걸친 모든 질문에 해당하는 구조를 고친 것이다. 결정은 [DECISIONS.md](DECISIONS.md)의 같은 날짜 마지막 항목.

**원인(확인한 것)**: 저장된 계획의 두 쟁점 question이 서로의 요건을 확인하라고 적고 있었고(쟁점 1: 신고불성실가산세 요건·공통 중복
규정, 쟁점 2: 소득세법 규정과의 관계), 근거 충족 판정은 쟁점의 법과 다른 조문을 입력에서 걸러(`_matching_law`) 다른 법 조문을
요구하고도 그 조문을 볼 수 없었다. 재검색(`gap_references`)이 조문을 가져와도 같은 필터에 걸렸다.

**변경**

- `issue_coverage.py`: 쟁점의 법 조문 + 쟁점 question이 법령명과 조문으로 지목한 조문(`named_in_question`)을 평가 대상에 넣는다. 판정에 `other_issues`를 알리고 다른 법·다른 쟁점의 요건을 요구하지 않게 한다. `assess_issues(..., scope_issues=)`.
- `question_planning.py`: 계획 지시에 "쟁점 question에는 자기 법·주체 요건만, 법 사이의 관계는 한 쟁점에만"을 추가. `retrieve_issues(..., scope_issues=)`; 재검색 안의 두 번째 판정은 부족 요건 문구를 질문에 덧붙여(`asked`) 가져온 타법 조문을 평가에 포함한다. 재검색(`reliable_workflow`)이 전체 쟁점 목록을 전달한다.
- **버그 수정** `reliable_workflow.gap_references`·`named_in_question`: `reference_spans`가 앞 단어를 법 이름에 포함해("관련 소득세법") 판정이 흔히 쓰는 문구에서 조문을 놓쳤다. 검색과 같은 `extract_constraints`로 통일했다.
- `claim_verification.py`: 생성 입력에 `other_issues`, 지시에 "다른 쟁점의 법 내용 금지·결론 되풀이 금지·공통 조건은 한 곳". `repeat_diagnostics`가 공개된 주장의 반복 쌍을 보고서 `repeats`에 기록한다(삭제 없음). `common_subject`: 모든 분석 쟁점의 주체가 같으면 답변 제목에서 생략. 프런트엔드 `issueLabel.js`가 패널 라벨에 같은 규칙을 쓴다.

**측정한 것**: 실제 반복 쌍(결론 재서술)의 글자 겹침은 0.34, 조건 문구 쌍은 0.89로, 글자 유사도는 의미 반복의 근거가 못 된다. 그래서 진단만 한다.

**검증**: WSL 전체 백엔드 **1,105 passed, 2 skipped, 6 xfailed**; 프런트엔드 `npm test` 22 passed, `npm run build` 정상. 신규 `test_issue_scope`(3, 재검색 수정을 되돌리면 실패함을 확인), `test_answer_structure`(4), `test_cross_law_lookup` 1개 추가, `frontend/tests/issueLabel.test.js`(3). 이후 재빌드한 이미지 전체 백엔드도 **1,105 passed, 2 skipped, 6 xfailed**, 웹 200, readiness ready. 실모델 호출은 하지 않았다.

**미확인·남긴 것**: 계획·생성 지시를 바꿨으므로 실제 효과(쟁점 1 충족 판정, 반복 감소)는 웹에서 확인해야 한다. 질문의 사실에 대한 적용 설명(장부 미작성 시 어떤 가산세가 실제로 걸리는지)은 이 변경 후 같은 질문으로 확인해야 해결 여부를 안다. 법 이름 라벨은 "소득세"(세목)와 "국세기본법"(법)이 섞여 있는 상태 그대로다. `auto blocks`에는 `repeats` 집계를 아직 넣지 않았다.

## 2026-10-07 키워드에 갇힌 세법 선택과 교차 법령 조회

실제 질문 "복식부기의무자가 장부를 작성하지 않았을 때 무기장가산세와 신고불성실가산세는 중복 적용되나요?"가 전체 보류됐다.
저장된 검증 기록(`chat_logs` 740, 읽기 전용)과 코드로 원인 사슬을 확인했다. 이 변경은 브랜치 `fix/law-selection-cross-law`의 이미지로 서비스에 반영돼 있다.

**원인(확인한 것)**

1. 세법 후보는 키워드 표가 정한다. 이 질문에는 "소득세"가 없어 `국세기본법`("가산세")만 후보가 됐고, 계획 모델은 후보 밖의 법을 쓸 수 없어(`unapproved_law_filter`) 쟁점이 `국세기본법` 하나로 계획됐다.
2. 쟁점 검색은 그 법으로 고정된다(`tax_type_filter = law_filter`, 정확 조회 결과도 같은 필터로 제외). 근거 판정이 "소득세법 제81조의5 요건 없음"을 지적했고 재검색도 같은 필터라 찾지 못했다. DB에는 소득세법 제81조의5와 국세기본법 제47조의2·제47조의3이 있다.
3. 모델이 쓴 주장은 하나였고, 판정은 "제47조의2 제6항의 큰 금액만 적용 규칙은 뒷받침"한다고 인정하면서도 무기장가산세 요건 근거가 없다는 이유로 주장 전체를 `insufficient`로 보류했다.
4. 표시: 법 이름 끝의 "법"을 무조건 떼어 "국세기본에 필요한 근거"로 나왔고, 일반 규칙 질문에도 "거래·사건의 적용 시점"을 확인하라고 안내했다.

**변경**

- 법 선택 `tax_laws.py`(`LAW_KEYWORDS`를 `chat_service`에서 이동, `chat_service._LAW_KW`는 별칭), `question_planning`: 계획 모델이 `KNOWN_LAWS` 전체에서 법을 고른다. 키워드 후보는 보존해야 하고(`missing_tax`), 추가 법은 최대 3개(`too_many_added_laws`). 프롬프트는 개별 세법의 가산세·특례와 공통 절차 규정을 법별 쟁점으로 나누게 한다. 계획 거부 시 키워드 기반 대체 계획.
- 교차 법령 조회 `hybrid_search_service._direct_in_scope`·`_names_law`: 법령명이 명시된 조문의 정확 조회 결과는 쟁점의 법 필터와 무관하게 남기고, 법령명 없는 조문은 이전처럼 제한한다. `reliable_workflow.gap_references`: 재검색이 근거 충족·주장 판정이 지목한 `알려진 법 + 조문`(최대 4개)을 질의에 덧붙이고 재질의 모델에도 `coverage_gaps`를 준다.
- 명제 단위 주장: 쟁점별 생성 프롬프트가 한 주장에 법적 명제 하나와 그 인용만 담게 하고, 보류 후 재생성 안내(`semantic_check_not_passed`)가 명제를 나누게 한다. 생성 프롬프트 해시가 바뀐다.
- 표시: `law_label`(…세법만 "법" 제거), `requested_inputs`(공개된 주장이 없으면 날짜 확인 요청을 생략하고 보고서의 `plan.missing_inputs`도 같이 정리).

**실제 질문 결과(수정 후, 질문 1개)**: 쟁점이 `소득세법`(1)·`국세기본법`(2)으로 나뉘고 주장 4개 중 3개가 공개됐다(limited). 핵심 판단은 "동시 적용 시 큰 금액만 적용, 같으면 무신고·과소신고가산세 적용"(국세기본법 제47조의2, 소득세법 제81조의5). 보류 1개(`1:2`)는 판정 모델이 질문과 무관한 조문을 인용했다고 지적한 정당한 보류다. 쟁점 1은 근거 충족 판정이 "무신고·과소신고가산세 요건, 국세기본법 제47조의2 제6항"을, 쟁점 2는 "소득세법 제81조의5 전문"을 부족하다고 지적해(각 쟁점이 자기 근거만 봄) `설명 보완 필요`로 남았다. 쟁점 간 근거 공유는 쟁점별 법·주체 범위 보존 원칙과 충돌하므로 바꾸지 않았다. 표시 오류 두 가지를 후속 수정했다: 공개된 주장이 모두 원문 요약일 때 패널이 "통과한 법적 설명이 없다"고 표시한 것, 답변이 이미 일반 범위를 밝혔는데 패널에 "추가 확인: 거래·사건의 적용 시점"이 남은 것.

**검증**: WSL `venv-wsl` 전체 백엔드 **1,097 passed, 2 skipped, 6 xfailed, 5 subtests passed**, `git diff --check` 통과. 신규 `test_law_selection`(7), `test_cross_law_lookup`(4), `test_check_gates`·`test_professional_presentation` 추가분. 이후 `dev/docker-up-wsl.sh backend frontend`로 재빌드해 **이미지 전체 백엔드 1,097 passed, 2 skipped, 6 xfailed**, 웹 200, readiness ready를 확인했다. 이 검증 자체에서는 실모델을 호출하지 않았다(위 실제 질문 결과는 사용자가 웹에서 한 질문이다). 패널 문구 수정(`test_answer_panel` 2개)은 재빌드 후 실제 답변으로 확인하지 않았다.

## 2026-10-07 공개 검사 개선과 측정 도구

실제 평가에서 맞는 답을 코드 검사가 막는 문제와 키워드 우연 라우팅이 확인돼, 공개 기준을 낮추지 않고 원인을 고쳤다.
커밋 `619b2fb`(라우팅), `6d60b7f`(공개 검사), `fae65eb`(측정 도구).

**변경**

- 라우팅 `history_context.py`: "한국 세법상" 같은 일반어는 법령명으로 보지 않는다(증여 사례의 "조회할 법령명을 지정" 오류). `tests/test_routing_variants.py`는 6세목 질문에 일반어·"계산"·"서류"·현재 연도를 붙여도 경로가 바뀌지 않음을 모델 호출 없이 고정한다.
- 교차참조 `claim_verification.unmatched_references`: 인용한 원문 자체가 언급하는 조문(법명 없는 `제127조` 등)은 `prose_reference_mismatch`로 보류하지 않는다. 원문에 없는 조문·다른 법명 참조는 계속 보류한다.
- 날짜 `temporal_scope.py`: 사건 날짜 구간이 인용 근거의 시행일~오늘 안에 있으면 legal 주장을 허용하고 그 외는 `historical_version_required`. `question_planning.validate_plan`은 기간("3년 6개월")을 `dates`에서 제외한다(양도 사례 계획의 오염 원인). 현행 시행본으로 판단하면 부칙 확인 안내를 한 번 표시한다(`current_version_note`). 생성·Judge 입력에 근거별 `governs_event_dates`를 추가했다. 공용 테스트 근거의 시행일은 2020-01-01→2026-01-01로 옮겼다.
- 전제 연쇄 `release_claims`: 전제가 표기 오류(`DETACHABLE_PREMISE_ERRORS`)로만 막히고 Judge가 supported면, 자기 검사를 모두 통과한 의존 주장은 공개한다. 화면에 `DETACHED_NOTE`, 보고서에 `detached_from`을 남긴다.
- 검사 등록표 `claim_verification.CHECKS`: 코드마다 `block`/`signal`, 재생성 분류, 전제 분리 가능 여부, 수정 안내를 한 곳에 둔다. signal은 `tax_scope_mismatch`·`subject_scope_mismatch`·`source_scope_unstated`·`historical_scope_unstated` 4개로, `CLAIM_SIGNAL_GATE=judge`(기본, 사용자 결정으로 유지)에서 Judge 입력 `server_flags`로 전달돼 Judge 판정으로만 보류한다. `block`으로 설정하면 직접 보류한다. 보고서 주장 항목에 `signals`를 기록한다. 새 검사 코드는 등록 없이 추가할 수 없다(`tests/test_check_gates.py`).
- 조문 표기: 모델은 `[[E1]]`로 인용 근거를 가리키고 `expand_citations`가 법령명·조문으로 바꾼다. 인용하지 않은 ID는 `unresolved_reference_placeholder`로 보류한다. 세액 금액은 질문이나 인용한 공식 원문 전체에 있으면 근거가 있는 값으로 본다.
- 재생성 피드백: `previous_failures.failed_claims`에 보류 문장, 인용 법령·조문, 문제별 `code/category/detail/fix`와 신호를 전달한다. 증거 별칭(E1)은 호출마다 바뀌므로 법령명·조문으로 전달한다. 오류 코드 분류(integrity/repairable/evidence)는 재생성 지시에만 쓰고 보류 기준은 바꾸지 않는다.
- 표시: 대체 표시 경로 `render_claims`까지 `subject_label`로 통일해, 질문에 `A회사`/`A사`가 있을 때만 주체 `A`에 "회사"를 붙인다. 생성·Judge 프롬프트 해시가 바뀌었다.

**측정 도구**(저장 결과만 읽으며 기본은 모델 호출 없음, 사용법은 [AUTO_EVALUATION.md](../../evaluation/AUTO_EVALUATION.md))

- `scripts/evaluate.py auto blocks <run...>` (`evaluation/block_report.py`): 보류된 주장을 검사 코드별로 세어 Judge 판정과 교차한다. 10-04 두 실행에서 주장 8개 중 5개 보류, Judge supported인데 코드가 막은 후보 2건(모두 `prose_reference_mismatch`, 수정함), 연쇄 보류 1건, 주장 없이 끝난 사례 1건(증여 라우팅).
- `scripts/evaluate.py auto filters <run...> [--cards] [--judge]` (`evaluation/filter_value.py`): 정상 씨앗 11개에 변형 60개를 넣어 검사별 탐지를 측정했다(`--judge` 미실행). 없는 조문·지어낸 세액·인용 변조는 각 11/11을 코드가 잡았고 다른 세목 문장은 11/11 신호로 표시됐다. 결론 뒤집기 2개·다른 근거 연결 10/11·조문 번호 이동 2/3은 코드가 잡지 못했다. 이동 2건은 인용한 조문의 실존 항·호를 가리키게 된 경우라 결정적 검사로 판별할 수 없고 Judge의 몫이다. 씨앗 11개 중 10개가 양도소득세 질문 하나에서 나와 세목 전반의 결론은 아니다.

**검증**

- 최신 이미지 전체 백엔드 **1,080 passed, 2 skipped, 6 xfailed, 5 subtests passed**. 이미지 내 `CLAIM_SIGNAL_GATE=judge`, readiness/dependencies ready(OpenRouter `openai/gpt-6-luna`), 웹 200, Alembic `20260930_0010`. `dev/docker-up-wsl.sh backend frontend`로 재빌드했다. 프런트엔드 코드는 변경하지 않았고 프런트엔드 테스트는 실행하지 않았다. `git diff --check` 통과.
- WSL `venv-wsl`에는 `kiwipiepy`가 없어 BM25 테스트 4건이 실패했다(코드 문제 아님). 확인 후 `kiwipiepy==0.24.0`을 설치했고(`requirements.txt`와 동일) 같은 1,080 passed를 확인했다.
- 실모델 채팅·Judge 호출은 하지 않았다. 신규 테스트: `test_temporal_scope`(12), `test_dependency_release`(8), `test_check_gates`(7), `test_routing_variants`(37+xfail 6), `test_block_report`(2), `test_filter_value`(1).

## 2026-10-06 대화·작업 문서 동기화

- 요청 범위는 지금까지의 대화와 구현 결과를 다음 작업자에게 전달할 `AGENTS.md`·`CLAUDE.md` 최신화다. 기존 작업 트리의 코드·문서 변경과 새 자동 평가 파일을 보존했다.
- [AGENTS.md](../../AGENTS.md)에 합의한 품질 목표, 질문/도구/검색/계산/표시/자동 평가의 구현 경계, 2026-10-04 실제 검증 범위, 결과 위치와 후속 우선순위를 추가했다.
- [CLAUDE.md](../../CLAUDE.md)는 공통 규칙의 진입점을 유지하면서 대화 요약·작업별 코드 진입점·현재 답변 결함을 안내한다. 참고 계산의 실제 경로는 `app/services/calculator/formula_workflow.py`다.
- 다음 구현은 아래 2026-10-04의 **서비스 답변 결함 수정**부터 진행한다. 자동 카드 기본 30개 전체 실행, 독립 전문가 승인·R2/G1/T1 보강, Reranker는 미완료다. 이번 문서 작업으로 상태를 변경하지 않았다.
- 검증일 2026-10-06: 변경 Markdown의 로컬 링크·CLI/코드 참조·기존 결과 파일 대조 및 `git diff --check`. 기록은 `evaluation/runs/document-handoff-20261006/verification.json`(Git/Docker 제외)에 보존한다. 제품 코드/DB/모델 변경·Docker 재빌드·전체 테스트·실모델·브라우저·현재 운영 상태 재검증은 수행하지 않았다. 아래 실행 수치는 2026-10-04의 증거다.

## 2026-10-04 자동 질문·평가 카드

### 구현과 실행

- 추가한 CLI는 `scripts/evaluate.py auto build|validate|run|publish|compare|pipeline`이다. [사용법](../../evaluation/AUTO_EVALUATION.md)에 전체 명령·재개·게시·판정 범위를 기록했다. 기존 수동 Dataset/인간 승인/LangSmith 확인 절차는 변경하지 않았다.
- 코드: `evaluation/card_schema.py`, `card_sources.py`, `auto_cards.py`, `auto_pipeline.py`, `auto_langsmith.py`, `auto_cli.py`; 얇은 연결은 `evaluation/cli.py`다. 서비스 코드에서 평가 도구를 import하지 않는다.
- 공식 보관 XML에서 원문/시점/해시를 검증하고 규칙 → 합성 질문/필수·금지 기대 판단 → 코드 검사/별도 감사 → 고정 카드를 만든다. 모델이 원문/답변을 다시 복사하는 오류는 구간 ID 선택과 서버 복원으로 보완했다. 관련 원문을 공유하는 사례는 split을 같이 둔다.
- 실제 채팅에는 질문만 전달하고 이력/저장·개인 문서·웹·중복 tracing을 격리한다. BM25를 먼저 준비하며 준비 실패는 기록하고 fallback을 유지한다. `--from-run`은 원 관측/생성 버전을 보존하면서 새 Judge만 실행한다.
- 모델/임베딩/8개 작업/DB schema/프런트엔드는 유지했다. 기본 생성 30개는 시도 범위다. 이번 검증은 일반 질문 6개와 실제 채팅 3개이며 모든 세목/복합/시점 질문의 성공률을 입증하지 않는다.

### 결과와 주의할 파일

- 로컬 결과 루트: `evaluation/runs/auto-evaluation-20261004/`(Git/Docker 제외). 컨테이너 재생성 전에 호스트로 복사했다.
- `initial-cards/`: 긴 인용 복사/초기 감사 문제를 발견한 중단 기록. 완료 배치나 최종 결과로 사용하지 않는다.
- `pipeline-v2/cards/`: 6개 생성 시도 중 3개 채택, 2개 fail, 1개 unknown. 규칙/원문 XML/제외 후보·이유/카드 해시를 보존한다.
- `pipeline-v2/run/`: 실제 질문만 전달한 채팅 관측 3개와 첫 평가. 평가기 형식 오류가 포함된 이전 결과다. 답변 관측 자체는 이후 재판정에서도 변경하지 않는다.
- `rejudge-v3/`: 구간 ID/ID enum 보완 후 재판정. 한 사례의 평가 pass에 필요한 발췌 누락이 남아 있어 최종 판정으로 사용하지 않는다.
- 최종 판정·최신 이미지 테스트·원격 검증 파일은 아래 완료 기록을 우선한다. 자동 진단은 인간 세무 승인과 다르다.

### 2026-10-04 실제 평가·게시 완료 기록

- 최종 재판정: `rejudge-final/experiment.json`, `report.md`, `langsmith-plan.json`, `langsmith-receipt.json`. **3개 관측/33항목: fail 14, pass 4, unknown 6, N/A 9, error 0; 사례 3개 fail**. 실제 채팅을 다시 생성한 결과가 아니라 `pipeline-v2/run`의 동일 답변을 개선한 Judge로 평가한 결과다.
- LangSmith Dataset `8b85c91e-f4ed-4c74-99eb-131384388d29`; 최종 Experiment **`tax-eval-system-ed423262b6103a000fb2a0a4`**, ID `9fa97800-93fd-4747-833b-6a1f57b69890`. 원격 API 재조회로 3 examples/3 runs/각 13 feedback(11항목+상태+지연)을 확인했다. URL/검증 범위는 `langsmith-readback-final.json`이다. 이전 Experiment `94e6e7...`, `eebc181...`은 평가기 형식 보완 전 결과다.
- 최종 새 실모델 실행 1개: `live-final/experiment.json`, `report.md`, 게시 영수증. 양도소득 질문을 원래 서비스에 다시 넣었고 BM25 `ready`를 확인했다. 11항목: fail 5/pass 3/unknown 2/N/A 1/error 0; 사례 fail. 실제 Graph 입력은 독립 감사/유용성 확인 한계를 unknown으로 기록했다.
- 새 실제 실행의 LangSmith Dataset `6f34b430-ca47-4b50-bc59-ad7a20f362e8`, Experiment **`tax-eval-system-4d053d98a595cf6f08f3fd20`**, ID `2a651434-2bca-4103-8fe3-97083f6ac82a`. 위 3개 고정 관측 재판정과 다른 배치다.
- 실행의 exit 1은 발견한 답변 실패를 뜻한다. 게시 영수증은 complete이며 LangSmith API 오류가 아니다. 최종 평가 모델 호출/발췌 오류 0은 해당 작은 검증 범위에 한정한다.
- 원문 파일 재검사 `auto validate`: 카드 3개, hash `148612441cffa2afee11f04554da23a25c60d6d661a9a0c9e5626ad2632c88fd`, 인간 승인 0. 최종 pytest 로그는 `backend-tests-final.log`, 이미지/상태는 `verification-final.json`, Markdown 12개/로컬 링크 65건 정상은 `documentation-check.json`에 보관한다.
- 최종 최신 이미지 전체 백엔드 **1,005 passed, 2 skipped, 5 subtests passed**, 56.63초. 신규 계약 검사 36개를 포함하며 마지막 보완은 제공자 오류 메시지를 알려진 내부 오류 코드 외에는 출력하지 않도록 한 것이다. `git diff --check` 통과, readiness/dependencies ready/Graph ok/웹 200. 프런트엔드 변경·테스트/build는 이번 범위에 없다.

### 다음 작업 (2026-10-04 당시, 1번은 2026-10-07에 코드 수정 반영·효과 미확인)

1. **실제 발견한 답변 문제**: 소득세 사례의 개인 A가 회사로 계획되는 문제와 불필요한 유보, 증여 사례의 날짜만으로 원문 조회/법령명 요구 경로에 진입하는 문제, 양도 사례의 확보 원문에 있는 장기보유 공제 조건/기준이 답변에서 누락되는 문제를 재현·수정한다. 이 배치의 고정 질문/실제 관측을 회귀 기준으로 사용하되 기대 카드는 자동 초안임을 유지한다.
2. **자동 카드 범위 확대**: 기본 30개 실제 생성/평가, 예외·정보 부족·복합·시점의 세목별 채택/제외 사유를 검토한다. 유효한 fail/unknown이 pass가 될 때까지 같은 카드를 반복 생성하지 않는다. 보관 원문의 위임/별표/부칙 결손을 먼저 해결한다.
3. **독립 승인/교정**: R2 혼동 근거, G1 원문 관계 감사, T1 숫자 기대값과 전문가 검수/오답 통과율을 확보한다. 동일 모델의 별도 호출을 독립적인 세무 정답으로 취급하지 않는다.
4. **데이터/검색 잔여**: 원문 의심 27행·보류 인용 4,952개·기존 빈 벡터 metadata·Reranker/추가 RAG 범위는 아래 이전 인계대로 남아 있다. 이번 작업에서 원문/색인 데이터는 수정하지 않았다.

## 2026-10-01 문서 동기화 인계

### 현재 기준과 이번 작업

- 이번 요청은 지금까지의 결과와 실행·인수인계 문서 최신화다. 제품 기능 변경이나 Reranker 구현은 수행하지 않았다.
- 시작 시 작업 트리는 깨끗했다. 생성/계획/Judge OpenRouter `openai/gpt-6-luna`, Ollama `qwen3-embedding:4b`/v1/2,560차원을 유지한다. LLM 작업 8개는 `config.py` 기준이다.
- 실행은 WSL에서 `source venv-wsl/bin/activate` 후 `bash dev/docker-up-wsl.sh backend frontend`. llama.cpp는 선택형 실험으로만 안내한다.
- 읽기 확인 **2026-10-01 14:18 KST**: 웹 200, readiness/dependencies ready, Graph ok, schema `20260930_0010`, OpenRouter Luna/Ollama Qwen3 v1. 생성 호출이나 전체 DB 감사 결과가 아니다.
- 직전 구현 최종 기록은 backend 969 passed/2 skipped/5 subtests passed, frontend 19 passed/build. 이번 문서 변경의 검증은 Markdown 12개·로컬 링크 59건·Python CLI 파일 참조 59건·LLM 작업명 8개·Reranker 미구현 대조와 `git diff --check` 통과다. 위 제품 테스트를 새 실행 결과로 보고하지 않는다.

### 완료된 결과와 보관 위치

| 영역 | 완료 범위 | 근거/결과 위치 |
|---|---|---|
| 검색 | 공식 현행 BM25·벡터·검증된 GraphRAG·Regex/Fuzzy/MMR·쟁점별 충족/재검색 | `app/services/search/`, `evaluation/runs/search-quality-20260930/` |
| 원문·색인 | 동일 시행본 1,503조문 복원 + 1,471조문 누락 항 생성, 2,974조문/13,203항 이력 감사 0 | 같은 디렉터리의 `repair/`, `repair-rest/`, `repair-letter/`, `index-audit.json`, `graph-audit.json` |
| 최종 검색 비교 | 개발 39문항 필수 라벨 38/38, MRR 0.746053, hard negative 5→4 | `repaired-baseline.json`, `algorithms-final.json`, `typos-exact.json` |
| 답변 구조·웹 | 공개된 핵심 판단·검토·절차·자료·추가 확인, 개별 조건 보존, 근거 패널 | `evaluation/runs/professional-answer-20261001/{vat-final,gift-final}.json`, PC/mobile PNG |
| 참고 계산 | 전용 범위 밖 공식 근거/JSON 산식/Decimal/Judge/근거 패널 | `app/services/calculator/formula_workflow.py`, `evaluation/runs/generic-calculation-20260928/` |

`evaluation/runs/`는 Git/Docker 빌드 제외인 로컬 결과다. 다른 PC/작업자에게 인계할 때 필요한
최종 결과와 plan/backup/state를 별도로 전달한다. 컨테이너 `/tmp`만을 백업으로 사용하지 않는다.
작은 예시 성공과 개발 라벨을 전체 세무 정답률·질문 완결성으로 해석하지 않는다.

### 남은 작업

1. **독립 품질 검수**: 여러 세목·주체·연도·복합/오타/부정 질문의 전문가 holdout, 필수/무관 근거, 기대 주장·예외·보류 기준을 LangSmith에서 검수한다. Judge 오답 통과/정상 차단과 검색 순위를 분리 측정한다.
2. **잔여 원문**: `evaluation/runs/search-quality-20260930/remaining-original-review.json`의 27행은 누락 의심 후보다. 동일 시행본 공식 XML·목록 탐지 오탐을 점검하고 새 plan/백업으로 보정한다. 다른 MST/시행본으로 자동 교체하지 않는다.
3. **그래프/입력 이력**: 대상 원문이 부족해 연결하지 않은 4,952개 인용과 기존 빈 벡터 metadata를 구분해 검수한다. 추측 관계 생성이나 사후 일괄 검증 표시는 하지 않는다.
4. **Reranker 후속 설계**: [RAG_IMPROVEMENT_PLAN.md](RAG_IMPROVEMENT_PLAN.md). Qwen3-Reranker-0.6B·별도 Docker·후보 풀 유지·off/shadow/active는 제안이다. 전용 모델/API/새 설정은 아직 없다. 이전 vLLM/Infinity 실험의 Reranker가 현재 존재한다고 간주하지 않는다.
5. **추가 RAG 범위**: 토큰/쟁점별 근거 예산·요건/예외 묶음, 일반 상담의 사건일/부칙 연결, 공식 실무 자료와 권한을 유지하는 문서 BM25, 단계별 응답 지연을 각각 비교 후 적용한다.

기존 보정은 완료됐다. 위 목록을 수행하기 위해 이미 보정된 전체 데이터를 다시 수집하거나
모델을 교체하지 않는다. 백업/rollback과 날짜별 상세 실패 기록은 아래에 보존한다.

## 날짜별 인계 이력

아래는 당시의 작업 상태다. 현재 우선순위·모델·테스트·기능 여부는 위 최신 인계를 사용한다.

## 2026-10-01 세무 답변의 역할과 전문적인 표시

- 코드: `schemas/reliability.py` 표시 역할, `claim_verification.py` 생성 지시/서버 출처 범위 기록/역할별 표시, `MessageBubble.jsx`/`answerSections.js`/`answerPresentation.css`, `VerificationPanel.jsx` 근거 수/쟁점/검사 범위/원본 표시. 표시 버전은 `tax-answer-20261001-v1`이다.
- 핵심 판단은 공개 승인된 독립 주장만 이동하며 한 번 표시한다. fact/guidance와 의존 결론은 승격하지 않는다. 역할 기본 explanation으로 이전 계약을 읽을 수 있고 공개 검사를 바꾸지 않는다. 직접 원문/결정적 계산/과거 법령의 별도 생성 경로는 기존 형식을 사용한다. 일반 분석 텍스트는 새 질문/다시 답변부터 바뀌며 스타일은 새로고침한 기존 대화에도 적용된다.
- 구체 조건을 `원문/시점` 단어 때문에 숨기지 않는다. 서버가 source_summary의 출처/과거 적용 미확정을 코드 검사·Judge 전에 기록하며, 생성 지시는 공통 안내를 다시 쓰지 않고 개별 조건만 작성하도록 했다. 실제 모델에서 공통 조건의 여러 문구 변형과 절차 제목 중복, 대통령령 원문 링크 누락을 발견해 수정했다. 모호한 의미 유사성으로 기존 주장을 임의 삭제하지 않는다.
- 검증 자료는 Git 제외 `evaluation/runs/professional-answer-20261001/`. 초반 `vat-live.json`, `gift-live.json`, `vat-v2.json`, `gift-v2.json`은 공통 문구 반복 보완 전 진단이다. 완료 기록에 명시한 최종 JSON/화면을 우선한다. 테스트 질문/답변을 대화 DB에 저장하지 않는다.
- 재현: 최신 backend에서 `python dev/probe_reliable_answer.py /tmp/<새파일>.json general|compound --warm-bm25`. 공개된 예제에만 사용한다. 최종 공개 주장·원본 스냅샷·plan/coverage를 `presentation_input`에 기록하여 추가 생성/Judge 없이 표시를 비교할 수 있다. 컨테이너 재생성 전에 결과를 호스트로 복사한다.
- 웹 확인: `PLAYWRIGHT_MODULE`에 설치한 Playwright 경로를 지정하고 `frontend/tests/answerPresentation.browser.cjs` 실행. `UI_ANSWER_JSON`을 최종 실제 JSON으로 지정하면 API 대역으로 생산 UI에 표시한다. `UI_SCREENSHOT`/`UI_MOBILE_SCREENSHOT`으로 화면을 보관한다. 이 파일은 실제 계정/대화 API에 쓰지 않는다.
- 남은 품질 검수: LangSmith에서 여러 세목·과거 시점·긴 복합 질문의 내용 충족도와 문체/중복/조건 근접/실무 조치의 읽기 품질을 독립적으로 검수한다. 작은 표시 스모크와 draft 결과를 세무 정답률/전체 질문의 성공 보장으로 표현하지 않는다. 기존 원문 27개 검수와 전문가 정확성 검증 작업은 아래 기록대로 별도다.
- 최종 완료 결과: backend **969 passed, 2 skipped, 5 subtests passed**; frontend **19 passed**/build; diff 검사 통과. 실모델 `vat-final.json`은 **5/5 공개·checked**, `gift-final.json`은 **4/4 공개·limited**, Judge 오류 **0**, 두 출력의 공통 적용 안내 **1회**다. 증여의 개별 조건은 4개 모두 문단 옆에 표시됐다. 최신 코드/설정으로 생성한 JSON과 Edge PC/모바일 실제 표시 검사 두 건을 보관했다. 웹 200/readiness ready/Graph ok, 생성 OpenRouter `openai/gpt-6-luna`, 임베딩 Ollama `qwen3-embedding:4b`.
- 화면 파일: `vat-desktop.png`, `vat-mobile.png`, `gift-desktop.png`, `gift-mobile.png`. API 대역은 실제 응답의 표시 확인용이고 사용자 대화 생성이 아니다. 코드/검증 상태와 사실을 연결한 운영자 평가는 기존 LangSmith에서 별도 진행한다.

## 2026-09-30 원문·색인 보정 및 세 검색 알고리즘

- 코드: `law/index_metadata.py`, `index_repair.py`, `scripts/repair_law_indexes.py`, `evaluation/index_repair_audit.py`; Alembic `20260930_0010`. 검색: `query_constraints.py`(Regex), `fuzzy_terms.py`(거리 1 사전 확장), `diversity.py`(MMR), 공식 쟁점 Hybrid 연결. 읽기 A/B: `issue_retrieval_probe.py --no-algorithms`, `search_algorithms_probe.py`.
- 보호: 원 질문/금액/날짜/부정 의미/참조는 유지한다. Fuzzy 모호 후보는 미확장, 원문만 요구한 명시 참조는 정확 조회, MMR은 모든 후보와 직접/그래프/보완·상위 2개를 보존한다. coverage·원문 인용·주장 의미 검사는 별도다. 생성/Judge OpenRouter GPT-6 Luna, 임베딩 Ollama Qwen3를 유지한다.
- 보정 실행 기록/원본·벡터·항·그래프 백업은 Git 제외 `evaluation/runs/search-quality-20260930/`에 저장한다. `repair/`는 핵심 세법 계획/376행 백업, `repair-rest/`는 나머지 현행 법령 계획/행별 백업이다. container `/tmp`는 재빌드 전에 반드시 호스트로 복사한다.
- 복원: 해당 plan/모든 backup/state를 컨테이너에 복사하고 `python scripts/repair_law_indexes.py rollback --plan <그 계획>`을 실행한다. 최신 수집/다른 보정 실행이면 덮어쓰지 않는다. 복원 후 `python scripts/sync_law_graph.py --all --apply`, `python scripts/audit_law_graph.py`를 실행한다. 그래프 원본 사본은 `repair/graph-before.json`; 별도 역사 그래프/대화 스냅샷은 수정하지 않았다.
- 전체 현행 그래프 동기화에서만 이전 원문 키 `TaxArticle`와 연결을 정리한다. 개별 법령 동기화/빈 전체 snapshot은 다른 데이터 삭제를 허용하지 않는다. `TaxTemporalArticle`/`TaxGraphSnapshot`은 보존한다.
- 확대 보정 중 Ollama 임베딩 1건의 300초 ReadTimeout을 확인했다. DB 변경 전에 발생했으며 완료 2,163행의 백업/체크포인트를 보존해 정상 재개했다. 직접 원인까지 확인한 것은 아니다. 장기 배치에서 재발 시 임베딩 서버 로그/네트워크와 서버 재기동을 점검한다.
- 완료(2026-10-01): 원문 복원 **1,503개** + 누락 항 색인 생성 **1,471개** = 보정 **2,974조문/13,203항**, lineage 감사 오류 **0**. 현행 전체 **6,675조문/16,437항**, 활성 벡터 누락/분할 대상 항 미생성 **0**. `repair-letter/`에 원문/보관 XML이 같은 부가가치세법 시행규칙 제50조 1행의 추가 plan/백업(9항)을 보관한다. 원문 숫자 호 존재 여부는 계속 별도 검사한다.
- 그래프: 전체 현행 **6,675노드/11,216 CITES**, stale/missing/duplicate/원문 증거 문제 **0**. `index-audit.json`, `graph-audit.json`, `corpus-after.json`에 저장했다. 관측 스냅샷은 **2026-10-01**이며 당시 법적 적용 기간을 추정한 결과가 아니다. 미해결 인용 **4,952개**는 대상 법령/세부 항이 없는 등의 이유로 연결을 보류한다.
- 같은 보정 코퍼스 A/B `repaired-baseline.json`→`algorithms-final.json`: 필수 근거 38/38, MRR 0.746053 유지; hard negative 5→4, P50 0.380→0.362/P95 0.429→0.374초, 오류 0. `algorithms-first.json`은 보호 후보를 앞으로 올려 MRR이 낮아진 실패 기록이다. 보호한 원 순위를 고정하고 다른 후보만 MMR로 다양화했다. `typos-exact.json` 16입력에서는 필수 근거 13/15→15/15, 원문 조회의 요청 외 후보 23→0, 오류 0이었다.
- 미완료 데이터 검수: 누락 의심 본문 **27행(소득세법 3행)**은 동일 시행본 복원이 확인되지 않았다. 임의 원문 교체/다른 MST/과거 버전 적용은 하지 않는다. 저장 원문·XML 구조·목록 탐지 오탐을 개별 점검하고 공식 동일 버전이 확보되면 새 보정 plan/백업으로 처리한다. 기존 metadata 없는 벡터의 입력 이력은 미입증이다. 이 기록으로 전체 코퍼스 법적 정확성/최신성/독립 골드 승인을 주장하지 않는다.
- 다음 평가: 개발에 사용하지 않은 전문가 정답/필수·무관 근거·오타·부정·과거 시점/복합 쟁점 holdout을 LangSmith에서 검수한다. 후보 회수/순위와 답변 근거 충족/법적 해석/Judge false pass·false block을 각각 측정한다. 현재 draft 라벨과 단일 실행은 세무 정답 골드가 아니다. 새 관리자 화면은 없다.
- 최종 이미지 전체 백엔드 **956 passed, 2 skipped, 5 subtests passed**, diff 검사 통과. 실행 설정은 세 플래그 true/λ=0.85, Ollama `qwen3-embedding:4b`/OpenRouter `openai/gpt-6-luna`. `gift-live.json`은 증여 공제/신고/서류 6/6 공개·limited, `vat-live.json`은 매입세액 요건/불공제 4/4 공개·checked, 두 Judge 오류 0. 대화 DB는 수정하지 않았다. 최신 컨테이너에서 공개 smoke를 재현할 때 `python dev/probe_reliable_answer.py <새 출력 파일> compound|general --warm-bm25`를 사용한다. 최종 검증 상태도 세무 정확성 입증이 아니다.
- 잔여 원문 점검 대상의 정확한 행 ID·해시·법령명·참조·시행일·MST URL은 `remaining-original-review.json`(27개)에 저장했다. 자동 보정 승인/원문 누락 확정 목록이 아니다. 당시 실제 schema/코드를 우선하고 서비스/데이터 재수집 여부를 확인한 뒤 새로운 계획을 작성한다.

## 2026-09-30 BM25 Hybrid RAG

- 구현/설정/작동 범위는 README의 `공식 법령 Hybrid RAG`와 ADR-068을 참고한다. 기본 BM25이며 `SEARCH_LEXICAL_BACKEND=trigram`으로 이전 키워드 경로를 선택할 수 있다. 임베딩 Ollama Qwen3-embedding:4b, 생성/Judge OpenRouter GPT-6 Luna를 유지한다.
- 실제 DB draft/dev 39문항 비교는 `evaluation/runs/hybrid-bm25-20260930/{trigram-all,bm25-body-all,bm25-fields-all,bm25-final-all}.json`(Git 제외). 최종 38/38, MRR 0.755994, P50 0.365초/P95 0.422초, hard negative 4, 실행 오류 0. 기존은 38/38, MRR 0.730075, P50 0.474초/P95 0.725초다. 해당 개발셋으로 설정을 조정했으므로 holdout 성적이 아니다. 첫 BM25 질문 5.645초, 색인 준비 38.957초였으며 독립 반복 측정이 필요하다.
- 검색 색인은 PostgreSQL에서 읽은 canonical 공식 현행 조문 6,664개다. 각 프로세스는 자신의 색인과 Kiwi 모델을 보유하므로 worker 수를 늘릴 때 메모리/초기 준비 비용을 확인한다. BM25 cold 대기는 12초 제한이며 초과 시 pg_trgm fallback을 사용한다. 같은 시행본 XML의 읽기 복구를 색인에 반영했으나 기존 벡터/그래프의 해시는 바꾸지 않았다.
- 재색인 준비: `evaluation/current_index_audit.py --all-core-recovery --manifest /tmp/core-repair.json`으로 ID/기존·복구 해시/시행일/원문 URL/스냅샷 ID를 기록한다. DB 쓰기는 없다. 중복 행/unique 충돌, 범위별 백업과 복원, 승인 필수·무관 라벨, 본문/벡터/항/그래프의 정합 갱신을 준비한 뒤 파일럿을 적용해야 한다. 이번에 `embed_clauses_for_articles`의 삭제 선행 문제는 해결했다(네트워크 완료 후 잠금·대조·transaction 교체).
- 관련성 재순서는 기존 coverage Judge에 중요도 순 ID 선택을 지시하는 수준이다. 전용 CrossEncoder 모델은 도입하지 않았다. 별도 reranker는 실제 쟁점별 holdout, 추가 지연/메모리, 오답 후보 혼입률을 비교한 뒤 선택한다. HNSW 추가 튜닝/스키마 변경·사용자 문서 BM25도 이번 범위에 추가하지 않았다.
- LangSmith 실제 게시에서 월간 unique traces usage limit 초과 429를 확인했다. 검색 결과는 정상 반환했으며 로컬 probe는 기본 tracing OFF, `--trace`일 때만 켠다. 이 외부 한도가 해소되기 전 게시 성공을 주장하지 않는다. 서비스 추적 설정/구독 변경은 없다.
- 실제 모델 스모크: `gift-smoke.json`은 4/4 공개이나 제53조 공제 한도 설명이 누락된 실패 진단이다. 실제 보완 질의에서 `상증세법 제53조`를 약칭 그대로 조회하던 문제를 확인해 정해진 법령 약칭/시행령/시행규칙만 정식명으로 연결했다. `gift-alias-smoke.json`은 **5/5 공개, 1/1 쟁점 답변, Judge 오류 0**, 제53조 원문/공제 설명을 포함한다. 여전히 limited이며 구체 첨부서류·전자신고·납부 상세 절차가 coverage 부족으로 남아 있다. 이 상태를 세무 정답/완결성 개선 완료로 보고하지 않는다.
- `core-repair-manifest.json`은 376개, DB 쓰기 0이며 위 단계의 실제 실행 결과다. 후보 목록은 대량 교정을 승인하거나 안전한 롤백 파일을 대신하지 않는다. 원본 교체 시 사본·벡터·항·그래프를 함께 검증해야 한다.
- 최종 이미지 전체 테스트 **931 passed, 2 skipped, 5 subtests passed**, `git diff --check` 통과, `/api/health/ready` DB 정상/Alembic `20260928_0009`. 서비스 Docker 재빌드 완료. 색인 준비 후 한 번 측정한 컨테이너 전체 메모리는 약 953MiB였으며 BM25만의 추가 메모리로 해석하지 않는다. 이후 worker/코퍼스 확대 시 별도 측정이 필요하다.

## 2026-09-29 RAG 검색 진단

- 코드: `hybrid_search_service.py`의 선택적 `diagnostics`, 공식 법률 조문 제목 보완(max 2), 실험용 비활성 `SEARCH_QUERY_INSTRUCTION_ENABLED`; 읽기 전용 `evaluation/issue_retrieval_probe.py` 및 `evaluation/current_index_audit.py`.
- 실험 명령: `python evaluation/issue_retrieval_probe.py /tmp/issue-retrieval.json --all` 및 `python evaluation/current_index_audit.py --all-core-recovery` (백엔드 컨테이너에서 실행). 이번 실행의 JSON은 Git 제외 `evaluation/runs/rag-improvement-20260929/`에 보관. 전자는 고정 2질의로 실제 검색 함수를 부르지만, 실제 LLM 질문 계획·coverage·답변 전체를 재현하지 않는다.
- draft 39문항 중 필수 라벨이 있는 38문항에서 후보 확보 37→38, MRR 0.727→0.730, hard negative 4건 동일. 새로 잡힌 `corp-03`은 세목이 명시되지 않은 질문이며 법인세법·소득세법 조문이 각각 10위·9위로 추가됐다. 실제 coverage Judge는 지방세도 함께 선택했다. 따라서 이를 세무 적합성 개선으로 인증하지 않는다. 동일 이미지에서 제목 보완을 끄고 Qwen instruction만 켠 A/B는 37/38과 MRR 0.727로 기준과 같아 기본 비활성이다.
- 현행 인덱스 감사: 조문 6,675/항 8,352의 활성 v1 벡터 누락은 0; 분할 조건을 충족하지만 항 벡터가 없는 조문 1,471; 누락 의심 본문 1,530. 다섯 핵심 세법의 누락 의심 379개 중 376개가 동일 시행본 보관 XML에서 더 긴 원문으로 읽기 복구 가능했다. 기존 DB 행·벡터·그래프는 수정하지 않았다.
- 다음 데이터 작업: 376개 각각의 원본 행 ID·해시·시행일·MST와 XML 스냅샷을 확정하고 중복 행을 분리한다. 제한된 파일럿의 재임베딩/항 인덱스 생성 전후에 승인된 필수·무관 조문 라벨과 실제 질문 답변을 비교한 뒤 확대한다. 현행 `embed_clauses_for_articles`는 항을 먼저 삭제하고 이후 임베딩을 생성하므로 실패 시 빈 인덱스가 남을 수 있다. 대량 실행 전 원자적 갱신·복원 경로가 필요하다.
- 운영자 평가는 LangSmith를 사용한다. 현 평가 라벨 39개는 draft이며 법적 정답 승인이나 충분한 hard negative 검수가 없어 대량 재색인의 품질 게이트로 사용할 수 없다.
- 최종 이미지 전체 백엔드 테스트 **911 passed, 2 skipped, 5 subtests passed**; 재실행 진단 JSON `final.json`의 recall 1.0(38/38), MRR 0.730075, hard negative 4, 오류 0. 검색 코드 외 화면 변경은 없다.

## 2026-09-28 근거 기반 범용 참고 계산

- 구현: `app/schemas/formula.py`, `app/services/calculator/formula_engine.py`, `formula_workflow.py`. 금융소득 즉시 보류를 없애고 공식 원문·명시적 가정·제한된 산식·Decimal·필수 Judge를 사용한다. 범용 계산기 API/새 테이블은 추가하지 않았다. 기존 전용 계산기의 입력 부족/DB 실패 경계는 유지한다.
- 웹은 verification에 저장한 원본 산식·수치 출처·실행 결과·원문을 펼쳐 보여준다. 계산 결과는 always limited이며 법령 적용을 checked로 올리지 않는다. 새 질문/다시 답변으로 적용하고 과거 답변은 자동 변경하지 않는다.
- 최종 공개 예시: `evaluation/runs/generic-calculation-20260928/financial-v5.json` 및 `.formula.json`, Edge `financial-desktop.png`. 국내 예금이자만 1억원인 거주자 예시 국세 산출세액 1,588만원, 예시 국세 원천징수 1,400만원, 차액 188만원. 기본공제 반영/세액공제 전/지방소득세 제외이며 20260421 보관 시행본 기준이다. 세무 골드 정답으로 사용하지 않는다. 실제 대화 DB에는 쓰지 않았다.
- `financial-v4`는 실패 진단이다. 코드의 한글 복합 단위/분수형 세율 해석 오류는 수정했다. 앞선 실모델 반복에서는 가정과 산식 불일치도 거부됐으며 최종 성공 한 번으로 전체 성공률을 주장하지 않는다. dev/probe_reliable_answer.py는 공개 스모크에서 모델 산식/Judge를 별도 `.formula.json`으로 기록한다. 개인 정보 질문에 무단 적용하지 않는다.
- 검증: 최신 백엔드 909 passed/2 skipped/5 subtests passed, 프런트엔드18. `frontend/tests/formula.browser.cjs`는 실제 성공 JSON을 `UI_FORMULA_JSON`으로 받아 API 대역으로 웹에 표시하고 패널/원문/모바일을 검사한다. 일반적인 표시 샘플을 세무 정확도 평가로 취급하지 않는다.
- 후속: 전문가 정답을 포함한 배당/이자 혼합, 근로·사업소득 병존, 세후 입력, 외국 원천징수, 비거주자, 공제 예외, 금액 경계 사례를 LangSmith에서 반복 평가해야 한다. 일반 계산 질문의 다른 세목 라우팅은 전용 계산기 우선과 모델 제안을 따르므로 모든 미지원 유형을 자동 탐지한다고 보장하지 않는다.
- 시점 한계: 현재 범용 계산은 구체적인 사건일/과거 연도를 명시하면 계산을 공개하지 않고 원문 설명으로 돌아간다. 현재 연도 또는 날짜 미상만 확보한 현행 시행본 기준 예시를 제공한다. 공식 최신 버전 확인과 historical 원문 선택/부칙 연결이 후속 과제다. 원문 근거가 부족하면 여전히 숫자를 제공하지 않을 수 있다.

## 2026-09-28 대화형 답변 표시 개선

- 질문에 직접 답하기, 짧은 문단/조건을 포함한 강조/필요한 목록을 생성 지시에 추가했다. `question_part`는 원 질문의 유일한 연속 발췌로 주장 표시 순서만 정하며 의존성을 우선한다. 생성/Judge에는 기존 OpenRouter GPT-6 Luna, 임베딩에는 Ollama를 유지한다.
- 렌더러는 짧은 연속 항목 2~8개만 표로 묶고 긴 설명은 소제목·문단으로 표시한다. 별도 요약 모델이나 검증 이후 세무 문장 재작성은 추가하지 않았다. 근거 목록은 설명/확인사항 뒤로 이동했다.
- 웹에서는 완료된 성공 도구를 접고 진행/실패 상태는 노출한다. 키보드 접근 가능한 표 스크롤, 문단/제목/목록 간격을 개선했다. frontend/tests/answerPresentation.browser.cjs는 합성 응답으로 PC·모바일 표시를 검사한다. tools.browser.cjs는 DONE 뒤 서버 이력을 다시 읽는 현재 동작에 맞게 합성 저장 응답도 갱신하도록 수정했다.
- 질문 계획의 배경 인물 과잉 분해와 개별 호출에서 답변 전체 근거 부재를 단정하는 문구는 지시를 보완했다. 서로 다른 납세의무를 자동 병합하거나 검증된 문장을 의미 유사도로 삭제하지 않는다.
- 백엔드·프런트엔드 재빌드 완료. 백엔드 884 passed/2 skipped/5 subtests passed, 프런트엔드 18 passed, Edge 표시/도구 연결 검사 2종 통과. 로컬 `evaluation/runs/answer-presentation-20260928/`에 스크린샷과 실모델 JSON을 보관한다. 기존 웹 답변 문장에는 소급 적용하지 않으며 새 질문/다시 답변이 필요하다. CSS와 도구 카드 배치는 새로고침하면 기존 대화에도 적용된다.
- 남은 답변 충족도 과제: `gift-final.json`의 질문은 성년 자녀 현금 증여의 공제 요건·신고·서류다. 최종 계획은 1개 쟁점으로 줄었고 3/3 주장이 공개됐지만, `coverage['1'].missing_requirements`는 제53조 공제 요건/한도 등을 여전히 누락으로 표시하고 `judge.missing_issue_ids=['1']`, 전체 status=limited다. 결과는 신고/서류 중심이며 핵심 공제 설명의 안정적 확보는 해결되지 않았다. 검색 후보→쟁점 관련성 선택→주장 생성에서 제53조 근거가 빠지는 지점을 후속 점검해야 한다. `gift-ordered.json`은 보완 전 두 주체 중복 사례이므로 최종 출력으로 오인하지 않는다. 이는 이번 표시 개선의 검증과 구분한다.

## 2026-09-28 반복 항목명·조건 개선

- `claim_verification.py`의 생성 지시에서 공통 출처/연도 범위를 conditions로 모으고 본문 조건을 다시 나열하지 않도록 했다. 렌더러는 동일 쟁점의 연속된 동일 제목을 한 번 표시하며, 개별 설명과 검증 원본은 유지한다. 일반적인 연도 미확정 조건만 공통 시점 안내로 모으고 구체적인 원천징수 기한·귀속·상환 조건은 보존한다.
- 최종 백엔드를 재빌드했으며 전체 테스트 878 passed/2 skipped/5 subtests passed. 실모델 여행비 사례는 3/3 공개, Judge 오류 0, 제목/시점 각 1회, 자료 확인 목록 1개였다. GPT-6 Luna 생성/Judge와 Ollama 임베딩을 유지했다.
- 실제 검증 출력은 컨테이너 `/tmp/travel-repeat-20260928-v2.json`에 있으며 컨테이너 재생성 시 사라진다. 웹 채팅 DB에는 쓰지 않았고 기존 답변 버전은 바뀌지 않았다. 화면 확인에는 새 질문 또는 다시 답변이 필요하다. 유사 문장 전체를 의미상 중복으로 추정해 삭제하지 않으므로 임의 표현의 반복까지 전부 제거한다고 보장하지 않는다.

## 2026-09-28 답변 형식 가변화

- `render_structured_answer`를 고정 4단계 목차에서 질문별 배치로 변경했다. 간단한 질문은 본문부터, 복합 질문은 세목별 제목부터 시작한다. 공개된 항목 주장이 2개 이상 있을 때만 표를 쓰고, 근거는 법령별로 묶는다. 검증 경계와 시점 유보는 유지한다.
- 로그인된 Edge의 개인카드 지출 사례를 다시 답변해 2/2 버전이 새 형식으로 표시되는 것을 확인했다. 최신 이미지 전체 테스트는 875 passed/2 skipped다. 과거 답변 버전은 그대로 남아 있다.

## 2026-09-28 복합 답변 출력 형식

- `claim_verification.py`의 공개 단계에 4개 섹션(결론, 상세 설명, 확인한 법적 근거, 실무 확인 사항)을 추가했다. 질문의 항목명·금액과 일치하는 공개 주장만 항목별 표에 넣고, 같은 항목의 복수 주장은 한 행으로 병합한다. 공개되지 않은 항목은 새 판단을 만들지 않고 누락을 표시한다.
- 실모델 개인카드 지출 사례는 13/13 주장 공개, 두 세목 답변, Judge 오류 0, 항목 표 2개를 확인했다. 이후 표 중복 행 병합 및 빠진 항목 안내를 단위 테스트로 검증하고 최신 백엔드를 재빌드했다. 로그인된 Edge 채팅에서도 같은 질문의 저장 답변이 네 섹션과 항목 표 2개로 렌더링되고 선물비 표 행이 한 줄인 것을 확인했다. 전체 테스트는 874 passed/2 skipped다.
- 이 형식 변경은 세무 정확성 입증이 아니다. 거래 시점이 없고 실제 증빙이 없으므로 각 비용의 확정 손금·공제·가산세 판단은 여전히 조건부다. 운영자 골드셋 검수는 LangSmith에서 진행한다.

## 2026-09-28 UI 평가 후속

- 로그인된 Edge의 6개 분야 대화에서 답변을 다시 생성했고, 저장된 대화별 최신 버전을 확인했다. 부가가치세 3, 법인세 3, 종합소득세 2, 증여세 2, 양도소득세 2, 상속세 2다. `evaluation/runs/ui-tax-fields-20260928/regenerated.json`은 Git 제외 경로의 로컬 평가 기록이다.
- UI 자동화가 양도소득세 대화 로딩 전에 증여세 답변을 읽었던 경쟁 상태를 수정했다. 다음 실행에서도 선택한 대화의 질문 본문과 기대 질문이 일치한 뒤 재생성해야 한다.
- 렌더링 순서 및 중복 시점 문구 수정 후 법인세를 재생성해 확인했다. 다른 5개 화면의 저장 답변은 해당 렌더링 수정 직전 생성본이다. 사용자 검토 시 최신 답변을 다시 생성하면 새 렌더링이 반영된다.
- 과거 시점 법령 버전 확인 및 분야별 세무 정확성 골드셋 평가가 남아 있다. 확인되지 않은 시행본을 해당 연도에 적용했다고 주장하지 않도록 현재 제한을 유지한다.

## 2026-09-28 웹 실사용 품질 점검 후속

- 여섯 분야의 실제 웹 대화는 로그인한 기존 계정에 남겼다. 최초 답변은 법령 시점 차단과 과잉 쟁점 분해 탓에 부가가치세가 전체 보류됐고, 다른 분야에도 문장 중복과 일부 쟁점 보류가 있었다. 스크린샷과 UI 응답은 Git 제외 경로 `evaluation/runs/ui-tax-fields-20260928/`에 있다.
- 최신 수정은 `source_summary`를 통해 확보된 법령 원문의 일반 기준만 조건부 설명하며, 2025년 사건에 적용할 역사적 버전은 아직 결정하지 않는다. 연도 중 여러 개정본이 있으므로 실제 거래일·귀속시점과 적용례·경과규정을 확인한 역사적 검색 연결이 후속 과제다.
- 실모델 2025년 부가가치세 진단 실행은 1개 쟁점, 4개 주장 공개, 공식 인용 3건으로 개선됐다. 향후 LangSmith 전문가 골드에서 근거 충족 Judge의 과다 차단, 과거 적용 false pass, 조건 문구 중복을 측정해야 한다. 전문가 정답 검수는 수행하지 않았다.

## 2026-09-28 일반 질문 보류 수정 후속

- 앞선 기록의 광범위한 도구 오분류·전체 답변 일괄 생성·인용 발췌 복사·재시도 시 통과 주장 폐기 문제를 수정했다. 현 구조와 제한은 `CURRENT_STATUS.md`, `RELIABILITY_WORKFLOW.md`, ADR-061을 우선한다.
- 공식 원문 복구는 **같은 MST/시행일/법령명/공포일과 XML 해시가 확인되는 기존 스냅샷**에 한한다. 전체 법령·임베딩·GraphRAG 백필은 하지 않았다. 스냅샷이 없거나 다른 버전이면 불완전한 근거를 계속 차단한다. 그 밖의 누락 형태·버전 적용기간 정합성은 후속 데이터 감사 대상이다.
- 금융소득 종합과세 비교과세·배당세액공제·원천징수 정산 전용 계산기는 미구현이다. 현재는 구체적인 입력과 지원 범위를 안내하며, 조건을 추가하면 자동으로 확정세액을 계산할 수 있다고 약속하지 않는다. 구현 전 공식 연도별 산식과 전문가 승인 사례가 필요하다.
- 사용자에게 보여주는 설명은 개별 코드/의미 검사를 통과한 범위다. H/I 실모델 실행에서 5개 쟁점 모두 설명이 나와도 누락된 법적 효과와 Judge false pass/false block은 독립 골드로 검증해야 한다. 운영자 평가는 기존 LangSmith를 사용한다.
- OpenRouter 계정에서 실제 `new-account-rpm` 20회/분 응답을 확인해 기본 18회/분으로 호출 간격을 제한했다. 다중 worker 또는 별도 평가 프로세스와 실행하면 프로세스별 제한이므로 계정 전체 한도를 합산해야 한다. 설정은 `OPENROUTER_REQUESTS_PER_MINUTE`.
- 공개 예제 실행 기록은 Git 제외 경로 `evaluation/runs/chat-routing-20260928/`에 보존한다. 테스트 도구는 `dev/probe_reliable_answer.py <새 결과 파일> consulting|general|compound|financial`이며 대화/법령 DB를 수정하지 않는다.
- 최종 이미지 전체 테스트 867 passed/2 skipped, 관련 컨테이너 4개 healthy, diff 검사 통과. 실모델 H/I는 5/5 쟁점·16/18 주장 공개, 호출 간격 적용 후 증여 복합질문은 3/3 쟁점·16/16 주장 공개다. 두 사례 모두 `limited`이며 쟁점별 설명 보완·차단 내용을 독립 전문가가 검수해야 한다. `consulting-all-issues.json`, `compound-paced.json`, `financial-final.json`에 실행 결과를 보존했다.

## 2026-09-28 복합 질문 검색 보강 후속

- 쟁점별 두 벡터 질의·공식 조문 키워드 검색·RRF·GraphRAG와 근거 충족 Judge를 연결했다. Alembic 0009 `pg_trgm` 색인을 적용했다. 기존 업로드 사용자 격리와 원문 조회 경로는 변경하지 않았다.
- H/I 실모델 사례는 부분 답변까지 도달했다. H의 부가가치세 항목에 손금 주장이 섞인 것을 발견해 `손금|익금|소득처분`을 법인세 범위 검사에 추가했다. I의 법인세 항목에 H의 손금 주장이 들어간 것도 발견해 법적 주장에 주체 범위 검사를 복구했다. 최종 이미지의 동일 질문 재실행은 `limited`, 5개 중 1개 쟁점·13개 중 4개 주장 공개였다. 잘못된 세목/주체 주장은 보류됐으나 네 세목의 법적 효과는 아직 충분히 답하지 못한다.
- 다중 쟁점의 근거 판정을 한 Judge 응답으로 묶자 한 ID 오류가 여러 쟁점을 `unverified`로 만들어 전부 보류되는 현상이 있었다. 판정을 쟁점별 독립 호출로 바꾸고, 재평가 오류 시 이전 `missing` 상태를 보존한다.
- 다음 단계는 H/I의 세목별 골든셋과 공식 조문 원본을 고정해 Recall@K 및 Judge false block을 측정하고, 생성 단계가 여러 쟁점의 증거를 한 번에 받아 잘못 인용하는 문제를 쟁점별 생성·검증으로 분리하는 것이다. 현재 보류의 주요 코드 사유는 인용 발췌 불일치, 주장 의존관계, Judge 불충분, 세목 혼입이다. 전문가 정답 검수 전까지 자동 결과를 완전한 세무 답변으로 간주하지 않는다.
- 근거 충족 Judge는 검색 후보 관련성과 쟁점 전체 충족을 잠정 판정할 뿐, 법적 정답률을 입증하지 않는다. 과거 현행 조문 자료의 호 목록 누락과 시점 버전 검증은 별도 데이터 보정이 필요하다. 전체 재수집은 실행하지 않았다.

## 2026-09-28 GraphRAG 연결 복구 후 확인

- `tax_neo4j`가 종료된 상태에서 백엔드만 재빌드돼 그래프 확장이 기본 벡터 결과로 복귀한 문제를 조사했다. 기존 볼륨으로 Neo4j를 기동해 현행 조문 6,675개와 CITES 8,387개를 확인했고 H/I 5개 쟁점의 그래프 추가를 재현했다.
- WSL 실행 스크립트 두 개에 활성 GraphRAG의 Neo4j 선기동·healthy 대기를 추가하고 의존성 API에 그래프 연결 상태를 표시했다. GraphRAG 값은 변경하지 않았고 Ollama 임베딩·OpenRouter 생성 설정도 유지했다.
- 이전 로그의 `ValueError`는 예외 종류만 남아 정확한 스택을 복원할 수 없다. Neo4j 종료 요청 주체/Exit 137의 직접 원인도 미확정이다. 재발 시 Docker 이벤트와 Neo4j 로그를 함께 조사한다.

## 2026-09-28 검증 흐름 구현 이후 후속

- 9/27 출처 표식 위조 및 단일 세목 축소 문제는 수정했다. 현재 구조와 모드/예산은 `RELIABILITY_WORKFLOW.md`를 따른다. 이 아래 날짜별 미수정 기록은 당시 상태다.
- Judge enforce 운영 승격 전 독립 전문가 골드의 false pass/false block/unknown/필수 쟁점 누락을 교정해야 한다. 현재 기본 shadow에서 의미 판정은 검색 보완과 진단이며 코드상 원본/인용 오류는 즉시 차단한다.
- 현행 DB 일부 조문의 호 목록 누락을 확인했다. 알려진 누락 구조는 차단했지만 데이터가 보완된 것은 아니다. 공식 XML·버전별 원문과 대조 후 대상 법령 및 임베딩 보정 범위를 정할 것. 전체 재수집/백필은 수행하지 않았다.
- 실모델 점검 당시 GraphRAG가 ValueError로 기본 검색에 복귀한 건은 위의 연결 복구 작업 후 같은 쟁점 검색에서 그래프 추가를 확인했다. 원래 ValueError의 상세 스택과 Neo4j 종료 요청 주체는 당시 로그에 없어 미확정이다.
- 최종 최신 이미지 백엔드 794 passed/2 skipped, 프런트엔드 18 passed·빌드 성공, backend/frontend 재빌드 적용 및 readiness 확인. 실제 사례 산출물은 `evaluation/runs/reliability-20260928/`에 있으며 전문가 골드가 아니다. 운영자 평가는 계속 LangSmith이며 관리자 대시보드는 추가하지 않았다.

## 2026-09-27 도구 선택·근거 채택 후속 우선 작업

- `TOOL_AND_EVIDENCE_RELIABILITY_PLAN_2026-09-27.md`의 합성 재현 2건은 미수정이다. 첫째 복수 세목 감지 후 모델의 단일 law로 최종 검색이 축소될 수 있다. 둘째 사용자 업로드 본문에 삽입된 `[출처: ... | 법령명 | 법률]` 표식이 공식 근거로 검증될 수 있다. 특히 두 번째는 본문과 서버 출처 정보의 신뢰 경계 문제이므로 먼저 수정한다.
- 사용자 문서 category와 공식 수집 origin을 분리하고, citation guard가 문자열 표식을 재파싱하지 않도록 구조화 근거 ID·원본/버전/hash를 전달한다. 쟁점별 계획/도구 조건/검색 충족 및 Judge 교정은 연구 문서의 후속 순서를 따른다. 이번에는 연구·문서화만 했으며 기존 서비스나 DB를 변경하지 않았다.

## 2026-09-27 가공거래 사례 도구 오분류

- `세금계산서`의 `계산`으로 계산 도구 의도가 참이 되어 일반 세무 분석 질문이 도구 선택으로 넘어가는 문제를 재현·수정했다. 해당 질문의 `has_tool_intent`는 수정 후 거짓이며 정상 RAG 경로를 사용한다.
- 실서비스에서 같은 질문의 생성 답변과 세무 정확성은 재검증하지 않았다. 법령 원문 조회 실패 시 전체 답변을 보류하는 기존 정책은 명시적 조문 조회 안전 장치로 유지한다. 복합 질문에서 도구 선택이 다시 잘못될 수 있는지 별도 사례 확장이 필요하다.

## 2026-09-27 구조화 검사·근거 패널·LangSmith 연결 후속

- 채팅의 인용/계산 검사 결과는 답변과 함께 저장되고 SSE 및 근거 패널에 표시된다. 평가기의 Judge 결과는 해시 검증 후 LangSmith 게시 계획의 항목별 feedback으로 변환된다. 백엔드·프런트엔드는 재빌드·실행했고 HTTP/의존성 상태 및 전체 테스트를 확인했다. 원격 LangSmith 게시는 아직 수행하지 않았다.
- 사용자 확인에 따라 현재 생성 모델은 OpenRouter GPT-6 Luna, 임베딩은 Ollama다. `dev/docker-up-wsl.sh`로 배포했다. llama.cpp 전용 스크립트는 이 구성에 맞지 않으며 사용하지 않는다. 모델 목록 전체 조회로 발생한 의존성 점검 ReadTimeout은 단일 모델 조회로 수정했고 `ready`를 확인했다.
- 서비스 검사는 조문 식별자와 계산기 최종 금액 대조 범위다. 주장과 근거의 의미 일치, 법령 적용 시점, 예외 누락은 자동 입증되지 않는다. 독립 정답을 갖춘 전문가 승인 평가셋, Judge 교정 및 오답 재현율을 마련한 뒤 서비스 사용 여부를 결정한다.
- 실제 계정으로 전송할 계획은 `evaluation/LANGSMITH.md` 절차에 따라 내용·지역·해시를 검토해야 한다. 현재 답변 버전 ID와 평가 run의 자동 상호 참조는 없으며, 평가는 데이터셋 case ID/관측 payload hash로 추적한다.

## 2026-09-27 운영자 평가는 LangSmith로 확정

- ADR-058을 따른다. 사용자 채팅 근거 패널과 LangSmith 운영자 평가를 연결하며 별도 관리자 대시보드/역할은 이번 범위에 추가하지 않는다.
- 검사 통과와 LangSmith 전송 성공은 분리한다. 저장 Judge 결과의 항목별 feedback 준비는 구현됐으며 운영 평가의 정확도 교정은 위 후속 항목을 따른다.

## 2026-09-27 LLM Judge 연구 후속

- 기존 구현을 활용한 세무 평가 설계는 `LLM_JUDGE_TAX_VALIDATION_RESEARCH_2026-09-27.md`에 있다. 다음 구현은 평가/서비스 guard 동기화 → 실제 컨텍스트와 독립 정답 입력 → 주장별 판정 → 기존 판례 오답으로 교정 → 항목별 지표·재개 기능 순이다.
- 고정 근거 어댑터는 이후 채팅과 동일한 전송 전 검사를 사용하도록 수정했다. 전문가 골드와 실제 오답 사례를 통한 평가 유효성 확인은 남아 있다.
- 기존 `answer_pilot.json`은 5개 draft/recorded 카드이며 설명에 오래된 Judge 미구현 문구가 남아 있다. 기존 run과 hash가 연결되므로 원본을 덮어써 승인하거나 변경하지 말고 새 버전으로 확장한다.
- 관련 기존 테스트 82 passed. 다음 단계의 모델 호출 성능·비용·세무 정확도는 아직 측정하지 않았다.

## 2026-09-27 법령 답변 검증·금액·문서 개선 후속

- 현재 작업 트리에 새 코드가 있으며 실행 중 Docker 서비스에는 아직 반영하지 않았다. 최신 backend 이미지 전체 pytest 761 passed/2 skipped, frontend 16 passed/빌드·Nginx 설정 검사 통과. 실제 프록시 경계 업로드·브라우저 전체 검증은 남아 있다.
- 부정확한 인용·계산값은 일반/SSE에서 생성 문구를 보류한다. 스트림 최종 답변은 검사 완료 후 전달하므로 첫 토큰 지연과 답변 누락율을 실사용 사례로 확인한다. 법적 의미 검증은 별도이며 `docs/ai/TAX_ACCURACY_GATE.md`에 전문가 골드 설계 초안을 남겼다.
- 동일 파일명 교체·여러 탭 검토의 SHA/revision 경쟁 테스트, 실제 frontend 경유 50MiB 업로드 경계, GraphRAG 종료 상태는 후속 운영 검증이다.

## 2026-09-27 프로젝트 분석 후 우선 수정 제안

- 사용자 요청은 프로젝트 분석 및 해결책 제안이다. 상세 근거·재현·완료 기준은 `docs/ai/PROJECT_REVIEW_2026-09-27.md`. 서비스 코드와 데이터는 변경하지 않았으며 아래 항목은 아직 미수정이다.
- 먼저 citation_guard의 법령/조문 교차·가지번호 부분 일치·항 누락을 구조화 근거 대조로 교체한다. 계산기의 float 변환으로 합성 `180×0.35=62`가 나오는 문제와 금액 정규식이 `1.5억원`에서 `5억원`을 잡는 문제를 회귀 테스트로 고정한다.
- Nginx client_max_body_size를 앱 파일 제한과 multipart 여유분에 맞춘다. 무인증 512KiB 업로드는 401 JSON, 2MiB는 413 HTML로 재현했다. 실제 frontend 경유 경계값 검증이 필요하다.
- 문서 검토 저장 요청에 expected_sha256/version을 넣고 잠금 안에서 대조해야 한다. 현재는 이전 화면의 입력에도 최신 원본 hash를 붙일 수 있다. 동일 이름 동시 업로드·검토의 원본/청크 일관성도 후속 확인한다.
- GraphRAG=true이나 tax_neo4j는 Exited(137), OOMKilled=false로 확인됐다. 종료 원인을 추정하지 말고 실제 endpoint·컨테이너 이벤트를 조사하며 dependencies health에 그래프 상태를 추가한다. 이번 세션에서 재기동하지 않았다.
- 검증: 실행 중 backend 753 passed/2 skipped, frontend 16 passed. 핵심 6개 파일의 로컬/컨테이너 SHA-256 일치. 실제 세무 정확도·부하·브라우저 E2E·복원 시험은 미수행이다.

## 2026-09-27 호스트 포트 변경 후 확인

- Compose 프런트엔드 3001, 백엔드 로컬 8001, 선택형 llama.cpp 생성 호스트 8004로 변경했다. 내부 백엔드 8000은 유지한다. 스모크·브라우저 테스트 기본 URL도 3001로 바꿨다.
- WSL 스크립트로 backend/frontend 재빌드·기동했고 둘 다 healthy. Windows 3001 UI/API 프록시와 8001 API 문서 HTTP 200, 3001 origin CORS preflight 200, 최신 백엔드 753 passed/2 skipped, 프런트 16 passed/빌드, 3001 경유 임시 문서 5종 스모크 통과. llama.cpp overlay의 새 호스트 8004는 정적 설정만 변경했고 이번에 기동하지 않았다.

## 2026-09-26 업로드 UI 후속

- PDF 전용 프런트 검사를 제거하고 다중 형식 선택·끌어놓기·사전 검사·처리 결과·청킹 상태 배지를 추가했다. `chunking_version=2`는 신규 업로드에만 저장된다. 과거 문서는 자동 재색인하지 않았다.
- 후속 검수: 실제 대용량 OCR 진행률은 아직 없고 현재 화면은 완료 전 대기 상태만 표시한다. 형식별 검색 정확도·출처 위치·PDF 표 인식은 골든셋 평가가 필요하다. 같은 이름 재업로드는 검토값을 초기화하므로 사용자 확인 UX를 유지한다.
- 배포·검증: WSL 가상환경에서 `dev/docker-up-wsl.sh backend frontend`, 최신 컨테이너 753 passed/2 skipped, 프런트 단위 16 passed/빌드 성공, 다섯 형식 임시 API 업로드·검색·위치 메타데이터 스모크 통과. 별도 브라우저 자동화는 이번 변경에서 실행하지 않았다.

## 2026-09-26 사용자 문서 구조화 청킹 후속

- `extractors.py`와 `structured_chunker.py`로 새 업로드 청크에 위치·제목·표 행·명시적 조/항/호를 보존한다. 기존 업로드는 변경하지 않았으므로 새 청킹 적용이 필요하면 사용자별 원본 존재 확인 후 재업로드 또는 별도 재색인 절차를 설계해야 한다.
- PDF/OCR의 표 셀 추출, HWPX 제목 스타일 판별, 긴 표 행의 원자성, 검색 정확도·인용 위치 정확도는 미검증이다. 형식별 골든셋과 hard negative를 만들어 기존 청커와 비교한다. OCR 숫자를 상담 계산에 자동 반영하지 않는다.
- 최신 backend 이미지를 `dev/docker-up-wsl.sh backend`로 적용했다. 컨테이너 전체 753 passed/2 skipped, `dev/probe_document_formats.py` 5종 API·벡터·위치 메타데이터 스모크 통과. 프런트엔드 변경은 없었다.

## 2026-09-26 문서 업로드 형식 확대

- `app/services/document/extractors.py`가 PDF(스캔 OCR), DOCX, HWPX, PPTX, HTML/HTM의 본문을 제한된 크기로 추출한다. Docker 이미지에 한국어·영어 Tesseract와 PDFium 바인딩을 추가했고, 비-PDF 원본은 같은 출처에서 실행되지 않도록 다운로드 처리한다. 새 업로드의 JSONB 메타데이터는 객체로 저장된다.
- 실제 검증: `PYTHONPATH=. python dev/probe_document_formats.py`가 임시 사용자 데이터로 5종 업로드 → OCR/원본 → 활성 임베딩 → 사용자 문서 검색까지 통과 후 정리. 최신 컨테이너 `pytest -q`: 746 passed/2 skipped, 프런트엔드 14 passed/빌드. 읽기 전용 DB 점검에서 문자열형 메타데이터 0건.
- 후속: 스캔 품질별 한국어 OCR 평가, 이미지형 HWPX/DOCX/PPTX 추출, 대용량 OCR 작업 큐·진행률, 페이지/슬라이드별 근거 위치의 구조화가 필요하다. OCR 추출값은 원본 대조 없이 계산이나 세무 판단에 자동 반영하지 않는다.

## 2026-09-26 상담 이후 업무 확장

- Alembic `20260926_0008` 적용 및 API/React 배포: 상담 PDF, 문서 원본·후보 검토와 확인 금액 적용, 계산 시나리오 비교, 법령 조문/버전 비교, 공식 일정 선택·준비 상태 관리.
- 검증: 최신 컨테이너 `pytest -q` 733 passed/2 skipped, frontend 14 passed/빌드, 임시 계정 실제 API `PYTHONPATH=. python dev/probe_workspace_features.py` 통과. PDF 합성 샘플 렌더링 확인.
- 후속: 기존 업로드는 원본이 없으므로 재업로드 안내 필요. 이미지형 PDF OCR, PDF 추출 품질 평가, 실제 문서-금액 자격 검증, 외부 알림, 세무 정답성 및 시점별 법적 적용 검수는 미구현. 원본 PDF 저장에 따른 백업·보존/삭제 정책도 운영 전 확정해야 한다.

## 2026-09-26 세목별 상담 확장

- 6개 세목(종합소득세·양도소득세·상속세·증여세·부가가치세·가산세) 상담 질문/서류 규칙, 세목별 입력 소유 경계, 조회 기준일별 DB 세율·공제 선택과 결과 저장을 배포했다. Alembic head `20260926_0007`; backend healthy, frontend 3002 HTTP 200.
- `PYTHONPATH=. python dev/probe_consultation_case.py`: 임시 계정으로 6개 세목 생성·입력·계산·삭제, 타 세목 필드 거부, 문서 상태 확인 후 정리. 관련 없는 조건부 질문을 생략한다. 합성 Edge 브라우저 종합소득세·증여세 흐름 통과. 최신 컨테이너 730 passed/2 skipped, frontend 14 passed/빌드 통과.
- 후속: 현재 계산기 코드 상수와 세목별 누락 조건을 공식 연도별 자료·전문가 판단과 대조한다. 기준일이 법적 사건일이나 신고 귀속기간의 정확성을 보증하는 것은 아니다. 실제 세무 계산 골든셋, 공제 자격, 경과규정 및 서류 자동 검증은 미구현이다.

## 2026-09-26 종합소득세 상담 작업 공간

- Alembic `20260926_0006` 및 `/api/consultation-cases`와 React 상담 화면을 배포했다. 질문 → 4개 계산 조건 확인 → 사용자 PDF 연결/자료 없음 기록 → 귀속연도 기준 참고 계산 및 근거 질문의 첫 수직 흐름이다. `dev/probe_consultation_case.py` 실제 API 스모크는 임시 데이터만 만들고 제거했다.
- 검증: 최신 backend 컨테이너 `722 passed, 2 skipped`, frontend 14 passed/빌드 성공, `frontend/tests/cases.browser.cjs` 합성 Edge UI 통과, Alembic head 적용, frontend 3002 HTTP 200.
- 후속: 종합소득세 소득 유형·개별 공제 및 공제 증빙의 자격 규칙을 도메인 전문가와 설계하고, 귀속연도별 세율/공제 DB와 경과규정의 법적 적용을 검수해야 한다. 연결 문서는 파일명 기반이므로 동일 파일명 재업로드를 독립 버전으로 추적하려면 문서 ID 도입이 필요하다. 실제 신고서 자동 작성/제출과 세무 정답성 검증은 이번 범위가 아니다.

## 2026-09-26 관계 블라인드 검수 인계
- `evaluation/sources/kg_relation_blind_review_20260926.json`에 56건 블라인드 양식을 생성했다. Judge 예측·추출/혼동 생성 유형을 포함하지 않으며 `review` 필드는 전부 비어 있다. 파일은 Git 제외이며 기존 풀·결과는 보존했다.
- 실제 법령 검수자가 문구상 관계 라벨, 원본 확인, 대상 버전 시점 상태, 이유·검수자·날짜를 직접 기록해야 한다. 완성본을 새 파일로 저장한 뒤 `python -m evaluation.kg_relation_human_review finalize`로 엄격 검증하고 `kg_relation_score.py`로 비교한다. 정확한 명령은 `evaluation/KG_RELATION_REVIEW.md`.
- 아직 인간 골드 0건, 품질 점수 없음, Neo4j 승인/서비스 반영 없음. 모델이 스스로 인간 라벨을 채워서는 안 된다. 양식의 reviewer는 인증된 사용자 계정이 아니므로 전문가 검수·이중검수·불일치 조정은 운영 절차로 남는다.
- 새 백엔드 이미지는 빌드했지만 실서비스 컨테이너는 교체하지 않았다. Compose 환경의 일회성 최신 이미지 컨테이너에서 전체 테스트 716 passed/2 skipped. 단독 `docker run`은 기존 DB/모델 설정 의존 테스트 3건이 실패했으나 Compose 환경에서는 통과했다.

## 2026-09-26 관계 Judge 전수 진단 후 인간 검수
- 56건 전수 2회 진단의 최종 로컬 결과는 `evaluation/runs/kg-relation-final-20260926.json`이다. 모두 `advisory_only`; 추출 48건은 `supported`, 대상 교환 혼동 8건은 `unsupported`로 합의했다. 총 Judge 시도 144회(429 및 원문 인용 검증 오류 재시도 포함), 제공자 반환 총 65,245토큰·0.0100509 USD. 성공률이나 법적 정답률로 발표하지 않는다.
- 인간 검수자는 Judge 판정이 없는 `evaluation/sources/kg_relation_stratified.json`에서 원문·출처·시점·관계 의미를 독립 검토하고 별도 `human_relation_gold`에 검수자·날짜·이유를 기록해야 한다. 골드 0건이며 Neo4j 승인/서비스 변경은 없다. 자세한 인계는 `evaluation/KG_RELATION_REVIEW.md`.
- 완료된 보고서의 실패 카드만 새 결과 파일에 재시도할 수 있도록 `--retry-from`과 요청별 `--delay-sec`를 추가했다. 후속 과제는 인간 라벨 확보, `kg_relation_score.py` 비교, 시점상 적용 및 실제 질문 적합성 평가다.

## 2026-09-26 관계 평가 표본·배치 확장
- `evaluation/kg_relation_review.py --auto`로 기준일 2026-09-26 이전 시행 버전만 포함한 6개 법령·56개 후보 카드 생성. 법률/시행령/시행규칙 19/19/18, 과거/최근 27/29, DEFINES/CITES 28/28, 대상 교환 혼동 후보 8건. 결과 `evaluation/sources/kg_relation_stratified.json`은 Git 제외. 최초 초안에는 미래 시행 버전이 섞였으나 기준일 필터 추가 후 초안·해당 진단 파일을 제거했다.
- 전체 56건 원본 재검증 결과 `source_verified=56`; 저장 결과 `evaluation/runs/kg-relation-preflight-asof-20260926.json`. OpenRouter Luna 2건 실호출 결과 `advisory_only=2`, 시도 2회, 제공자 보고 727 입력/141 출력 토큰·cost 0.0001432. 결과 `evaluation/runs/kg-relation-asof-smoke-20260926.json`. 모두 모델 의견이며 인간 골드 라벨은 0건.
- `KG_JUDGE_*` 전용 설정과 카드별 원자적 체크포인트, 동일 설정 재개/명시적 실패 재시도, 제공자 사용량 기록을 구현했다. 아직 LangSmith 관계 평가 업로드, 전문가 라벨, 실제 법적 적용 판단 비교는 없다.
- 2026-09-26 최신 backend 이미지를 `dev/docker-up-wsl.sh backend`로 재생성했고 `docker exec tax_backend pytest -q`: 705 passed/2 skipped. 체크포인트 중단·재개와 미래 시행 버전 배제·재시도 호출 수 회귀 테스트를 포함한다.

## 2026-09-26 관계 LLM Judge 평가 경로 추가
- `evaluation/kg_relation_judge.py`: 원본 재대조가 통과한 미검수 관계 카드만 provider 중립 `structured()` 호출로 진단한다. 2회 기본 반복, exact 원문 인용 검증, 입력 예산·오류 유보가 있으며 결과를 로컬 JSON으로 저장한다. Neo4j 승인/채팅 경로는 변경하지 않는다.
- `evaluation/kg_relation_score.py`: 별도 인간 검수 gold의 출처 풀 해시·검수자·날짜를 확인한 뒤에만 커버리지/정확도/정밀도/재현율/hard negative 오인율을 계산한다. 실제 인간 gold는 아직 0건이고 LangSmith 업로드도 아직 연결하지 않았다. 문서: `evaluation/KG_RELATION_REVIEW.md`.
- 남은 일: 법률·시행령·시행규칙과 시대별 층화 카드 확장, 전문가 라벨 확보, Judge vs 인간 골드 비교, 시점상 적용 판단 평가, LangSmith 전송 범위 검토. 현재 관계 Judge를 실제 법적 정확도나 자동 승인 장치로 취급하면 안 된다.
- WSL 실호출 스모크: OpenRouter `openai/gpt-6-luna`로 소득세법 관계 카드 1건을 2회 진단했고 두 실행이 모두 `supported`로 일치했다. 저장 위치는 Git 제외 `evaluation/runs/kg-relation-smoke-20260926-final.json`. 이것은 모델 의견일 뿐 정답률·전문가 승인 결과가 아니다. 최초 스키마의 선택 필드는 OpenRouter strict JSON 요청이 거절되어, 모든 출력 필드를 필수로 고친 후 성공했다.
- 최신 backend 이미지를 `dev/docker-up-wsl.sh backend`로 재생성했고 컨테이너 healthy, 전체 테스트 698 passed/2 skipped를 확인했다. 이 테스트는 전문가 골드와의 실제 품질 비교를 대체하지 않는다.

## 2026-09-26 과거 법령 XML 검수 오탐 및 관계 검수 카드
- 버전 3162·3163의 제125조에는 같은 조문번호의 개정 지시문과 조문 본문이 별도 `law_history.articles` 행으로 보존되어 있다. 두 행의 XML `조문내용`은 각각 자신의 본문에 포함된다. 기존 `validate_all_sources()`가 조문번호로 본문을 사전화하면서 마지막 행만 남겨 2건을 오탐했다. 이제 `source_article_id`로 정확한 원본 행을 비교한다. 원본 DB·Neo4j 데이터는 변경하지 않았다.
- `tests/test_tax_knowledge.py`에 중복 조문번호 오탐 방지와 진짜 XML/본문 불일치 감지 회귀 테스트를 추가했다. 전체 5,400개 버전(조문 1,038,278행, 구조 단위 6,924,423개) 재검수 결과 해시·파싱 오류 0, XML/본문 불일치 0이다. 중복 구조 단위 1,734개/101버전은 그대로 보존·모호성 차단 대상이다. 최신 backend 이미지 `pytest -q`: 689 passed, 2 skipped.
- `evaluation/kg_relation_review.py`와 `evaluation/KG_RELATION_REVIEW.md`를 추가했다. 실제 원본의 정의·인용 관계에서 재현 가능한 미검수 카드를 만들며, `evaluation/sources/kg_relation_review_pool.json`에 초기 13건(DEFINES 5, CITES 8)을 생성했다. 모두 소득세법 버전 306의 후보이고 골든 라벨은 0건이다. 버전 3162·3163 제125조는 관계 후보가 없어 카드 0건이 정상이다. 검수자 선정, 법률/시행령/시행규칙·시대별 층화, hard negative 라벨링, dev/test 분할은 미완료다. Neo4j 승인 상태와 채팅 검색 경로는 바꾸지 않았다.

## 2026-09-25 과거 Knowledge Graph 전수 적재 이후 남은 검수

- `scripts/sync_tax_knowledge.py all` 미처리 0, `audit` 5,400/5,400 및 노드 6,924,423/6,924,423·고유 관계 1,313,901/1,313,901 일치. 중복 참조 101개 스냅샷의 1,734개 구조 단위는 순서 식별자로 분리했다. 새 자료를 수집하면 `all --apply`로 추가분만 재개하고 `audit`/`validate`를 다시 실행한다.
- 당시 보고된 버전 3162·3163 제125조의 XML/본문 불일치 2건은 위 2026-09-26 조사에서 검수기 오탐으로 해결됐다. 원본/색인 재생성은 필요하지 않다. 같은 번호의 개정 지시문과 본문 조문은 계속 공존하므로 임의의 조문 선택이나 자동 관계 승인은 금지한다.
- 후보 1,313,898개는 기계적 원문 추출 결과일 뿐 법률 전문가의 관계 의미·사건 적용시점 검수는 안 됐다. 승인 3개만 과거 RAG에 사용한다. 검수자 인증·이중검수와 관계 정답셋 평가가 다음 단계다. 일반 현행 채팅은 기존 CITES 그래프를 사용한다.

## 2026-09-25 버전별 Knowledge Graph 시범 단계 후속 — 전수 적재 항목은 위 결과로 대체

- 구현·시범 적용 범위와 검수 명령은 `docs/TAX_KNOWLEDGE_GRAPH.md`. 소득세법 버전 306 `제1조의2`에서 3개 관계를 원문 일치 검수했다. 나머지 버전은 위의 전수 적재로 후보 생성까지 완료됐지만, 이를 전체 법령 관계의 법적 검수 완료라고 표시하면 안 된다.
- 과거법령 전 범위의 조·항·호·목 적재와 체크포인트는 위에서 완료했다. 검수자 권한/이중검수, 누락·오탐 계량, 정의 문형 확장, 관계 골든셋 평가는 미완료다.
- 현행 `law_articles` 일부에서 역사 XML 대비 항·호 본문 누락 또는 갱신 시점 차이가 확인됐다. 현행 원문 동기화·개정 시점 정합성 검수 후에만 검수된 Knowledge Graph를 일반 채팅에 확대한다. 지금 일반 채팅은 기존 CITES GraphRAG다.
- 최신 backend 이미지 전체 테스트 682 passed/2 skipped. 시범 과거법령 조회에서 정의·인용 근거 추가를 확인했지만 실제 세무 정답률 검증은 아니다.

## 2026-09-25 AI 작업별 설정 후속

- 6개 작업은 기본 OpenRouter Luna. 각 작업은 `LLM_TASK_<NAME>_*`로 독립 전환 가능하며 예시는 README와 `.env.example`에 있다. 기존 `ROUTING_LLM_*`는 더 이상 사용하지 않는다.
- 실제 세무 골든셋에서 작업별 reasoning effort·모델 변경의 도구 선택 정확도, 검색 Recall, 인용 정확도, 지연, 비용을 비교한다. 합성 스모크는 도구 선택·검색어 형식만 확인한다.
- LangSmith 월간 추적 할당량 429는 별개 문제로 남아 있다.
- 최신 backend 이미지 전체 676 passed/2 skipped, 6개 작업 상태 ok 확인. 실제 세무 답변 품질의 전후 비교는 아직 미실시다.

## 2026-09-25 채팅 모델 역할 분리 후속 검증

- `dev/probe_chat_routing.py`는 비식별 합성 질문의 smoke test일 뿐이다. 실제 세무·법령 질의 골든셋에서 Luna 단일 모델과 nano routing의 도구 선택 정확도, 검색 Recall, 지연시간, 비용을 비교한다.
- 당시 `ROUTING_LLM_*` 옵션은 ADR-043 작업별 설정으로 대체됐다. 현재 로컬 도구 선택은 `LLM_TASK_TOOL_SELECTION_PROVIDER=ollama`와 `LLM_TASK_TOOL_SELECTION_MODEL=qwen3.5:9b`로 설정한다.
- LangSmith 월간 추적 한도 429는 별도로 해결해야 하며, routing 점검 스크립트는 추적을 끄고 수행한다.
- 분리 배포 후 backend 전체 테스트 666 passed/2 skipped, 두 LLM 상태 ok를 확인했다. 프런트엔드 실사용 전 과정의 품질 비교는 미실시다.

## 2026-09-25 장문 이어쓰기·실서비스 LangSmith 추적

- 생성 출력 `length` 이후 원문·근거를 유지한 최대 2회 이어쓰기 및 반복 방지 구현. 완결 후 인용/계산 검증·저장, 미완료는 저장하지 않는다. 일반·SSE·재생성 공통이며 Nginx 900초 read timeout을 배포했다.
- Compose 실서비스의 `CHAT_TRACING_ENABLED=true`, LangSmith 루트 채팅 추적과 하위 단계 전송을 설정했다. SDK 스트림 장식자가 연결 종료 시 검색 작업 취소를 막아 명시적 trace 문맥으로 교체했다.
- 최신 이미지 pytest 661 passed/2 skipped. LangSmith 합성 trace 전송/읽기 검사는 계정 월간 unique traces 초과 HTTP 429로 원격 저장 실패. 키·프로젝트·tracing 설정은 적용됐으며 한도 복구 또는 증액 전에는 새 추적이 LangSmith 이력에 보이지 않는다. 재확인: `docker exec tax_backend python -m dev.probe_langsmith_chat`. 실패 중 생성된 추적의 자동 재전송은 없다.

## 2026-09-25 유료 생성 안정화

- 목적별 추론/출력 예산, 제한적인 HTTP 429 재시도, deadline, 안전한 API 오류, 숫자 usage 로그, 단일 조문 선택 우회, 일반 후속 질문 오탐 완화, Compose tracing opt-in을 구현했다. 기존 DB·벡터·대화 버전 기능은 보존했다.
- 실제 Luna 호환성 검사 6종(일반/stream/JSON/도구 인자/인용 스키마/과거법령 스키마)은 합성 입력으로 성공했다. 세무 판단·계산 정답률이나 실제 사용자 UI 전체 시나리오를 검증한 것은 아니다.
- 최종 WSL 최신 backend 이미지: 652 passed/2 skipped, backend healthy 및 3002 dependencies ready. git diff --check 통과. LangSmith 자동 tracing 런타임 false/false를 확인했고 최종 테스트에서 월간 추적 한도 경고가 사라졌다.
- 남은 과제: 골든셋으로 법령 적용시점·인용·계산 품질 평가, 질문당/사용자당 비용·동시 요청 제한, 민감정보의 OpenRouter 전송 정책, 혼합 의도 및 tool=none(불필요/입력부족) 분리. 긴 맥락은 입력 토큰 예산을 별도로 설계해야 한다.
- 재검증: WSL 가상환경에서 dev/docker-up-wsl.sh backend → docker exec tax_backend pytest -q. 유료 스키마 점검은 docker exec tax_backend python -m dev.probe_openrouter_model openai/gpt-6-luna --pipeline.

## 2026-09-25 GPT-6 Luna 생성 전환

- 실제 `.env`와 예시 설정을 `openai/gpt-6-luna`로 변경하고 Luna 전용 요청 파라미터 및 회귀 테스트를 추가했다. 기존 대화·법령 DB는 변경하지 않았다.
- 비식별 일반/JSON Schema/스트리밍 API 실호출은 모두 성공했고 WSL backend 재빌드·health 확인 및 전체 632 passed/2 skipped를 완료했다. 후속: 세무 골든셋 인용·계산 품질, 요청당 비용과 장기 429 발생률을 확인한다. 개인 세무 서류 외부 전송 정책은 별도 검토가 필요하다. LangSmith 월간 추적 한도 429는 별도 이슈다.

## 2026-09-25 Qwen3.8 무료 모델 사용자 직접 실험

- 로컬 `.env`에서만 Qwen3.8 27B 무료 생성 모델을 선택하고 WSL backend 재빌드·재시작 완료. 실행 컨테이너 설정 일치·health 확인. `.env.example`/운영 권장 모델은 변경하지 않았다.
- 직전 비식별 실호출은 일반/스트리밍/구조화 모두 429였으며 이번 턴은 사용자 직접 채팅 실험을 위해 설정만 전환했다. 별도 실제 생성 호출은 하지 않았다. fallback 없음.

## 2026-09-25 재생성 오류와 Gemma 무료 모델 실험

- 재생성 저장 시 발생한 `get_pool` 지역 변수 충돌을 수정하고 스트림 최종 커밋 회귀 테스트를 추가했다. 일반·재생성 SSE의 미처리 예외는 안전한 오류 이벤트로 전달한다.
- Gemma 4 26B-A4B 무료 엔드포인트 실호출 결과 일반/스트리밍 429, 엄격한 JSON Schema 404. `CHAT_MODEL`은 Dots3로 유지. 무료 모델 한도·구조화 출력 지원 변화 시 비식별 재검증 필요.
- WSL `dev/docker-up-wsl.sh backend`로 재배포, 백엔드·프런트엔드 health 및 Alembic head 확인. 최신 이미지 전체 631 passed/2 skipped. 실제 사용자 대화의 재생성 버튼은 별도 수동 확인이 가능하며, 자동 테스트는 합성 데이터로 동작한다.

## 2026-09-25 동일 대화 답변 버전

- `20260925_0005_answer_versions` 마이그레이션, 마지막 답변 재생성 SSE/버전 선택 API 및 UI를 추가했다. 마지막 질문 수정은 기존 분기 방식 유지.
- 새 모델 출력의 정답성 자체는 이 기능으로 검증하지 않는다. 후속 질문이 이미 작성된 턴의 버전 전환은 의도적으로 지원하지 않는다.
- 백엔드 628 passed/2 skipped, 프런트엔드 14 passed/빌드 및 합성 API Edge 브라우저 통과. 실제 OpenRouter 생성·실제 계정 UI의 수동 클릭 검증은 별도이며 이번 자동 검증은 생성 모델의 답변 품질을 뜻하지 않는다.

## 2026-09-25 내 정보 화면 수정

- `ProfileScreen.jsx`의 세로 flex 카드 축소/내용 잘림을 고치고 `profile.css`로 공통 UI 스타일에 맞췄다. WSL Compose 재빌드 완료.
- `frontend/tests/profile.browser.cjs`는 합성 API로 데스크톱/모바일 카드 가시성, 가로 넘침, 프로필 저장, 비밀번호 변경을 검증하며 Edge headless에서 통과했다. 실제 계정 데이터는 변경하지 않았다. 프런트엔드 14 passed/빌드 성공, 백엔드 623 passed/2 skipped.

## 2026-09-25 채팅 액션 아이콘·공유

- 사용자 마지막 질문의 수정, AI 마지막 답변의 재생성을 아이콘 버튼으로 정리하고 완료된 각 답변에 공유 아이콘을 추가했다. Web Share API 미지원 시 텍스트 복사이며 공유 URL·서버 저장은 없다. 프런트엔드 테스트 14 passed/빌드 성공/재배포 완료. 합성 브라우저 테스트 코드는 수정했지만 Playwright 패키지가 로컬에 없어 실제 브라우저 실행은 후속 확인이 필요하다.

## 2026-09-25 출처 제목 교정 후속 검증

- 일반·스트리밍 채팅의 현행 법령 출처 제목을 DB 원문으로 교정하도록 변경했다. Dots3가 생성하는 제목의 오탈자 사례를 재현하는 테스트와 SSE `replace` 처리 테스트가 있다. 재빌드 후 백엔드 623 passed/2 skipped, 프런트엔드 13 passed이며 컨테이너에서 실제 소득세법 제101조 제목 교정도 확인했다.
- 실제 사용자 질문의 답변·인용 정확도는 아직 검수되지 않았다. 재배포 후 생성 출처의 제목·법령명·조문번호 및 과거 법령 경로를 샘플 검수한다. 스트리밍에서는 교정 직전의 생성 문구가 잠시 보일 수 있다.

## 2026-09-25 Dots3 무료 모델 활성화 — 세무 품질 미검증

- `.env`/`.env.example` 생성 모델을 `dots-studio/dots-3-note-preview:free`로 변경하고 backend 재빌드·재기동. health ready, 일반·JSON Schema·SSE 비식별 실호출 성공, 최신 Docker 전체 pytest 619 passed/2 skipped.
- Qwen3.8 무료 엔드포인트는 ModelRun upstream 공유 처리량 429로 중단된 이력. Dots3는 현재 연결되지만 무료 Preview 모델이라 장기 가용성·한국어 세무 답변/인용 정확도는 별도 골든셋/전문가 검수가 필요하다.

## 2026-09-25 Qwen3.8 27B 무료 모델 고정 후 실제 생성 제한

- `.env`/`.env.example` `CHAT_MODEL=qwen/qwen3.8-27b:free`; backend 재빌드·재기동 완료. health 카탈로그 조회 ok, Ollama 임베딩 ok.
- 실제 비식별 생성은 OpenRouter HTTP 429 `Provider returned error`. 오류 메타데이터는 ModelRun upstream의 `qwen/qwen3.8-27b:free` 일시 rate limit이라고 명시했다. 인증 키 조회 200/무료 계정 확인. 유료 모델이나 다른 무료 모델로 자동 fallback하지 않았다.
- 무료 제한이 풀린 뒤 일반·JSON Schema·SSE 실제 호출을 재검증하고, 그 다음 세무 검색/인용 품질을 평가해야 한다. 지금 사용 가능하다고 표시하지 말 것. 최신 컨테이너 pytest 619 passed/2 skipped.

## 2026-09-25 OpenRouter 무료 생성 배포 완료 — 품질 평가 필요

- 사용자 키 입력 후 최신 backend 재빌드·기동. health에서 생성 `openrouter/free`/임베딩 `ollama` 모두 ok. 비식별 일반·구조화·SSE 생성 스모크 통과. 최신 이미지 전체 테스트 619 passed/2 skipped.
- 요청마다 무료 모델이 달라지고 초기 구조화 응답에서 빈/비JSON 사례가 관찰됐다. `require_parameters`와 형식 오류 1회 재시도 추가 후 스모크는 통과했지만 지속 안정성은 아직 미검증이다. 무료 요청 한도/429와 실제 세무 답변의 근거·인용 품질을 평가해야 한다.
- 실제 키는 `.env`에만 있으며 출력·커밋 금지. 개인정보가 포함된 사용자 질문은 외부 제공자 데이터 정책 검토 전 테스트하지 않는다.

## 2026-09-25 OpenRouter 무료 모델 연결 — 사용자 키 대기

- `.env`/`.env.example`은 OpenRouter 무료 라우터를 생성 provider로 선택했으나 `OPENROUTER_API_KEY`는 비어 있다. 사용자만 실제 `.env`에 키를 입력한다. 기존 Docker 컨테이너는 재배포하지 않았으므로 지금 웹 서비스는 여전히 이전 Ollama 구성이다.
- 키 입력 후 WSL `venv-wsl` 활성화 → `bash dev/docker-up-wsl.sh backend` → `/api/health/dependencies` 확인 → 비식별 질문으로 일반/구조화/SSE 실제 호출 테스트. 무료 한도/429, JSON Schema 호환, 스트리밍 완료, 인용 품질을 기록할 것. 테스트용 질문에 실제 개인정보를 포함하지 않는다.
- `openrouter/free`는 모델이 고정되지 않아 재현 가능한 법률 품질 평가에는 부적절할 수 있다. 결과 비교 시 응답 모델 ID를 별도 기록하거나 고정 `:free` 모델을 선택하고 다시 평가한다.

## 2026-09-25 `num_ctx=8192` 임시 실험 후 4,096 복구

- 동일 비식별 복합 질문 실제 파이프라인에서 8,192 입력 3,815/출력 1,220토큰, `done_reason=stop`, 23.8초로 생성 완료. 4,096에서는 입력 3,815/출력 281에서 `length` 중단했다.
- 8,192 완료 직후 두 모델 모두 100% GPU였으나 VRAM 여유는 120MiB뿐. 답변이 요청 제59조의4와 하위법령 대신 다른 소득세법 조문으로 이탈했다. 생성 완료를 법적 정확성으로 해석하지 말 것. 반복·동시 요청/OOM 평가 없이 기본값을 8,192로 전환하지 않는다.
- 실험용 프로세스만 설정을 바꿨고 `.env`/Compose/DB는 보존. 종료 후 Ollama에 4,096 요청을 보내 `ollama ps`에서 4,096 복구를 확인했다. 다음 우선순위는 다법령 근거 검색과 필수 조문 우선 프롬프트 예산, 그다음 단계적 컨텍스트 성능 실험이다.

## 2026-09-25 실제 복합 질문 중단 재현

- 실제 Ollama+DB+검색 채팅 스트리밍(저장·웹·LangSmith 차단)에서 소득세법 제59조의4 제1항 제1호 및 관련 하위법령 비교 질문이 입력 3,815 + 출력 281 = 컨텍스트 4,096토큰에 도달해 `done_reason=length`로 중단됐다. 수정된 어댑터가 실패로 표시하고 미완성 답변을 저장하지 않았다.
- 검색 근거는 5건·4,326자이고 모두 소득세법이었다. 요청한 시행령·시행규칙은 입력에 없었다. 종료 원인과 근거 부족을 별도 결함으로 다룰 것. 시스템 프롬프트 2,300자도 예산에 포함된다.
- 다음 구현은 검색 결과 전체 5건을 그대로 프롬프트에 넣는 경로의 토큰 예산과 위계/필수 근거 우선 선택. 법적 조건을 문장 중간에서 자르는 단순 문자열 절삭은 피하고, 불가 시 명시적 유보. 실제 사용자 질문을 받으면 별도로 재현해 비교할 것.

## 2026-09-25 복합 질문 답변 중단 — 종료 사유 검출 추가

- Ollama 생성 어댑터가 `done_reason`과 토큰 수를 기록하고 `length` 등 미완료를 예외로 전환한다. 채팅 라우터는 스트리밍 오류 이벤트(정상 `[DONE]` 없음), 비스트리밍 502를 반환한다. 미완료 일부 출력은 저장하지 않는다.
- 강제 짧은 출력의 실제 Ollama 요청에서 `done_reason=length`를 확인했다. 사용자가 겪은 원인과 동일하다는 증거는 아직 없다. 사용자 재현 질문으로 `Ollama completion` 로그의 `reason`, `prompt_tokens`, `output_tokens`를 확인해야 한다. 민감한 질문·답변 원문은 진단 로그에 넣지 말 것.
- 다음 작업: 4,096토큰 내에서 필수 법령/질문 우선 입력 예산과 답변 여유를 계측·평가한다. 단순히 컨텍스트를 올리면 12GB GPU 공존 설정이 깨질 수 있다. GPT/Claude 교체 여부는 이 오류와 분리해 평가한다.
- Ollama backend 이미지 재빌드·healthy 확인, 최신 이미지 전체 pytest 612 passed/2 skipped(추적 비활성), 프런트엔드 12 passed. 첫 Docker 전체 pytest에서 기존 LangSmith 추적 설정이 원격 429를 출력했으므로 추후 테스트는 `LANGCHAIN_TRACING_V2=false` 등으로 외부 추적을 끄고 수행해야 한다. 평가 업로드를 테스트 성공으로 간주하지 말 것.

## 2026-09-25 결함 6건 수정 완료 — 품질 평가는 후속

- `history_context.py`: 의도/시점 라우팅과 서버 메타데이터 상속. `history_structure.py`: 보존 XML의 정확한 항·호·목 추출. `history_search.py`: 버전 소속 대조/질문 범위 Graph 인용. `history_answer.py`: 필수 근거 예산/생성·검증 상태.
- backend/frontend 최신 배포. 전체 595 passed/2 skipped, frontend 8 passed/build, healthy/HTTP 200 확인. `tests/test_history_runtime_regressions.py` 34개 사례. 원본 데이터·127,838개 임베딩·Graph 재작성 없음.
- 실제 모델은 구법 제2조 인용을 바꿔 실패하기도 했고 이제 error로 정확히 표시된다. 실패를 숨기거나 검증을 약화하지 말 것. 구법 후속 질문은 올바른 529 버전/1949-07-15를 유지했다. 추가 모델 인용 재현율 및 전문가 법률 검수가 필요하다.
- 계산기 스키마에는 tax_year가 없다. 연도 질문이 역사 경로에 잘못 진입하는 문제만 해결됐으며, 연도별 세율/공제 자동 적용을 주장하면 안 된다. 별도 적용연도 규격/검증 작업 필요.
- 모델별 전체 토큰 예산·긴 항 처리·다중 의도/법령 비교·구조 메타데이터 없는 옛 대화의 자동 복원은 후속. 지금은 모호하면 재확인을 요청한다.
- 상세 검증/한계: `docs/evaluation/2026-09-25-history-runtime-fixes.md`. 아래 미수정 기록은 이전 관측 이력이다.

## 2026-09-25 런타임 리뷰 — 수정 전 결함 기록

- 읽기 전용 재현으로 연도만 있는 계산/문서 질문의 역사 경로 오분기, 과거 법령 후속 질문의 일반 검색 진입, 명시 버전/법령명 충돌 무시를 확인했다.
- 과거 본문 `①\n①` 중복: 고유 본문 53,466개, 발생 행 583,010개. 버전 309 제59조의4 제1항 조회가 `①`만 선택하고 존재하는 제1호를 없다고 처리한다.
- 같은 조의 항 질문에서 10,000-byte 예산으로 질문 대상 조문이 빠지고 조세특례제한법 그래프 근거 2개만 남는 동작도 확인했다. 생성 실패 주입 시 최종 도구 상태가 ok인 문제 포함.
- 제품 코드/DB는 수정하지 않았다. 상세 재현/개선 순서: `docs/evaluation/2026-09-25-history-runtime-review.md`. 관련 기존 테스트 31개는 통과했으므로 이 사례들을 회귀 테스트에 추가해야 한다.

## 2026-09-25 임베딩 완료 후 검증

- DB 저장 127,838/127,838, 실패 0. 전수 Neo4j 감사 5,400/5,400 및 관련 회귀 테스트 31 passed.
- 실제 의미 검색 소규모 진단 3/3, 유보 2/2, GraphRAG 채팅 스모크 통과. 진단 코드 `evaluation/history_retrieval_pilot.py`, 결과 해석은 `docs/evaluation/2026-09-25-history-embedding-validation.md`.
- 독립 검수한 다법령·다시점 정답셋, hard negative, 인간 법적 적용 검수는 아직 필요하다. 위 3건을 전체 검색 품질이나 세무 정답률로 해석하지 않는다.

## 2026-09-25 과거 법령 임베딩 완료 — 후속 평가 필요

- 최종 DB 상태: 청크 127,838/127,838 임베딩, 실패 0, 미준비 0, History* 그래프 5,400/5,400. indexer 최종 종료 코드 0.
- 이전에 기록된 `ReadTimeout` 실패 8개는 `embed --retry-failed --limit 8`로 재처리해 해결했다. 아래의 4개 실패/진행 중 수치는 과거 관측 이력이다.
- 다음 작업: 여러 연도·동일 시행일 모호성·부칙/hard negative 검색 평가, 법적 적용 시점 및 답변 검수. 전체 벡터 완료를 정답률 검증으로 해석하지 않는다.

## 2026-09-24 임베딩 일시 정지 진단 및 재개 확인

- 배치의 마지막 오류는 `ReadTimeout` 4개였다. 작업 프로세스는 한 차례 종료됐으나 컨테이너가 재기동했고, DB 임베딩이 20,532 → 20,632/127,838로 증가하는 것을 확인했다. 현재 실패 4개.
- 진행 중인 worker를 중복 실행하지 않는다. 나머지 완료 후 worker 종료/락 해제를 확인하고 `python scripts/index_law_history.py embed --retry-failed --limit 4` 등으로 실패 4개를 재처리한 뒤 `failed=0`, `embedded=chunks` 검수 필요. 재시도 전에 Ollama 지연 원인을 점검한다.

## 2026-09-24 사용자 요청으로 임베딩 재개

- `bash dev/history-index-wsl.sh start` 실행 후 컨테이너 running 확인. 저장량 10,292 → 10,320/127,838로 증가, 실패 0.
- 전체 백필 진행 중. 최신 수치는 `bash dev/history-index-wsl.sh status`로 확인하고, 완료는 chunks=embedded/failed=0/unprepared=0 및 배치 종료로 판정한다.

## 2026-09-24 사용자 요청으로 임베딩 중지

- PC 종료를 위해 `bash dev/history-index-wsl.sh stop` 실행. 컨테이너 `exited`, `running=false` 확인.
- 중지 후 DB: 10,292/127,838 청크 임베딩 저장, 실패 0. 원본 및 Graph 5,400개 보존. 전체 임베딩 미완료.
- 사용자가 재개를 요청하면 Docker/DB 실행 상태 확인 후 `bash dev/history-index-wsl.sh start`로 남은 작업 재개. 임의 자동 재개하지 않는다.

## 2026-09-24 과거 법령 GraphRAG — 백필 완료 추적 필요

- 서비스/Graph 적재/전수 소속 검수는 완료. 전체 벡터는 6,224/127,838에서 진행 중, 실패 0. tax_law_history_indexer를 최신 코드로 재개했고 docker wait로 WSL 연결을 유지했다. PC/WSL 종료 후 dev/history-index-wsl.sh start 필요.
- `bash dev/history-index-wsl.sh status`의 chunks=embedded, failed=0, unprepared=0 및 종료 코드를 확인해야 백필 완료다. 성공으로 미리 표시하지 말 것. 모델 tag 내부 가중치를 바꾸면 색인 규격 버전도 올리고 재색인한다.
- 5,400 Neo4j snapshot audit 통과/MENTIONS 86,552. docs/HISTORY_RAG.md에 구현/실험/한계 기록. 생성 및 벡터 검색은 소수 스모크이며 전체 정답률 평가 아님.
- backend/frontend 재배포로 과거 조회 및 이전 조회 실패 유보 코드도 실행 이미지에 반영됨. 전체 561 passed/2 skipped, frontend 8 passed. 역사 답변은 현행 뷰어 대신 공식 MST+efYd 링크를 사용한다.
- 다음: 전체 임베딩 완료/오류 점검 → 여러 연도·동일 시행일 모호성·부칙/hard negative 평가 → 법적 적용 검수. 현행 Graph 설정은 유지하고 HISTORY_GRAPH_RAG_ENABLED만 true로 활성화했다.

## 2026-09-24 독립 수집기 및 전수 검수 완료

- **최종 상태**: 5,400/5,400, pending/failed=0. 전수 검수 passed=true, 공식 표본 3개 일치, 컨테이너 정상 종료 0. 추가 수집 2,502개. docs/evaluation/2026-09-24-law-history-recovery.md 및 JSON 참고. 아래 3,284는 진행 중 관측 이력이다.
- 다음 작업: 동일 시행일 복수 버전 474묶음 및 부칙/사건 기준일 적용 검수, 구법 검색·Graph 연계 설계. 수집 완료를 법적 적용 정확도 인증으로 해석하지 말 것. 현행 검색/Neo4j에는 아직 구법 미반영.

- 사용자 승인으로 미수집 2,502개 재개. tax_law_history_worker가 수집 후 자동 전수 검수까지 실행한다. 최신 관측 3,284/5,400, 실패 0. API/현행 검색/Neo4j 변경 없음.
- bash dev/law-history-wsl.sh status 및 logs, evaluation/runs/law-history/audit-*.json 확인. 보고서 passed=true + 전체 coverage + 컨테이너 exit 0을 함께 확인해야 완료.
- 543 passed/2 skipped. 독립 worker 재생성 후 정상 이어받기 실증. PC/WSL 종료 후에는 start 명시 재실행 필요; 실패 데이터는 자동 무한 재시도하지 않는다.

## 2026-09-23 검수 결과 — 수집 재개 필요

- 실제 수집 중단 확인: 2,898/5,400 저장, pending 2,502, 실패 0. run 4는 running으로 남았지만 마지막 heartbeat 9/22 21:10 KST, 수집 프로세스 없음. 이번 요청은 검수이므로 재개하지 않음.
- 저장 원문 전체 무결성 및 법/영/규칙 표본 3건 공식 원문 대조 통과. 동일 시행일 복수 버전 474묶음의 적용 의미는 미검증. docs/evaluation/2026-09-23-law-history-audit.md 참고.
- 다음: 사용자 지시에 따라 collect 재개, 완료 후 재검수. 구법 채팅/Graph 연결은 아직 불가. DB 수정·API 재배포 없음.

## 2026-09-22 판단 유보 구현 — 활성화 대기

- app/services/chat_service.py _failed_tool_answer: 법령/문서 도구 실패 시 고정 안내로 최종 생성 차단. 일반/SSE, 저장 도구 상태 유지. tests/test_lookup_abstention.py 22개 추가, 전체 526 passed/2 skipped.
- 수집 worker를 유지하려고 tax_backend 재시작하지 않음. 변경 파일 복사 후 별도 pytest 프로세스로 검증했으나 현재 API 프로세스에는 미활성화. 수집 완료 후 dev/docker-up-wsl.sh backend로 재배포하고 실제 질문 확인 필요.
- 일반 검색 빈 결과, 구법 버전 적용 확인, Judge 교정은 이번 변경 범위 아님. 수집 마지막 확인 1,574/5,400, 실패 0; 실제 최신 상태를 재조회할 것.

## 2026-09-22 과거 법령 수집 진행 중

- law_history 스키마와 20260922_0003 적용, 41개 대상/5,400개 목록 확보. 본문 전체 수집은 진행 중이며 status를 실제 조회할 것.
- Windows 숨김 wsl 프로세스로 `docker exec tax_backend python scripts/collect_law_history.py collect` 실행. stdout history-collection.20260922.log, stderr history-collection.20260922.error.log (Git/Docker 제외). WSL 유지용 전경 docker exec이며 PC/WSL/컨테이너 재시작 때 자동 복구하지 않는다.
- 중복 작업은 DB advisory lock 차단. 중단 후 같은 collect로 미수집 재개, 실패는 collect --retry-failed. 기존 실행 running 표시만으로 살아 있다고 간주하지 말고 heartbeat/프로세스도 확인.
- 전체 504 passed/2 skipped, DB 멱등·정정 스냅샷·시점 불일치 rollback 검증, 1949-07-15 소득세법 원문 저장 성공. 채팅/임베딩/Neo4j에는 미반영.
- 후속: 수집 완료/실패 사유·원문 품질 감사 → 부칙/조문 시점 검수 → 구법 임베딩/과거 Graph 투영. 법령 ID가 바뀐 전신/후신 연결, 별표 첨부 다운로드는 미구현.

## 2026-09-22 검수 자료 열기

- evaluation/sources/precedents/2026-09-20-pilot/검수자료.html을 브라우저로 열면 수집 10건과 미승인 기준 5건을 함께 볼 수 있다. 읽기 전용이며 메모 저장/승인 UI는 없다.
- 재생성은 python -m evaluation.precedent_review --batch BATCH. 기존 HTML은 덮어쓰지 않는다. 원본에 비해 HTML 태그만 제거한 텍스트 표시이므로 원문 서식은 공식 출처에서 확인한다.

## 2026-09-20 판례 후보

- evaluation/sources/precedents/2026-09-20-pilot/README.md와 draft-cards.json부터 검수. 10건 원문/5건 초안, 운영 DB 적재 없음. sources 전체 Git/Docker 제외.
- 초안 선정 ID: 623075/619463/622927/621977/622257. 판시사항·요지 중심이므로 실제 사실관계 정리, 구법 적용 범위, 상급심/후속심 연결, hard negative 구체화 후 승인 필요.
- 최신순 제한 표본으로 대표성 없음. 민사 후보 2건은 제외 삭제하지 않고 보존. API 인증값은 .env에서 읽고 출력/저장 금지.

## 마지막 턴 재생성/수정

- chat_revision_service.py + conversations/{id}/revise, ChatArea/MessageBubble 연결 및 Docker 반영 완료. 원본 대화 유지/별도 대화 생성 방식이다.
- 490 backend/8 frontend tests, Edge 합성 브라우저, 실제 PG rollback 검증 완료. frontend/tests/revisions.browser.cjs는 PLAYWRIGHT_MODULE 지정 후 실행 가능.
- 서버 idempotency/다중 탭 중복 생성 차단, 중간 턴 수정, 버전 탐색 UI는 미구현. 새 분기 생성 뒤 답변 실패하면 빈 분기/복사 문맥이 남을 수 있고 원본은 보존된다.

## Judge 증거 오류 수정 완료

- 최신 judge schema 1.1/evidence_policy_version 1. A/R ID 기반, 일반 paired/특정 합성 행동 기준 behavioral. 형식 오류만 한 번 재평가.
- judge-evidence-ids-01은 같은 저장 답변 3항목 모두 pass, 이전 2개 발췌 오류 해소. 인간/독립 모델 교정 완료가 아님. 관련 테스트 43 passed.
- 신규 행동 항목 정책은 현재 호환 함수 evidence_policy를 명시적으로 확장해야 한다. 법적 기준의 원문 필수 조건을 일괄 해제하지 말 것. 전체 5개 법령 카드는 여전히 미승인이다.

## LLM Judge 초기 구현

- scripts/evaluate.py judge --run-dir RUN --output NEW_DIR로 저장된 고정 컨텍스트 답변 평가 가능. local judge.json/md만 생성, 인간 판정/원래 gate는 그대로다.
- 실제 첫 대상은 answer-ready-verified의 정보 부족 응답 1개다. 전체 GraphRAG/법령 정확도 평가로 소개하지 않는다. 5개 pilot은 draft라 unknown을 유지한다.
- LangSmith feedback 연계, 독립 Judge 모델/가중치 digest, 공식 카드 승인 및 전체 채팅 A/B는 후속. 동일 로컬 모델 자원 경합·자기평가 편향 주의.

## 다음 작업: 평가 기준 카드 검수

- evaluation/QUALITY_CRITERIA.md와 datasets/answer_pilot.json의 5개 초안을 검수한다. 공식 원문 버전·발췌·귀속기간·부칙과 hard negative의 정확한 조항을 확보한 후 승인할 것.
- input.review_card.calibration_examples는 모델 교정용 초안이지 기존 counterexamples 자동 통과 자료가 아니다. Judge 결과 스키마/실행기는 아직 미구현, 인간 Adjudication과 분리해야 한다.
- 5개 전수 검수 후 20개로 확대하고 실제 답변 관측·Judge 교정·LangSmith 항목별 업로드 연결 순으로 진행한다.

## 2026-09-19 GraphRAG 로컬 채팅 활성화

- LLM Judge는 사용자 우선순위 변경으로 미구현/보류. 로컬 GRAPH_RAG_ENABLED=true, Ollama 유지. 일반 채팅 검색에 기존 그래프 확장을 활성화했다. 관계도 UI는 없다.
- 실제 Nginx/SSE 질문에서 base=5 added=2 및 답변/대화 저장 확인. 법적 정답률 검증이 아니며 답변의 조건 누락·잘못된 설명은 별도 검수 대상이다. 모델 답변을 세무 정답으로 문서화하지 말 것.
- WSL이 마지막 foreground 프로세스 종료 뒤 자동 종료될 수 있다. 재기동 직후 Neo4j가 준비되지 않으면 안전하게 기본 RAG로 돌아간다. 서비스를 확인할 때 WSL 터미널을 유지하고 Neo4j 준비 상태도 확인한다.
- 테스트 계정 graph-smoke-* 3개와 각 대화는 보존. 첫 질문은 stdin 인코딩 손상으로 무효, 두 번째는 기동 중 fallback, 세 번째만 그래프 추가 근거 확인 사례다. 기존 사용자 데이터/법령/벡터는 수정하지 않았다.
- 롤백: 로컬 .env GRAPH_RAG_ENABLED=false 후 bash dev/docker-up-wsl.sh backend. .env.example에는 실제 키가 있으므로 내용/diff 출력 금지.

## 2026-09-19 키 입력 파일 최종 변경

- 사용자 명시 요청으로 .env.example의 LANGSMITH_API_KEY를 publish에서 읽는다. .env.langsmith와 evaluation/langsmith.env.example은 삭제했다. 아래 이전 키 위치 안내보다 이 항목을 우선한다.
- .env.example에는 실제 키가 있으므로 내용/diff를 출력하지 말 것. Docker 빌드에서 제외했지만 Git 추적 파일이므로 실제 키를 커밋하면 안 된다. 자동 추적·평가 업로드는 별도 명시 동의 경계를 유지한다.

## 2026-09-19 LangSmith 전환 인계

- 현재 명령은 scripts/evaluate.py langsmith prepare/publish. 자체 dashboard 소스·실행기 제거, 포트 8765 종료. 아래 UI 실행 지침은 당시 이력이다. runs/reviews는 삭제하지 않았다. 제거한 UI는 미추적 파일이었으므로 Git에서 복구할 수 없으며 캐시 디렉터리는 정책상 삭제 거부로 남을 수 있다.
- .env.langsmith의 LANGSMITH_API_KEY는 빈 상태. 사용자가 직접 입력하고 계정 region을 확인해야 한다. 키를 출력하거나 서비스 .env/Compose에 넣지 말 것. production tracing은 활성화하지 않는다.
- 평가 결과 전송 계획 2개: evaluation/runs/langsmith-metrics-plan.json(본문 제외), langsmith-review-plan.json(본문 포함·검수 큐 요청). 실제 39문항 base/graph 78결과이며 uploaded=false. 사용자에게 내용을 확인받고 계획 hash를 publish --approved-sha256에 지정해야 한다. 아직 원격 전송 권한 확인/계정 성공 검증 없음.
- 최신 Docker 476 passed/2 skipped, 로컬 평가 45 passed. 새 테스트 9개는 SDK autospec 기반 mock이며 클라우드 성공으로 소개하지 않는다. 첫 공개/합성 데이터 전송과 실제 LangSmith UI 확인이 남았다.
- LangSmith는 저장된 artifact import이며 새 추론/실서비스 trace가 아니다. 기본 latency 대신 observed_elapsed_seconds를 볼 것. draft는 diagnostic 지표이고 로컬 gate는 그대로 유지한다.
- 원격 장애 시 receipt와 부분 생성 리소스를 확인한다. 자동 롤백/삭제하지 않는다. 원격 검수의 로컬 자동 동기화는 후속이며 현재 수동 규약 변환·재채점 필요. 상세 evaluation/LANGSMITH.md.

## 2026-09-19 로컬 평가 UI 인계 (과거 이력)

- WSL venv에서 python scripts/evaluation_dashboard.py → http://127.0.0.1:8765. 사용자 서비스와 별도이며 기본 배포 이미지/Compose에서 제외. 코드·데이터 삭제 없음.
- 검수 저장은 evaluation/reviews에 추가 전용 JSON. 원본 결과/정답셋/점수는 변경하지 않는다. 답변 JSON은 score --adjudications로 사용하고 근거 제안은 공식 검수 후 새 정답셋 버전으로 수동 반영할 것.
- 테스트: 로컬 평가/UI 44 passed, 서비스 Docker 467 passed/2 skipped, 실제 파일 기반 Edge 조회·필터·모바일 검사 통과. browser-check.cjs는 라벨을 저장하지 않는다.
- 남은 범위: 독립 전문가 라벨 승인, 실제 채팅 trace 수집, 대용량 목록 페이지네이션. 다중 사용자 인증/원격 접속/평가 실행 버튼은 의도적으로 구현하지 않았다. 단일 신뢰 PC에서만 사용하고 외부 프록시로 공개하지 말 것.

## 2026-09-19 실행 파일 정리 후 검증

- scripts/evaluate.py → evaluation/cli.py로 명령 처리를 분리하고 구 평가 stub 2개 삭제. 최신 Compose 이미지 일회성 컨테이너 전체 467 passed/2 skipped, 합성 22개 통과. 실행 중인 서비스는 재생성하지 않았으므로 변경된 CLI 사용 시 새 이미지로 실행할 것.
- 별도 무네트워크 컨테이너에서는 PDF 토크나이저 최초 다운로드가 실패했다. DB 설정 없는 독립 컨테이너에서는 계산기 API 2개 및 합성 평가 gate가 실패했다. Compose 환경에서는 통과했다. offline 합성 평가의 DB 스냅샷 의존성을 분리하는 후속 점검이 필요하며, 완전 무의존 CI 실행을 이번 결과로 보장하지 않는다.

## 2026-09-19 평가 시스템 인계

- 최종 Docker pytest 460 passed/2 skipped(기존 경고 26개), 합성 계약 22개 통과. scorer 1.1은 gold 미정의 사례를 오답이 아니라 incomplete로 처리한다. 다른 scorer 버전의 report는 compare가 거부한다.

- 새 진입점 scripts/evaluate.py, 구현은 evaluation/cli.py. evaluation/README.md를 먼저 읽을 것. 과거 eval_rag/eval_graph_rag 점수는 새 scorer와 직접 비교하지 않는다. 두 구 실행 파일은 제거했으며 원래 질문/결과는 보존했다.
- 실제 세무 라벨 승인자는 아직 없다. retrieval.json 39개는 모두 draft/dev, 제안 hard negative 6개도 재검수 대상. 기존 grounded=true를 승인 이력으로 승격하지 말 것.
- 우선 작업: evaluation/runs/retrieval-rescored/evidence_review_queue.json의 231개 후보를 공식 원문과 대조하여 필수·보조·무관·hard negative로 검수하고, 기준일/버전/검수자를 채울 것. 라벨 변경 시 버전·dataset hash가 바뀌므로 새 실행 필요.
- evaluation/runs/answer-ready-verified에 실제 모델 생성과 빈 인간 검수 양식이 있다. 인간 검수 없이 자동 pass로 바꾸지 말 것. outputs는 Git ignore되며 공유 전 비식별 확인 필요.
- 전체 채팅/컨텍스트/권한/성능 trace 자동 수집은 미구현. components.json의 recorded 계약에 관측을 넣어 score할 수 있지만 실제 계측 없이 기대 값을 관측으로 복사하면 안 된다.
- 라이브 검색은 ALL 또는 명시 입력 필터의 단일 쿼리 비교, 고정 컨텍스트 생성은 검색·웹·대화 저장과 분리된 평가다. E2E 품질 검증으로 소개하지 않는다.
- 합성 계약 CI만 연결했다. 실제 법령·기준일·예외·복합 근거 test셋과 검수자 간 일치도, 동일 토큰 예산 비교는 후속이다. GraphRAG 기본 false는 그대로 유지했다.
- source snapshot 초기 구현은 무관한 Neo4j 준비 상태가 계산 gate에 영향을 줬다. 현재는 검색/원문/계산 단계별 의존성만 해시하고 고정 컨텍스트/도구 선택은 DB를 요구하지 않도록 수정했다.

## 2026-09-19 GraphRAG 후속 작업

- 구현·동기화·검증 완료, 아직 채팅 확장 플래그 false. 아래 9/13의 설정 누락과 10개 실패는 복구됨. 최신 Docker 431 passed/2 skipped, 격리 통합 2 passed.
- 다음 우선순위: 법률/시행령/시행규칙 복합 질문별 필수 근거 집합을 별도 검수하고, 추가 근거 정밀도·동일 토큰 예산 재현율·실제 생성 인용 평가. 기존 38개 라벨은 기본 검색도 모두 성공하므로 추가 가치 측정에 부족하다.
- 남은 사례: inc-02 종합소득 기본공제 질문에 같은 계열의 양도소득 관련 시행령이 추가된다. 단순 키워드 필터의 한계이며 활성화 전에 해결해야 한다. 기본 RAG 자체의 긴 본문도 전체 컨텍스트 예산을 초과할 수 있다.
- 6,275개 미해결 참조는 자동 수집/수정하지 않았다. 특히 호 확인 실패 2,953, 항 확인 실패 124는 저장 원문과 공식 XML을 대조해 누락/버전/파서 문제를 분리해야 한다. 대규모 재수집은 범위 승인 후 진행.
- Graph 관계 UI와 독립 dependency 상태 API는 미구현. 원문 도구가 RAG를 생략하는 경로는 그래프 확장을 실행하지 않는다.
- scripts/eval_graph_rag.py는 stdout JSON Lines, DB 쓰기 없음. 전체 결과는 docs/evaluations/graph_rag_2026-09-19.json. docs/GRAPH_RAG_VALIDATION_2026-09-19.md에 실행·한계를 기록했다.
- 기존 추론 provider는 Ollama로 보존. 현재 Compose에는 OLLAMA_WINDOWS_IP 필수 extra_hosts가 남아 있으므로 WSL 스크립트 사용 또는 명시 export 필요. 과거의 셸 선택형 bootstrap은 이번 Graph 작업에서 재연결하지 않았다.
- WSL이 foreground 프로세스 없이 종료되는 환경에서 명령 사이 자동 재시작이 관찰됐다. Neo4j 준비 전 조회가 일시 실패했다가 준비 후 성공했다. 운영 시 WSL 유지/부팅 정책과 dependency 관측을 분리해 검토할 것.

## 2026-09-13 Neo4j 통합 테스트 인계

- 기존 dev 검증 스크립트를 tests/integration으로 이전/제거. WSL venv에서 python -m pytest -q tests/integration --run-neo4j --graph-real-sample: 2 passed. 옵션 없으면 2 skipped. 임시 컨테이너 잔존 0.
- 주의: 작업 시작 시 기존 tracked Graph 설정/Compose/수집 필터 변경이 사라지고 Graph 파일들만 untracked로 남아 있었다. 사용자 상태를 보존했으며 서비스 재빌드는 하지 않았다.
- 전체 로컬 테스트 10개 실패(414 passed): tests/test_graph_rag.py 7, test_graph_temporal.py 2, test_law_coverage.py 1. 대표 원인은 GRAPH_RAG_ENABLED/NEO4J_DATABASE 없음과 재정경제부 필터 미반영. 서비스 설정/현재 브랜치 의도를 확인한 뒤 별도 복구해야 한다.

## 2026-09-08 실제 실행 이미지 교체

- 발표 파일의 assets/chat.png·source.png는 이제 실제 Docker/Ollama 실행 결과다. 합성 캡처를 다시 실행해도 발표 이미지를 덮어쓰지 않도록 capture-ui.cjs는 OS 임시 폴더로 출력한다.
- 실제 재캡처는 capture-live-ui.cjs. localhost 서비스에 자기 임시 계정만 생성·삭제하며 live-capture.json에는 비밀 없이 질문·답변·확인 결과를 저장한다.
- 캡처 중 발견한 후속 품질 검증: 제50조 기본공제 대상 답변의 설명 범위, 3문장 지시 미준수, 저장 원문의 하위 호 누락 가능성. 이번에는 답변/DB/프롬프트를 고치거나 화면에서 숨기지 않았다. 과거 파서 데이터와 최신 공식 원문 비교는 별도 승인 범위에서 진행할 것.
- 시연 계정 2개(최초 캡처 검증 오류 후 재실행) 모두 종료 시 회원 삭제 API HTTP 200으로 정리했다. 기존 사용자 자료는 접근하지 않았다.


## 2026-09-07 슬라이드 설명 방식 개편

- 면접 슬라이드 3~5장을 전체 기능 아키텍처 / 쉬운 문제 해결 / 검증 방식·한계·개선으로 변경했다. 테스트 개수는 본문에서 제거했고 과거 골든셋 지표 정의는 구현 근거에 남겼다.
- 편집 원본 interview.html과 배포용 tax-ai-interview.html 모두 반영. 기존 최신 UI 이미지는 유지한다. 수정은 발표 자료에 한정되며 실제 재평가·전문가 검수는 후속 작업이다.


## 2026-09-07 프런트엔드 리팩토링 인수인계

- ChatArea/useChat, 공통 UI, DocumentsScreen/useDocumentLibrary, Calculator/forms로 역할을 분리했다. 현재 작업은 UI/문서 상태 조회에 한정하며 세율·계산 수식은 변경하지 않았다.
- 재검증: frontend에서 npm test와 npm run build. preview 실행 후 tools.browser.cjs 및 workspace.browser.cjs를 실행한다. PLAYWRIGHT_MODULE로 설치 위치를 지정할 수 있다. API는 합성 응답이며 실제 사용자 자료를 생성·삭제하지 않는다.
- 문서 search_ready는 활성 벡터 컬럼의 non-null 개수 기준이다. 임베딩 모델 의미적 호환성, 인덱스 품질 또는 검색 성공을 인증하지 않는다. 업로드는 기존 동기 요청이며 백그라운드 작업 상태/진행률 복구 기능은 미구현이다.
- 계산 결과의 기준일/실제 사용한 자료 시행일은 서버가 아직 제공하지 않는다. 현재 정보 없음으로 표시한다. 요청별 세율 provenance 및 세목별 적용 범위 검증은 후속 과제다.
- 같은 파일 업로드의 서버 DELETE/INSERT 원자성·동시 업로드 충돌은 별도 개선이 필요하다. 이번에는 사용자 확인과 목록 확인 전 업로드 보호를 추가했다.
- HTML 면접 슬라이드의 이전 UI 캡처 교체 완료(2026-09-07 후속 요청): capture-ui.cjs의 문서/health mock을 갱신하고 2880×1800 이미지 2장을 덮어썼다. standalone 재빌드·5장 전체 시각/자동 검증 완료. 이전 이미지 별도 백업 없음. 합성 데이터·health 시연 상태이며 실제 모델 응답으로 소개하지 않는다.


## 2026-09-07 면접 슬라이드 제작

- 발표 파일: `docs/portfolio/tax-ai-interview.html` (단독 전달 가능). 편집 원본·이미지·빌드/캡처/검증 스크립트 및 사용법은 같은 폴더에 있다.
- 실제 React 화면에 합성 API 데이터를 주입해 캡처했다. 개인정보·실제 세무 답변·실제 법령 본문은 포함하지 않았다. 소스 링크는 저장소 상대 경로이므로 파일 단독 공유 시 링크는 끊기지만 근거 설명 텍스트는 남는다.
- 슬라이드 레이아웃·오프라인 동작·인쇄 5페이지 검증 완료. 발표 전 개인별 담당 범위/기간/기여율은 본인 확인 후 추가할 것. 자료에는 확인되지 않은 수치를 넣지 않았다.
- 후속 문서 정합성: README와 과거 컨텍스트의 BM25·검색/계산 병렬·실패 RAG-only 설명은 현재 코드와 다르다. 이번에는 제품 설명 전체를 변경하지 않고 슬라이드에 실제 코드를 반영했다.
- 현재 코드 품질 전체 재평가나 모델 재기동은 수행하지 않았다. 임시 프런트 preview는 종료했고 검증 캡처/PDF는 OS 임시 폴더에 있다.


## 2026-09-07 계산 실패 정책 반영

- 계산 실패를 0원/기본 공제로 반환하지 않는다. errors.py의 안전한 오류 계약을 API와 도구가 공유하며 실패 답변은 최종 LLM을 우회한다. 변경된 기대값(빈 세율표는 오류, 잘못된 도구 인자는 입력 오류)에 맞춰 테스트를 수정했다.
- 백엔드 372개·프런트 6개와 Docker 프런트 build, 합성 API 브라우저 검증 통과. 기존 DB를 변조하지 않고 mock으로 장애를 주입했다. 이번 변경은 법정 세율·수식 정확성 인증이 아니다.
- 다음 검증: 세목별 실제 적용 범위·시행연도·공제 한도·Decimal 반올림 및 부분적으로 손상된 세율표 검증을 통합 평가기에 포함할 것. 데이터 보정 필요 여부는 별도 감사 후 결정한다.
- 양도소득세의 주식/기타 선택지는 화면에 남아 있으나 실행하면 미지원 안내한다. 별도 계산식 구현 전 부동산 공식을 재사용하지 않는다.
- 실행 시 현재 Ollama 구성은 dev/docker-up-wsl.sh를 사용한다. 직접 docker compose 호출 시 자동 탐지 환경변수 OLLAMA_WINDOWS_IP가 없어 실패할 수 있다.


## 2026-09-05 도구 카드·SSE·대화 복원 완료

- ToolCallCard.jsx와 toolState.js가 도구 진행/결과를 표시한다. 문서 본문은 React 텍스트 노드로만 렌더링한다. 법령 성공은 원문 뷰어, 계산 성공은 프리필 화면으로 연결한다.
- 공통 planner의 on_event callback → chat_service 준비 태스크/큐 → SSE 경로다. 연결 종료 시 준비 태스크를 취소한다. 최종 결과만 저장하고 LLM history에는 role/content만 전달한다.
- backend 352 tests, frontend 5 tests/build, 합성 API 브라우저 smoke, 실제 Ollama 스트리밍 이벤트 확인 완료. 브라우저 검증은 로컬 preview에서 진행했으며 실제 계정·문서 데이터는 수정하지 않았다.
- 브라우저 테스트는 tests/tools.browser.cjs(프런트 디렉터리 기준)이며 Playwright·Edge가 필요하다. 의존성은 제품 런타임에 추가하지 않았다.
- 남은 별도 과제: Docker frontend npm install 출력에서 취약점 2건(moderate 1, high 1)이 보고됐다. 이번 기능 작업에서는 의존성 강제 업그레이드를 하지 않았다. 통합 품질 평가기와 실제 소유 PDF 성공 경로 골든셋도 후속 과제다.

## 2026-09-05 공통 도구 계층 도입

- 선택은 tools/planner.py, 입력 허용 목록은 registry.py, 제한 실행은 executor.py에 있다. calculator/engine.py의 이전 extract_calculation_request/run_calculation_for_query는 제거했으며 테스트는 실제 공통 경로로 이동했다.
- 법령 조회는 law/lookup_service.py가 단일 구현이다. 사용자 PDF는 search_user_documents → 기존 _search_documents의 user_id SQL 필터로 조회한다.
- Docker 전체 테스트 346 passed. 실제 Ollama의 법령·문서·계산기 선택과 법령 조회·계산 실행, 문서 없는 사용자 not_found 확인.
- 후속: 통합 평가기 구축, 다중 도구 연쇄 실행 여부 결정, 실제 소유 PDF 성공 경로 골든셋 추가. 문서 페이지 번호는 현재 반환하지 않는다.
- DB/모델/사용자 대화 데이터 삭제·추가 없음. 기존 테스트는 유지·이관했으며 새 도구 보안·실패 경계 테스트를 추가했다.
- 최종 답변 생성·인용 guard까지 실제 호출 성공(대화 조회·저장만 mock). 인용은 단순 문자열 대신 운영 extract_citations로 정규화해서 비교해야 한다. dependency ready 확인, git diff --check 통과.

## 2026-09-05 app 정리 완료

- 미사용 검색 wrapper와 `calculator/updater.py` 제거, 네 계산기의 누진세율 적용은 `calculator/brackets.py`로 통합. README 구조도도 갱신했다.
- `dev/docker-up-wsl.sh backend` 최신 이미지 전체 pytest 329 passed. 기동 준비 후 live·ready·dependencies HTTP 200 확인. 이번에는 실제 LLM 답변 생성 시험은 반복하지 않았다.
- DB·모델 데이터 변경 없음. 세율 자동 갱신은 운영 기능이 아니었으며 재도입하려면 출력 검증·실제 시행일 검증·승인 후 반영 설계가 선행돼야 한다.
- 추가 필수 작업은 없으며 chat/upload 역할 분리는 선택적 후속 작업이다. 기존 답변 품질 평가 우선순위를 유지한다.

## 2026-09-05 미사용 호환 함수 제거

- `chat_service._build_final_messages`, `calculator.engine._parse_extraction_json`은 운영 코드에서 사용되지 않아 제거했다. 이 함수들을 테스트를 위해 재도입하지 않는다.
- 테스트는 실제 ChatPromptTemplate과 계산기 추출 파이프라인을 대상으로 변경했다. Docker 최신 이미지 전체 pytest 317 passed.
- 추가 작업이나 데이터 보정은 필요하지 않으며 다음 우선순위는 기존 답변 품질 평가다.

## 2026-09-05 LangChain 선택 기능 도입 완료

- 사용자의 1·2·3번 요청을 ChatPromptTemplate, Runnable, PydanticOutputParser 적용으로 진행했다. LangSmith는 후속 연결 대상으로 남겼다.
- `ai_pipeline.py`는 공통 호출 함수를 받아 실행하며 provider SDK를 import하지 않는다. `langchain-core`만 재도입하고 `langchain-ollama`는 제거 상태를 유지한다.
- `ai_output.py`에 분류·인용·계산기 추출 모델을 추가했다. 잘린 JSON·잘못된 타입·누락/알 수 없는 필드는 fallback 처리하며 자동 생성 재시도는 없다.
- 최신 Docker 전체 테스트 317 passed. 실제 HTTP provider를 통한 생성·스트리밍·구조화 인용·계산기 추출 및 dependency ready 확인 완료.
- Windows PowerShell에서 한글 포함 Python 코드를 WSL stdin으로 전달할 때 `$OutputEncoding`을 UTF-8로 설정해야 한다. 기본 인코딩으로 한글이 `?`가 된 스모크는 전달 방식을 고쳐 재검증했다.
- 다음 작업: 골든셋·평가 기준 마련 후 LangSmith 추적·평가 연결. 현재는 run_name·prompt_version·callback 경계를 준비했으며 외부 업로드 설정은 추가하지 않았다.

## 2026-09-05 LLM 연결 코드 정리 완료

- `langchain-core`도 제거하여 최신 Docker 이미지는 LangChain 패키지 없이 실행된다.
- `call_llm`·`call_llm_structured`·`stream_llm`의 생성 길이 인자는 `max_tokens`다. 저장소 내부 호출부는 모두 갱신했으며 별도 외부 스크립트에서 `num_predict=`로 호출했다면 변경해야 한다.
- factory의 설정 인자를 명시하고 `base_url`로 통일했다. 테스트용 HTTP 주입 전역 변수와 설정 캐시 키를 제거했다. 프로세스 설정은 재시작으로 변경한다.
- `dev/docker-up-wsl.sh backend` 재빌드 완료. Docker 전체 pytest 296 passed, 실제 Ollama 일반 생성·스트리밍·구조화 응답 모두 성공, dependency ready 확인.
- 다음 작업은 답변 품질 평가이며 이번 정리는 모델·프롬프트를 바꾸지 않았다.

## 2026-09-05 ChatOllama 제거 및 HTTP 어댑터 검증 완료

- `inference/llm/ollama.py`가 Ollama `/api/chat`을 `httpx`로 직접 호출한다. 서비스 공통 인터페이스, 모델·컨텍스트·상주·thinking 설정은 유지했다.
- 초기 교체에서 `langchain-ollama`를 제거했고 후속 정리에서 미사용 `langchain-core`도 제거했다.
- WSL 가상환경 활성화 후 `dev/docker-up-wsl.sh backend`로 최신 backend 이미지를 빌드·기동했다. 전체 pytest 294 passed, 실제 일반 생성·스트리밍·JSON 응답 및 dependency ready 확인 완료.
- 기존 JSON 스모크 세션은 중단되어 결과를 회수하지 못했다. 재개 후 구조화 호출을 다시 실행해 약 6.4초에 정상 응답을 확인했다.
- 다음 작업: 답변 품질 골든셋과 평가기. 이번 변경으로 세무 답변 정확도가 개선됐다고 판단하지 않는다.

## 2026-08-23 Ollama 동시 GPU 적재

- `qwen3.5:9b` 5.5GB와 `qwen3-embedding:4b` 4.4GB를 컨텍스트 4,096에서 모두
  100% GPU로 적재했고 3회 교차 호출을 통과했다. 잔여 VRAM은 약 463MiB다.
- 운영 chat 기본 `OLLAMA_NUM_CTX`는 4,096로 변경했다. 병렬도 증가나 Windows GPU 사용량
  급증 시 OOM 위험이 있으므로 `OLLAMA_NUM_PARALLEL=1`을 유지한다.

## 2026-08-23 serving 실험 환경 최종 감사

- WSL/Windows를 점검해 vLLM·Infinity·TEI·llama.cpp·리랭커 실행 자원과 어제 받은 모델을
  정리했다. WSL에는 관련 컨테이너·이미지·모델 볼륨·Python 패키지가 남아 있지 않다.
- 현재 운영 자원인 Windows Ollama, `qwen3.5:9b`, `qwen3-embedding:4b`와 프로젝트 DB는 보존했다.
- 재도입용 llama.cpp 코드와 Compose 파일만 저장소에 남아 있다.

## 2026-08-23 llama.cpp 실행 자원 삭제

- llama.cpp 도입 코드는 유지하고 WSL Docker의 컨테이너 2개, 이미지 2개와
  `tax_assistant_llama_cache`만 삭제했다.
- 현재 런타임은 Ollama LLM·Ollama v1 임베딩이며, llama.cpp를 다시 사용할 때는
  `dev/docker-up-llamacpp-wsl.sh`가 필요한 이미지와 모델을 재다운로드한다.

## 2026-08-23 vLLM·Infinity 제거

- vLLM·Infinity 전용 파일, 컨테이너, 이미지와 Hugging Face/Infinity 모델 캐시 볼륨을 삭제했다.
- 이후 표준 실행은 `dev/docker-up-llamacpp-wsl.sh`만 사용한다.
- PostgreSQL 데이터와 `tax_assistant_llama_cache`는 보존했다.
- 과거 vLLM·Infinity 절은 실험 이력이며 재실행 지침이 아니다.
- TEI Docker 이미지와 `tax_assistant_reranker_cache`, 리랭커 코드·설정·health/UI 표시도 제거했다.
- 후속 llama.cpp CPU A/B에서 BGE-Reranker-v2-M3 Q4는 MRR 0.9276→0.9088로 하락하고
  평균 1.746초가 추가되어 채택하지 않았다. 현재 검색 정렬을 유지한다.

## 2026-08-23 llama.cpp 소규모 서비스 전환

- 신규 overlay `docker-compose.llamacpp.yml`과 실행 스크립트
  `dev/docker-up-llamacpp-wsl.sh`를 추가했다.
- 생성은 Qwen3.5-9B GGUF Q4_K_M CUDA, embedding_v2는 Qwen3 Embedding 4B GGUF
  Q4_K_M CPU/last pooling 구성이다. 활성 임베딩은 데이터 안전을 위해 아직 v1이다.
- 다음 필수 작업은 llama.cpp 임베딩 비교·백필·골든셋 평가와
  `dragonkue/bge-reranker-v2-m3-ko`의 자체 GGUF Q4_K_M 변환 및 평가다.
- 최신 backend 이미지 전체 테스트는 `287 passed`, llama.cpp Compose config는 정상이다.
  실제 기동에서 llama.cpp CPU/CUDA 이미지는 정상 pull됐으나 컨테이너가 Hugging Face의
  IPv6 주소만 해석하고 연결하지 못해 GGUF 다운로드가 실패했다. WSL 호스트 HTTPS는
  정상이다. 다음 작업은 호스트에 GGUF를 선다운로드하고 read-only volume으로 마운트하는 것이다.
- Mac에서는 Docker가 Metal GPU를 전달하지 않으므로 llama-server를 호스트에서 실행하고
  backend 컨테이너가 `host.docker.internal`로 접속하는 별도 프로파일이 필요하다.

## 2026-08-23 vLLM NVFP4 재검증

- 10.43GiB는 체크포인트 다운로드 크기이며 실제 가중치 VRAM 사용량으로 해석하지 않는다.
- 모델 제작자의 Qwen3.5 하이브리드 구조 주의사항에 따라 Compose의 FP8 KV cache 강제
  설정을 제거했다. 단독 계측에서 compressed-tensors 양자화, 모델 로딩 9.71GiB,
  weights+non-torch 10.11GiB, activation 0.27GiB, KV cache 0.37GiB를 확인했다.
- `gpu-memory-utilization=0.96`은 Windows가 사용하는 VRAM 때문에 시작 전 검사에서 실패했다.
  `0.90`에서는 11,205/12,227MiB를 사용하며 컨테이너 health가 통과했다.

## 2026-08-23 Ollama 임베딩 상주 옵션 제거

- Ollama 임베딩 adapter는 `/api/embed` 요청에 `keep_alive`를 보내지 않는다.
- `OLLAMA_KEEP_ALIVE_SEC=-1`은 Ollama 채팅 LLM에만 적용된다. 이미 메모리에 올라간
  임베딩 모델은 다음 정상 임베딩 요청부터 Ollama 기본 유휴 만료 정책을 적용받는다.

## 2026-08-22 provider 중립화 및 Infinity 검증

- 생성 LLM provider는 `ollama`/`vllm`, 임베딩과 리랭커 provider는 각각
  `ollama`/`infinity`만 허용한다.
- 최신 백엔드 Docker 이미지 전체 테스트 결과는 `284 passed`이다.
- Infinity 공식 CPU 이미지의 Transformers가 Qwen3를 인식하지 못해 커스텀 이미지에
  Transformers 4.56.2와 Sentence-Transformers 5.1.1을 고정했다.
- Qwen 공식 모델은 last-token pooling을 요구한다. smoke test에서 부분 snapshot이
  mean pooling으로 대체되는 현상을 확인했다. 활성 버전은 v1 Ollama로 유지하며
  `embedding_v2` 백필은 실행하지 않았다.
- 공식 Ollama는 범용 `/api/rerank`를 제공하지 않는다. Ollama reranker adapter는
  호환 API 게이트웨이용이며, 기본 Ollama에서는 Infinity를 사용하거나 비활성화한다.
- Infinity 임베딩과 리랭커를 별도 컨테이너로 분리했다. 각 역할은
  `INFINITY_*_DEVICE=cpu|cuda`로 독립 배치하며 `dev/set-inference-device-wsl.sh`로
  해당 컨테이너만 재생성할 수 있다. 12GB GPU에서는 vLLM 실행 중 GPU 전환을 차단한다.
- 이전의 컨테이너 시작 시각 초기화는 Docker Desktop 크래시가 아니었다. Docker는
  Ubuntu WSL 내부 systemd 서비스이며, Codex의 일회성 `wsl.exe -e` 명령이 끝날 때
  배포판도 Stopped 상태가 되어 다음 명령에서 다시 시작된 것이다.
- 실제 vLLM 차단 원인은 Windows Ollama의 `qwen3-embedding:4b Q4_K_M`이
  `keep_alive=-1`로 GPU에 상주하면서 VRAM 약 4.37GB를 점유한 것이다. vLLM의 기존 0.96 설정은
  시작 시 11.46GiB free VRAM을 요구하지만 실제 free는 10.77GiB였다. Ollama 임베딩을
  CPU 전용 서버로 옮기거나 언로드하기 전에는 12GB GPU에서 vLLM과 동시 실행할 수 없다.
- WSL RAM은 24GB(실제 23.47GiB), swap 16GB로 정상 적용됐다. 안정화를 위해 vLLM과
  두 Infinity 모델은 현재 중지했다.

이 파일은 미완료 작업 또는 다음 세션에 반드시 전달해야 하는 내용이 있을 때 갱신한다.
완료된 작업의 장기 상태는 `CURRENT_STATUS.md`, 영구 설계 이유는 `DECISIONS.md`에 반영한다.

## 과거 서빙 실험 당시 인계 — 현행 기준은 맨 위 참조

- 활성 작업: vLLM 생성 서버와 한국어 리랭커 구현 및 실제 기동 완료. 새 작업 전 `git status --short`로 기존 변경을 확인할 것.
- 최근 영역: 생성 LLM vLLM 전환, Ollama 임베딩 유지, Docker GPU 실행 스크립트.
- 최근 검증: provider·health·검색 관련 최신 backend 선택 테스트 `29 passed`. 전체 테스트는 Infinity 전환 완료 후 재실행 필요.
- NVIDIA Container Toolkit 1.20.0 설치, Docker `nvidia` runtime 등록 및 컨테이너 `nvidia-smi` 검증 완료. `dev/docker-up-vllm-wsl.sh`로 전체 스택 기동 및 dependency health를 확인했다.
- 모델 조합: 생성 `ig1/Qwen3.5-9B-NVFP4`, 임베딩 `Qwen3-Embedding-4B`, 리랭커 `dragonkue/bge-reranker-v2-m3-ko`. 임베딩·리랭커는 Infinity CPU 다중 모델 overlay로 통합 중이다.
- 12GB GPU 제약: NVFP4 모델은 텍스트 전용·eager·기본 KV dtype·2,048 토큰·동시 1요청·GPU utilization 0.90으로 검증했다. CPU offload는 Qwen GDN Triton 커널의 CPU pointer 오류로 사용할 수 없다.
- CPU 추론 제약: WSL 할당 RAM은 15GiB이며 Infinity 컨테이너는 12GiB로 제한했다. Qwen3 Embedding 4B 백필과 reranker 동시 실행의 지연·메모리를 실제 측정해야 한다.
- 공식 Infinity `latest-cpu` smoke test는 내장 Transformers가 `qwen3`를 인식하지 못해 실패했다. `docker/infinity.Dockerfile`에서 Qwen3 지원 버전을 고정했으며 커스텀 이미지 재검증이 필요하다.
- 프런트엔드는 `/api/health/dependencies`를 30초마다 조회해 역할별 실제 provider와 모델을 표시한다.
- 데이터 주의: 기존 DB는 과거 수집기로 인해 호·목이 누락됐을 수 있으며 전체 재수집은 아직
  자동 실행하지 않는다.
- 추천 다음 작업: `target.text`를 직접 조문 RAG 컨텍스트에 우선 반영.

## 작업 중 갱신 형식

```markdown
### YYYY-MM-DD — 작업 제목

- 사용자 목표:
- 완료한 변경:
- 변경 파일:
- 실행한 검증과 결과:
- 남은 작업:
- 막힌 이유 또는 필요한 사용자 결정:
- 데이터·마이그레이션·배포 주의사항:
```

## 갱신 원칙

- “테스트 완료” 대신 명령과 결과 수를 쓴다.
- 실행하지 않은 작업을 완료로 표시하지 않는다.
- 코드 경로와 함수명을 구체적으로 적는다.
- 비밀값, 토큰, 실제 `.env` 내용을 기록하지 않는다.
- 작업이 완전히 끝나면 임시 메모를 제거하고 `CURRENT_STATUS.md`에 최종 상태를 반영한다.
# 2026-09-22 판례 실험 후속

- 판례 5건 실험 완료: evaluation/runs/precedent-pilot-20260922/report.md와 experiment.json. 분석은 docs/evaluation/2026-09-22-precedent-pilot.md. 원시 Judge pass 6/fail 3/error 1을 정답률로 쓰지 말 것(명백한 의미 판정 오류 존재).
- 법령 도구 invalid_arguments 2건/not_found 1건에서 일반 검색 없이 정상 생성으로 흘러감. chat_service.py의 법령/문서 tool_run 분기에서 실패 처리 구분 필요. 이번 요청은 평가이므로 서비스 수정은 하지 않음.
- 구법 질문에 현행 검색 자료가 섞임. 시점 버전 확인과 부족 시 유보, 전체 프롬프트 토큰 계측 필요. 컨테이너 GRAPH_RAG_ENABLED=false 관측(과거 문서 true와 다름), 설정 변경하지 않음.
- 현재 생성/Ollama 설정 보존. 평가 전용 assess diagnostic_draft 옵션은 인간 승인 변경 없이 허용하며 일반 CLI gate 유지. 실제 평가 모델도 Qwen3.5:9b여서 자기평가 편향. 별도 검수 및 반례 교정 필요.
- 관련 회귀 테스트 포함 backend 496 passed/2 skipped. 실험 원문/결과 외부 전송 없음. 컨테이너 /tmp/precedent-source와 /tmp/precedent-pilot-20260922에도 복사본이 남으며 호스트 결과는 보존됨.
# 국세청 공식 일정 캘린더 후속 검토 (2026-09-25)

- 국세청 공개 HTML 구조가 바뀌면 `/api/tax-schedule/official`이 503을 반환한다. 표 구조·연월 검증을 유지하며 파서를 수정하고, 장기 운영 시 페이지 변경 감시/알림을 추가한다.
- 현재 전체 공식 일정만 표시한다. 개인별 신고 의무 판정은 사업자 유형만으로 불가능하며 과세기간, 업종, 신고 구분, 성실신고 대상 여부 등 별도 검증된 프로필과 규칙이 필요하다.
- `/api/tax-schedule`은 과거 고정 날짜 레거시 API로 남았다. 외부 사용 여부 확인 후 제거하거나 공식 일정 기반으로 별도 마이그레이션한다. 채팅용 일정 조회 도구는 아직 연결하지 않았다.
# 국제세무 파일럿 후속 (2026-09-25)

- `evaluation/sources/international-tax/pilot-2026-09-25/` 17개 공식 원본은 수집/해시 검사만 통과했다. 17개 모두 `unreviewed`이며 시행·적용일 검증, 본문 영역 정제, 원문 언어 대조가 남았다.
- 한–일 조약 원본 PDF에 OCR을 적용하고 추출 조문을 스캔본과 대조한다. 일본 재무성 MLI 통합 참고문은 법적 원문이 아니다. 미국 USCODE-2024 판본은 현행 2026년 답변에 자동 적용하지 않는다. 중국 영문 자료는 중국어 원문과 대조한다.
- 관할·과세연도·거주지/원천지 질의 스키마 및 3개 양자 조약 관계를 설계한 뒤, 국가별 분리 검색과 유보 테스트를 먼저 추가한다. 그 전에는 현재 한국 중심 RAG/Graph/계산기·서비스 DB로 이 자료를 적재하지 않는다.
