# AI 작업 지침

문서 기준일: 2026-10-06. 실행 방법과 모델 역할은 아래의 현행 기준을 따른다.
이번 갱신은 대화·작업 결과의 인수인계다. 마지막 구현·실모델 검증일은 2026-10-04이며,
문서 기준일을 서비스 재검증일로 해석하지 않는다.

이 저장소에서 작업하는 Codex 및 호환 에이전트는 작업을 시작하기 전에 다음 문서를 순서대로 읽는다.

1. `docs/ai/PROJECT_CONTEXT.md` — 프로젝트 목적, 구조, 도메인 불변 규칙
2. `docs/ai/CURRENT_STATUS.md` — 현재 구현 상태, 진행 중인 변경, 다음 작업
3. `docs/ai/DECISIONS.md` — 주요 설계 결정과 이유
4. 작업과 관련된 `README.md` 절 및 실제 코드

이어 작업할 때는 `docs/ai/HANDOFF.md`의 최신 인계와 남은 작업을 확인한다. 날짜별 과거 기록에
등장하는 모델·테스트 수·미완료 항목은 해당 시점의 기록이며, 최신 요약과 실제 코드를 우선한다.

## 작업 시작 규칙

- 먼저 `git status --short`로 사용자의 기존 변경을 확인하고 보존한다.
- 문서보다 실제 코드와 테스트가 다르면 코드를 기준으로 판단하되, 작업 완료 시 컨텍스트 문서를 함께 갱신한다.
- `.env`, `.claude/settings.local.json` 등 비밀 또는 로컬 설정의 값을 출력하거나 문서에 복사하지 않는다.
- 법령·세율·운영 상태처럼 변경 가능한 사실은 추측하지 않고 공식 데이터 또는 실행 결과로 검증한다.

## 대화에서 확정한 품질 목표

- 잘못된 법적 판단을 생성·공개 전에 막는다. 검증 상태만 표시하는 것으로 목표를 달성했다고 보고하지 않는다.
- 복합 질문은 주체·세목·요청·시점을 보존해 쟁점별로 처리한다. 건설사 가공 컨설팅 등 특정 예시에 맞춘 분기보다 여러 분야에서 재현 가능한 해결을 우선한다.
- 확보한 근거로 답할 수 있는 부분과 추가 확인이 필요한 부분을 나눠 설명한다. 일부 조건·시점이 없다는 이유로 질문 전체를 유보하지 않는다. 근거가 없는 법적 결론은 확정하지 않는다.
- 답변은 핵심 판단 → 질문에 맞는 검토·설명 → 필요한 절차·자료·근거 순으로 자연스럽게 구성한다. 제목·강조·비교표를 필요한 곳에 사용하고, 같은 주체·판단·출처 안내·적용 시점 주의문을 반복하지 않는다. 공개 검사 후 문장을 새 LLM 호출로 다시 쓰거나 개별 적용 조건을 삭제하지 않는다.
- 계산 요청은 전용 계산기의 지원 범위와 공식 근거 기반 참고 산식 경로를 확인한다. 전용 계산기가 없다는 이유만으로 일괄 거절하지 않으며, 필요한 비교과세·공제 등을 빠뜨린 참고값을 확정 납부세액으로 제시하지 않는다.

## 현행 서비스 기준

- 생성·질문 계획·Judge: OpenRouter `openai/gpt-6-luna`. 임베딩: Windows Ollama `qwen3-embedding:4b`, `v1`, 2,560차원.
- `config.py`의 기본 생성 provider는 `ollama`이므로 실제 실행 환경에는 `LLM_PROVIDER=openrouter`, `CHAT_MODEL=openai/gpt-6-luna`를 명시한다. 사용자 요청 없이 모델 역할이나 벡터 버전을 바꾸지 않는다.
- LLM 작업은 `answer`, `history_answer`, `citation_extraction`, `query_classification`, `tool_selection`, `document_classification`, `question_planning`, `answer_judge`의 8개다. 작업별 설정은 공통 provider/model을 상속한다.
- 공식 현행 쟁점 검색은 BM25·벡터·검증된 GraphRAG와 Fuzzy·Regex·MMR을 사용한다. 사용자 문서 소유권과 과거 법령의 별도 경로를 유지한다.
- 전용 Reranker는 미구현이다. `docs/ai/RAG_IMPROVEMENT_PLAN.md`의 모델·서비스·설정은 제안이며 현재 기능으로 기술하지 않는다.
- 운영자 평가·검수는 LangSmith다. 사용자에게는 SSE 진행 상태와 채팅 근거 패널을 제공한다.
- 공식 XML 기반 자동 질문·평가는 `scripts/evaluate.py auto pipeline`과 `evaluation/AUTO_EVALUATION.md`를 따른다. `auto_validated`를 인간 승인 정답으로 승격하지 않는다. `--publish`는 공개 법령·합성 배치만 게시한다.
- 공식 출처 ID·버전·해시·원문 인용과 주장 검사를 보존한다. 표시 역할·검색 순위·Judge 판정을 세무 정확성의 독립 입증으로 취급하지 않는다.

## 지금까지의 구현 인계

| 영역 | 완료한 구현·보존할 경계 |
|---|---|
| 질문·도구·근거 | 쟁점 계획 → 서버 도구/입력 검사 → 출처·버전·해시 검사 → 근거 충족/재검색 → 주장별 코드·인용·Judge 검사 → 공개. 전체 질문의 성공이 입증된 것은 아니다. |
| 검색 | 공식 현행 쟁점 검색에 한국어 BM25·벡터를 RRF로 결합하고 검증된 GraphRAG를 확장한다. Regex로 참조·수치를 보호하고 제한된 Fuzzy 확장·MMR 순위 조정을 적용한다. 사용자 문서와 과거 법령은 별도 경로다. |
| 원문·색인 | 동일 시행본 보관 XML로 계획·백업·임베딩 사전 준비·트랜잭션 교체·감사·rollback 경로를 구현했다. 2,974조문/13,203항 보정 감사 오류 0은 이전 보정 당시 결과다. |
| 계산 | 전용 계산기 6종과 공식 근거 기반 제한 JSON 산식/Decimal 참고 계산을 사용한다. 모델이 작성한 임의 코드를 실행하지 않는다. |
| 답변·웹 | 생성 단계의 표시 역할과 검증된 주장으로 질문별 구조를 만든다. SSE 진행·채팅 근거 패널·저장된 검사 결과를 제공한다. 운영자 검수는 LangSmith다. |
| 자동 평가 | 공식 보관 XML → 규칙·합성 질문·평가 카드 → 코드 검사/별도 원문 감사 → 실제 채팅 관측 → 11항목 평가 → 선택적 LangSmith 게시. 채팅에는 질문만 전달하고 기준·기대 조문은 주입하지 않는다. |

연결 구조는 [RELIABILITY_WORKFLOW.md](docs/ai/RELIABILITY_WORKFLOW.md), 검색·계산·표시의
세부 구현과 과거 결과는 [PROJECT_CONTEXT.md](docs/ai/PROJECT_CONTEXT.md)와
[HANDOFF.md](docs/ai/HANDOFF.md)를 따른다.

### 마지막 구현 검증 — 2026-10-04

- 최신 이미지 백엔드 전체: **1,005 passed, 2 skipped, 5 subtests passed**. 신규 자동 평가 계약 검사 36개를 포함한다. 프런트엔드는 이 작업에서 변경·재검증하지 않았다.
- 자동 카드: 일반 질문 6개 시도 → 3개 채택, 2개 fail, 1개 unknown. 기본 6세목 × 5유형의 30개 전체 실행은 미완료다. 인간 승인 카드는 0개다.
- 동일 저장 답변 3개 최종 재판정: 33항목 중 fail 14/pass 4/unknown 6/N/A 9/error 0, 사례 3개 모두 fail. 이후 BM25 준비 후 새 양도 질문 1개도 사례 fail·평가기 오류 0이었다. 평가기 구현 완료와 답변 품질 개선을 구분한다.
- 최종 카드·관측·보고서·게시 영수증: `evaluation/runs/auto-evaluation-20261004/`의 `pipeline-v2/cards/`, `rejudge-final/`, `live-final/`. 검증 요약은 `verification-final.json`, 원격 조회는 `langsmith-readback-final.json`이다. 초기 중단/이전 Judge 결과를 최종 결과로 사용하지 않는다.
- LangSmith에서 3개 저장 답변의 최종 Experiment는 `tax-eval-system-ed423262b6103a000fb2a0a4`다. 별도의 새 실제 실행 Experiment·원격 ID·URL은 최신 [HANDOFF.md](docs/ai/HANDOFF.md)와 각 게시 영수증에 있다.

`evaluation/runs/`, `evaluation/sources/`, `evaluation/reviews/`는 Git/Docker 제외 자료다.
다른 작업 환경으로 인계하거나 컨테이너를 재생성할 때 필요한 결과·원문·계획·백업·영수증을
호스트에 보존하고 별도 전달한다. 저장소 체크아웃만으로 이 자료가 복원되지는 않는다.

### 이어서 해결할 우선순위

1. **서비스 답변 결함**: 개인 A를 A회사로 계획하는 오류·불필요한 유보, 증여 질문의 날짜만으로 원문 조회/법령명 요구에 진입하는 오류, 양도 질문의 장기보유 특별공제 조건·기준 누락을 재현·수정한다. 필수 원문의 정확한 버전이 생성 입력까지 전달되는지도 확인한다.
2. **다양한 질문 검증**: 고정 카드로 수정 전후를 비교한 뒤 일반·예외·정보 부족·복합·시점의 30개 시도를 확대한다. 유효한 fail/unknown 카드를 pass가 될 때까지 다시 만들거나 판정 기준을 낮추지 않는다.
3. **독립 정확성 입증**: R2의 혼동 근거 라벨, G1의 관계 원문 감사, T1의 독립 숫자 기대값, 전문가 holdout과 Judge 오답 통과/정상 차단 검수를 확보한다. 동일 모델의 별도 호출은 독립 세무 정답 검수가 아니다.
4. **잔여 데이터·검색**: 이전 감사의 원문 의심 27행·연결 보류 인용 4,952개·빈 벡터 metadata 입력 이력을 점검한다. 이미 보정한 전체 데이터를 다시 수집하지 않는다. 전용 Reranker·추가 RAG 범위는 [후속 설계](docs/ai/RAG_IMPROVEMENT_PLAN.md)다.

자동 평가의 명령·재개·게시 범위는 [AUTO_EVALUATION.md](evaluation/AUTO_EVALUATION.md)를 따른다.
서비스 변경 후에는 같은 카드를 새 출력 폴더에서 `auto run`하여 실제 답변을 비교한다.
`auto run --from-run`은 저장 답변의 Judge만 다시 실행하므로 서비스 수정 검증으로 보고하지 않는다.
자동 카드는 `auto_validated`이며 인간 승인 정답셋이 아니다. 자동 평가의 예약 실행은 미구현이다.

## 실행 및 검증

- 현재 서비스의 개발 실행·재빌드는 WSL 가상환경을 활성화한 뒤 `dev/docker-up-wsl.sh`를 사용한다.

```bash
cd '/mnt/c/Users/Laptop PC/Desktop/tax_assistant'
source venv-wsl/bin/activate
bash dev/docker-up-wsl.sh backend frontend
```

- 스크립트는 Windows Ollama 주소·필수 임베딩/로컬 작업 모델을 검사한다. GraphRAG 사용 설정이면 Neo4j를 먼저 준비하고 Compose를 실행한다. 생성 provider는 현재 설정을 따른다.
- `dev/docker-up-llamacpp-wsl.sh`는 명시적으로 llama.cpp를 시험할 때만 사용한다. 기본 서비스 실행에 overlay를 적용하지 않는다.
- 웹은 `http://localhost:3001`, 백엔드는 `http://127.0.0.1:8001`이다. `/api/health/ready`는 DB 준비 상태, `/api/health/dependencies`는 LLM·임베딩·Graph 상태를 구분한다.
- 백엔드 구현 변경의 전체 테스트는 최신 이미지에서 실행한다. 문서만 바꾼 작업은 링크·명령·코드 대조와 diff 검사를 하고 검증 범위를 보고한다.

```bash
docker exec tax_backend pytest -q
```

- 프런트엔드 변경은 `frontend/`에서 `npm test`, `npm run build`로 확인한다. 실제 모델/화면 검증과 독립 세무 정답 검수를 구분한다.
- DB 스키마 변경은 수동 SQL 적용이 아니라 Alembic revision으로 작성한다.
- 데이터 전체 재수집, 삭제, 대규모 백필처럼 기존 상태를 바꾸는 작업은 범위를 확인한 후 실행한다.

## 작업 종료 규칙

- 구현과 관련 테스트를 완료한다.
- `git diff --check`를 실행한다.
- 아키텍처, 실행법, 현재 상태 또는 다음 작업이 달라졌다면 `docs/ai/` 문서를 갱신한다.
- 미완료 작업이나 데이터 보정 필요 사항은 `docs/ai/HANDOFF.md`에 구체적으로 남긴다.
- 완료 결과에는 검증 날짜·범위·결과 파일을 남긴다. 개발용 평가 라벨과 작은 스모크를 전체 세무 정답률로 보고하지 않는다.
