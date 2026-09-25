# 국제세무 공식자료 1차 수집·검수 기록

## 결과

- 범위: 한국과 연결된 미국·일본·중국 세무 자료 및 한–미·한–일·한–중 조약. 한국 국내법은 기존 프로젝트 수집분을 보존하고 이번 배치에서 재수집하지 않았다.
- 공식 출처 문서 **17/17건 수집**, 실패 0, 원본 합계 21,549,949 bytes. 원본 파일 17개와 검토용 추출 텍스트 17개를 `evaluation/sources/international-tax/pilot-2026-09-25/`에 보존했다.
- 모든 원본의 SHA-256·파일 크기와 추출 텍스트 길이를 재검수했다. 자세한 목록과 각 문서 링크는 [로컬 검토 페이지](../../evaluation/sources/international-tax/pilot-2026-09-25/review.html) 또는 같은 폴더의 `manifest.json`에서 확인한다. 원본 폴더는 Git·Docker 빌드에서 제외된다.
- 미국 5건: 2024년 미국 법전 §7701·§901 스냅샷, IRS 거주자·소득 원천·외국납부세액공제 안내. 한–미 조약 1건.
- 일본 3건: e-Gov 소득세법 XML, 일본 국세청 2025년 소득세 안내·외국납부세액공제 안내. 한–일 조약 원문·MLI 적용 설명·통합 참고문 3건.
- 중국 3건: 중국어 개인소득세법 원문, 국가세무총국 영문 법령·시행규칙 참고문. 한–중 조약 원문·제2의정서 2건.

## 검수 경계

- 현재 `review_status=unreviewed` **17건**. 수집·해시 검사는 법령의 적용 시점, 개정 반영 여부, 조약 효력이나 납세자 사실관계에 대한 검증이 아니다. `effective_from`/`effective_to`는 확인 전이므로 비어 있다.
- 한–일 조약 **법적 원문 PDF는 스캔본**으로 텍스트 추출 58자뿐이다(`ocr_required=true`). 보존된 원본에 OCR 및 조문별 대조가 필요하다. 별도 수집한 일본 재무성의 MLI 통합 참고문은 읽을 수 있지만 **법적 원문이 아니다**.
- 미국 법전 자료는 `USCODE-2024` 판본으로 명시했다. 2026년 현행법이라고 간주하지 않는다. 일본 국세청 소득세 안내도 2025년판이다. 중국 영문 자료는 원문 대조 전 참고 번역으로만 분류했다.
- HTML 추출 텍스트에는 메뉴·각주 등 주변 문구가 포함될 수 있다. 원문 파일과 대조해 본문 선택기·조문 구조·발효 날짜를 검수한 후 검색 인덱스에 넣어야 한다.
- **평가 정답셋, 학습셋, 프로덕션 RAG/Graph/DB로 자동 연결하지 않았다.** 국가 간 혼합 검색이나 외국 세액 계산도 아직 없다. 외부 배포·재배포 전 각 출처의 이용 조건을 별도 확인한다.

## 재현·검수 명령

```bash
source venv-wsl/bin/activate
python scripts/collect_international_tax.py --output evaluation/sources/international-tax/NEW_BATCH
python scripts/collect_international_tax.py --output evaluation/sources/international-tax/NEW_BATCH --audit
# 중단·실패 항목 재개: 위 output에 --resume 추가
```

수집 목록·검증 규칙: `evaluation/international_sources.py`. 감사 명령은 기존 원본을 수정하지 않는다.
