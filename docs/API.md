# API

백엔드 HTTP API 목록입니다. 실행 중인 서버의 `/docs`(FastAPI 자동 문서)에서도 확인할 수 있습니다.

[← README로 돌아가기](../README.md)


## API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/api/auth/signup` | 회원가입 | 불필요 |
| POST | `/api/auth/login` | 로그인 (httpOnly 쿠키 발급) | 불필요 |
| POST | `/api/auth/logout` | 로그아웃 (쿠키 삭제) | 불필요 |
| GET | `/api/health/live` | FastAPI 프로세스 liveness | 불필요 |
| GET | `/api/health/ready` | DB·Alembic readiness (Docker healthcheck) | 불필요 |
| GET | `/api/health/dependencies` | DB와 역할별 LLM·임베딩 provider 상세 상태 | 불필요 |
| GET | `/api/users/me` | 내 프로필 조회 (사업자 유형 포함) | ✅ 필요 |
| PATCH | `/api/users/me` | 프로필 수정 (이름·전화번호·사업자 유형) | ✅ 필요 |
| PATCH | `/api/users/me/password` | 비밀번호 변경 | ✅ 필요 |
| DELETE | `/api/users/me` | 회원 탈퇴 | ✅ 필요 |
| GET | `/api/conversations` | 대화 목록 조회 (최근 50개) | ✅ 필요 |
| POST | `/api/conversations` | 새 대화 생성 | ✅ 필요 |
| GET | `/api/conversations/{id}/messages` | 대화 메시지 전체 조회 | ✅ 필요 |
| PATCH | `/api/conversations/{id}` | 대화 제목 변경 | ✅ 필요 |
| DELETE | `/api/conversations/{id}` | 대화 삭제 | ✅ 필요 |
| POST | `/api/upload` | 지원 문서 업로드 및 벡터 저장 | ✅ 필요 |
| GET | `/api/documents` | 내가 업로드한 파일 목록 | ✅ 필요 |
| DELETE | `/api/documents/{filename}` | 파일 삭제 (전체 청크 제거) | ✅ 필요 |
| POST | `/api/chat` | 채팅 질문 (일반 응답, 계산기 메타데이터 포함) | ✅ 필요 |
| POST | `/api/chat/stream` | 채팅 질문 (SSE 스트리밍, `tool`/`chunk`/`calc` 이벤트) | ✅ 필요 |
| POST | `/api/calculator/income-tax` | 종합소득세(근로·사업·연금·기타·금융소득, 가상자산 분리과세 포함) 계산 | ✅ 필요 |
| POST | `/api/calculator/retirement` | 퇴직소득세 계산 | ✅ 필요 |
| POST | `/api/calculator/financial-income-tax` | 이전 금융소득 입력 형식의 별칭(종합소득세 계산기로 계산) | ✅ 필요 |
| POST | `/api/calculator/capital-gains` | 양도소득세 계산 | ✅ 필요 |
| POST | `/api/calculator/inheritance` | 상속세 계산 | ✅ 필요 |
| POST | `/api/calculator/gift` | 증여세 계산 | ✅ 필요 |
| POST | `/api/calculator/vat` | 부가가치세(일반·간이과세자) 계산 | ✅ 필요 |
| POST | `/api/calculator/penalty-tax` | 본세를 아는 가산세만 계산(계산기 화면은 각 세목 API의 `penalty_type` 옵션 사용) | ✅ 필요 |
| GET | `/api/law-articles/lookup` | 법령명·조문번호로 조문 원문 조회 (조문 뷰어) | ✅ 필요 |
| GET | `/api/tax-schedule` | 사업자 유형 기준 다가오는 신고·납부 기한 | ✅ 필요 |
| GET | `/api/tax-schedule/official?year=2026&month=10` | 국세청 월별 공식 게시 일정(출처·확인시각·최신 확인 실패 여부 포함) | ✅ 필요 |
| GET | `/api/health` | 서버·DB 상태 확인 | 불필요 |

> 자동 생성 API 문서: `http://localhost:8001/docs`

웹 사이드바의 **세무일정**에서 국세청 [월별 세무일정](https://www.nts.go.kr/nts/ad/taxSchdul/selectList.do?mi=135747)을 달력으로 조회할 수 있습니다. 이전·다음 달 버튼 외에도 달력 아이콘 또는 연월 입력으로 원하는 시점을 직접 선택할 수 있습니다(2000년 1월~다음 연도 12월). 백엔드는 해당 월의 공개 표를 30분 동안 캐시하고, 화면에 마지막 확인 시각과 원문 링크를 표시합니다. 재확인에 실패하면 24시간 이내의 이전 조회 결과만 경고와 함께 보여주며, 그 밖에는 오류로 처리합니다. 일정이 0건이면 미게시 가능성을 안내합니다. 기존 `/api/tax-schedule`의 사업자 유형별 고정 날짜 계산은 레거시 API이며 공식 일정이나 개인별 신고 의무로 사용하지 않습니다. 국세청 사이트 구조 변경·게시 지연·납세자별 예외는 자동 보정되지 않습니다.

`/api/law-articles/lookup`의 `article_no`에는 `59조의4`, `제59조의4 제9항 제1호 가목`처럼
공백이나 하위 단위가 포함된 표기도 전달할 수 있습니다. 조회에는 정규화된 조 번호
(`제59조의4`)를 사용하고, 응답의 `reference`에는 `article=59`, `article_branch=4`,
`paragraph=9`, `item=1`, `subitem="가"`처럼 각 단위를 분리해 반환합니다.
하위 단위가 지정되면 `target`에 실제 본문 대조 결과도 포함됩니다. `target.exists=true`이면
요청한 항·호·목의 `text`를 반환하고, 존재하지 않으면 조 전체 조회는 유지한 채
`target.exists=false`와 누락된 단계(`level`)·사유(`detail`)를 반환합니다.
