# 조문 검색 평가셋 (embedding-retrieval)

한국 세법 질문 203개와, 각 질문에 답하는 **현행 법령 조문**을 짝지은 검색 평가셋이다. 임베딩 모델과 하이브리드 검색이 질문에 맞는
조문을 상위 몇 위 안에 가져오는지 잰다.

| 항목 | 내용 |
|---|---|
| 파일 | [`datasets/embedding_retrieval.json`](datasets/embedding_retrieval.json) (데이터), [`datasets/embedding_retrieval_cases.md`](datasets/embedding_retrieval_cases.md) (문항 전체 목록) |
| 버전 | 1.1.0 (2026-11-06) |
| 규모 | 203문항 = 일상 표현 64 · 법령해석례 102 · 기존 용어 질문 37 |
| 정답 | 문항마다 현행 조문 1개(`required`), 일부 문항은 함께 정답으로 치는 조문(`acceptable`) |
| 언어 | 한국어 |
| 상태 | **세무 전문가 검수 전 초안 라벨.** 개발·시험 구분 없음([ROADMAP.md](../docs/ai/ROADMAP.md) A1·A2에서 보강 예정) |
| 만드는 코드 | [`build_embedding_set.py`](build_embedding_set.py) (DB 필요) |
| 측정 코드 | [`embedding_probe.py`](embedding_probe.py), [`embedding_candidate.py`](embedding_candidate.py), [`embedding_encode.py`](embedding_encode.py) |
| 기준 결과 | [CURRENT_STATUS.md](../docs/ai/CURRENT_STATUS.md) "임베딩 비교·조문 검색 평가셋 — 2026-11-06" |

## 왜 만들었나

이전 검색 평가셋([`datasets/retrieval.json`](datasets/retrieval.json), 39문항)은 "양도소득세 기본공제 금액은?"처럼 조문의 용어가
질문에 그대로 들어 있어 현재 검색이 거의 다 맞혔다. 그래서 임베딩 모델을 바꿔도 차이가 드러나지 않았다. 이 평가셋은 성격이 다른
질문을 섞어 점수가 꽉 차지 않게 하고, 묶음별로 따로 집계해 어떤 질문에서 강하고 약한지 보이게 했다.

## 검색 대상

라벨은 이 프로젝트 DB의 현행 법령 조문을 가리킨다. 2026-11-06 기준 검색 대상은 다음과 같다.

- 현행 법령 41개(법률·대통령령·부령), 조문 6,675개와 긴 조문을 나눈 항 16,099개. 조문 시행일 범위 2025-01-01~2026-07-31.
- 세목: 소득세·법인세·부가가치세·상속세 및 증여세·국세기본법·조세특례제한법·지방세 관계법·관세법 등.
- 법령해석례 207건도 DB에 있지만 **정답 후보가 아니다.** 벡터만 재는 측정에서는 후보에서 빼고, 하이브리드 측정에서는 결과에서 조문만 센다.

각 라벨에는 확인할 때 쓴 시행본의 시행일(`effective_date`)과 법령 페이지(`source_url`)를 남겼다. 법이 개정돼 조문이 바뀌면 라벨도
다시 확인해야 한다.

## 묶음과 만든 방법

### 1. 일상 표현 (colloquial, 64문항)

- **질문**: 이 평가셋을 위해 작성했다(작성: AI 코딩 도우미 Claude, 2026-11-06). 납세자가 실제로 물을 법한 주제를 고르고, 조문의 용어를
  피해 일상 말투로 썼다. 예: "월세 받는 집이 딱 한 채뿐인데 그 임대 수입에도 세금을 내야 하나요?" → 소득세법 제12조(비과세소득).
- **정답**: 질문의 답을 정하는 조문 하나. 저장된 조문의 제목과 본문을 하나씩 대조해 그 내용을 다루는지 확인했다
  (예: 전세대출 원리금 공제가 소득세법 제52조 본문에 있는지). 법령 9개, 중앙값 31자.
- **함께 인정**(3문항): 정답과 함께 같은 결론을 정하는 조문.

  | 문항 | 정답 | 함께 인정 | 이유 |
  |---|---|---|---|
  | col-19 1주택 2년 보유 후 양도 | 소득세법 시행령 제154조 | 소득세법 제89조 | 비과세 규정(법)과 요건(시행령) |
  | col-44 증여세율 | 상속세 및 증여세법 제56조 | 같은 법 제26조 | 제56조가 제26조의 세율을 그대로 쓴다 |
  | col-62 6월 매도와 재산세 납세자 | 지방세법 제114조(과세기준일) | 같은 법 제107조(납세의무자) | 기준일 현재 소유자가 낸다 |

### 2. 법령해석례 (interpretation, 102문항)

- **원자료**: DB에 저장된 법제처 법령해석 207건(2005~2025년 회신). 각 건의 제목은 대체로
  `질의기관 - 쟁점(「법령명」 제N조제M항 등 관련)` 형식이다.
- **질문**: 제목의 쟁점 부분. 법률 문체이며 중앙값 50자. 예: "혼인으로 1세대 2주택이 된 비거주자의 주택 양도 시 양도소득세의 비과세 여부".
- **정답**: 제목 괄호 안에서 **처음 인용한 조문**이 현행 DB에 있으면 그 조문. 나머지 인용 조문 중 현행에 있는 것은 함께 인정(4문항).
- **제외**: 제목이 위 형식이 아닌 65건, 처음 인용한 법령이 검색 대상 DB에 없거나 그 조문이 현행이 아닌 40건. 남은 102건은 2009~2025년 회신이다.
- **표시**: 질문 안에 「법령명」 제N조가 들어 있는 33문항은 `explicit_reference: true`. 조문 번호로 바로 찾을 수 있어 따로 집계한다.
- **출처**: 문항마다 해석 원문 링크(`source_url`, 국가법령정보센터).
- **법령 분포**: 지방세특례제한법 18, 조세특례제한법 14, 소득세법 11, 지방세법 10, 지방세법 시행령 10 등 18개. 지방세 쪽이 많다.

### 3. 기존 용어 질문 (legacy, 37문항)

- [`datasets/retrieval.json`](datasets/retrieval.json)의 39문항 중 현행 조문 정답(`required`)이 있는 37문항. 정답이 없는 비교 질문 1개와 정답이
  법령해석 번호인 1개를 뺐다. 중앙값 25자.
- 원래 평가셋의 헷갈리는 오답(`hard_negative`) 6개를 `hard_negatives`로 옮겼다(점수에는 쓰지 않는다).

## 데이터 형식

```json
{
  "id": "col-19",
  "tier": "colloquial",
  "query": "집 한 채를 2년 넘게 갖고 있다가 팔면 세금을 안 내도 되나요?",
  "required": [{"law": "소득세법 시행령", "article": "제154조", "title": "1세대1주택의 범위",
                "effective_date": "20260421", "source_url": "https://www.law.go.kr/lsInfoP.do?lsiSeq=..."}],
  "acceptable": [{"law": "소득세법", "article": "제89조", "title": "비과세 양도소득", "...": "..."}],
  "source": "written for this set; label checked against the stored article"
}
```

| 필드 | 뜻 |
|---|---|
| `id` | `col-NN`, `int-<해석 번호>`, `leg-<기존 id>` |
| `tier` | `colloquial` · `interpretation` · `legacy` |
| `query` | 검색에 넣는 질문 원문 |
| `required` | 정답 조문 1개(법령명·조문 번호, 확인한 시행본의 제목·시행일·법령 링크) |
| `acceptable` | 찾으면 정답으로 치는 다른 조문 |
| `explicit_reference` | (해석례) 질문에 「법령명」 제N조가 있음 |
| `hard_negatives` | (기존) 헷갈리는 오답. 참고용 |
| `source`, `source_url` | 라벨 출처, 해석 원문 링크 |

조문은 `(법령명, 조문 번호)`로 맞힌다. 같은 조문의 항이 검색되면 그 조문을 찾은 것으로 본다.

## 지표

| 지표 | 정의 |
|---|---|
| hit@k | `required` 또는 `acceptable` 조문이 상위 k개 안에 든 문항의 비율(k = 1, 5, 10, 20) |
| MRR@20 | 처음 맞힌 순위의 역수 평균(1위 1, 2위 0.5, 20위 밖 0) |
| 한쪽만 맞힌 문항 | 두 설정을 비교할 때 같은 문항에서 한쪽만 상위 k개에 정답을 넣은 수. 부호 검정 p값을 함께 낸다 |

집계는 전체, 묶음별, "해석례 중 조문 번호 없는 질문" 다섯 가지로 낸다. 203문항에서는 대략 4~5%p 미만의 평균 차이를 우연과 구분하기
어려우므로 한쪽만 맞힌 문항 수와 p값으로 판단한다.

## 사용법

WSL 가상환경에서 실행한다(DB와 Ollama 필요). 결과는 `evaluation/runs/`(Git 제외)에 `results.json`·`report.md`로 남는다.

```bash
source venv-wsl/bin/activate
python evaluation/build_embedding_set.py      # 평가셋과 문항 목록 다시 만들기

# 지금 임베딩의 벡터 검색만
python evaluation/embedding_probe.py --mode vector --output evaluation/runs/embedding-probe/<이름>-vector
# 답변 파이프라인이 쓰는 검색 경로(벡터+BM25 결합·제목 보정·직접 조회·MMR, Graph 끔)
python evaluation/embedding_probe.py --mode issue --output evaluation/runs/embedding-probe/<이름>-issue

# 다른 임베딩 모델 비교: 문서·질문 내보내기 → 다른 환경에서 임베딩 → 채점·짝 비교
python evaluation/embedding_candidate.py export
python evaluation/embedding_encode.py --run evaluation/runs/embedding-candidates --model <HF 모델> --name <이름>
python evaluation/embedding_candidate.py score --model <이름>
python evaluation/embedding_candidate.py compare --candidate <이름> --k 5
# 그 모델 벡터를 검색 경로에 넣어 판정(DB는 바꾸지 않음). 유사도 임계값은 후보 통과 비율을 맞춰 정한다
python evaluation/embedding_probe.py --mode issue --vectors evaluation/runs/embedding-candidates/<이름> \
  --threshold <값> --output evaluation/runs/embedding-probe/issue-<이름>
```

Windows의 Ollama를 쓰면 `OLLAMA_BASE_URL`·`EMBEDDING_BASE_URL`을 `http://<WSL 기본 게이트웨이>:11434`로 둔다.
`--mode issue`는 BM25 색인을 먼저 만들고, 검색이 다른 키워드 검색으로 넘어간 횟수를 `search_fallbacks`로 기록한다(0이어야 한다).

## 한계

- **검수 전 라벨.** 일상 표현의 정답은 조문 제목·본문 대조까지 했을 뿐 세무 전문가가 확인하지 않았다. 해석례의 "처음 인용한 조문"은
  결론을 정한 조문이 아닐 수 있다.
- **해석 시점과 현행 조문의 차이.** 평가셋의 해석례는 2009~2025년 회신인데 정답은 현행 조문이다. 공식 회답 정답셋을 만들며 대조해 보니
  해석례 102문항 중 **36문항은 회신 후 정답 조문의 인용 항이 바뀌었다**(2010년 지방세법 전부개정처럼 같은 번호가 다른 조문이 된 경우 포함).
  이 라벨은 틀렸을 수 있다. `interpretation_gold.json`의 `validity`가 `unchanged`인 해석 번호만 남기는 방법으로 다음 버전에서 고친다.
- **정답 하나.** 실제 질문은 여러 조문이 함께 답하는 경우가 많다. 이 평가셋은 대표 조문 하나를 찾는지만 본다.
- **분포 치우침.** 해석례는 지방세 관계법이 많고, 일상 표현은 소득세·상속세 및 증여세 주제가 많다.
- **조정에 쓴 문항.** 개발·시험 구분이 없어, 이 문항으로 검색 설정을 조정하면 점수가 부풀 수 있다.
- **실제 답변 경로와의 차이.** 질문 원문 하나로 세목 필터 없이 검색한다. 실제 답변은 질문을 쟁점으로 나누고 세목별로 검색어를 다듬는다.
- **하이브리드에서의 해석례.** 해석례 질문은 그 해석 문서 자체가 하이브리드 결과 칸을 차지할 수 있어, 해석례 묶음의 하이브리드 점수는 낮게 나온다.

## 출처와 이용

- 법령 조문: 국가법령정보센터(law.go.kr). 법령은 저작권법 제7조에 따라 보호받지 않는 저작물이다.
- 법령해석례: 법제처 법령해석(국가법령정보센터). 질문은 해석 제목의 쟁점 문장을 그대로 썼고, 문항마다 원문 링크를 남겼다.
- 일상 표현 질문과 묶음 구성·라벨은 이 프로젝트에서 만들었다. 저장소의 라이선스는 아직 정하지 않았다(README "라이선스").

## 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.0.0 | 2026-11-06 | 처음 구성(203문항) |
| 1.1.0 | 2026-11-06 | 라벨에 확인한 시행본의 제목·시행일·법령 링크, 해석례에 원문 링크를 더하고 문항 목록 문서를 만든다. 문항·정답은 1.0.0과 같다 |
