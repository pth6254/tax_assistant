"""Bounded official precedent collection, isolated from production databases."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

import httpx
from dotenv import dotenv_values


def redact(text):
    return re.sub(r'(?i)(\bOC(?:=|%3D))[^&\s"<>]+', r'\1REDACTED', text)


def write(path, value):
    with path.open('x', encoding='utf-8') as file:
        file.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def collect(output):
    key = dotenv_values('.env').get('LAW_API_KEY')
    if not key:
        raise ValueError('Missing API credential')
    root = Path(output)
    root.mkdir(parents=True, exist_ok=False)
    manifest = {'collected_at':datetime.now(timezone.utc).isoformat(), 'source':'law.go.kr',
                'scope':'10 maximum; Supreme Court source; evaluation only', 'records':[], 'errors':[]}
    seen = set()
    try:
        with httpx.Client(timeout=40, follow_redirects=False) as client:
            for law in ['소득세법','부가가치세법','법인세법','상속세 및 증여세법']:
                if len(manifest['records']) >= 10:
                    break
                params = dict(OC=key,target='prec',type='JSON',JO=law,org='400201',
                              datSrcNm='대법원',display=10,page=1,sort='ddes')
                response = client.get('https://www.law.go.kr/DRF/lawSearch.do',params=params)
                response.raise_for_status()
                payload = json.loads(response.text)
                write(root/f'list-{len(seen)}-{len(manifest["records"])}.json',json.loads(redact(response.text)))
                listing = payload.get('PrecSearch',{}).get('prec',[])
                if isinstance(listing,dict): listing=[listing]
                print(json.dumps({'law':law,'candidates':len(listing)},ensure_ascii=False),flush=True)
                accepted = 0
                for item in listing:
                    if len(manifest['records']) >= 10 or accepted >= 3: break
                    pid = str(item.get('판례일련번호',''))
                    if not pid.isdigit() or pid in seen: continue
                    seen.add(pid)
                    time.sleep(0.5)
                    try:
                        detail = client.get('https://www.law.go.kr/DRF/lawService.do',params=dict(OC=key,target='prec',type='JSON',ID=pid))
                        detail.raise_for_status()
                        sanitized = redact(detail.text)
                        data = json.loads(sanitized)
                        body = data.get('PrecService',{})
                        if str(body.get('판례정보일련번호','')) != pid: raise ValueError('ID mismatch')
                        if body.get('사건번호') != item.get('사건번호'): raise ValueError('Case mismatch')
                        if len(str(body.get('판례내용',''))) < 200: raise ValueError('Insufficient body')
                        write(root/f'{pid}.json',data)
                        manifest['records'].append({'id':pid,'law_search':law,
                            'case_number':body.get('사건번호'),'title':body.get('사건명'),
                            'court':body.get('법원명'),'decision_date':body.get('선고일자'),
                            'source_url':f'https://www.law.go.kr/precInfoP.do?precSeq={pid}',
                            'sha256':hashlib.sha256(sanitized.encode()).hexdigest(),
                            'hash_basis':'credential-redacted API response before JSON formatting',
                            'file':f'{pid}.json','review_status':'draft'})
                        accepted += 1
                        print(json.dumps({'collected':pid,'case':body.get('사건번호')},ensure_ascii=False),flush=True)
                    except Exception as error:
                        manifest['errors'].append({'id':pid,'type':type(error).__name__})
    except Exception as error:
        manifest['errors'].append({'stage':'list','type':type(error).__name__})
    finally:
        write(root/'manifest.json',manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--cards-only', action='store_true', help='Build draft cards from an existing pilot; no network')
    args=parser.parse_args()
    try:
        if args.cards_only:
            build_cards(Path(args.output))
            return 0
        result=collect(args.output)
        print(json.dumps({'collected':len(result['records']),'errors':result['errors']},ensure_ascii=False))
        return 0 if len(result['records'])==10 else 2
    except Exception as error:
        print(type(error).__name__)
        return 3


def build_cards(root):
    from evaluation.schema import Dataset
    selected = [
        ('623075','구법상 일시적 2주택 특례에서 신규 주택 취득 후 기존 임차인과 연장한 계약의 종료일을 전입기한 판단에 쓸 수 있나요?',
         '취득 당시 계약과 취득 후 연장 약정을 구별하고 판결이 적용한 구법 범위에 한정하여 설명한다.'),
        ('619463','예식업체가 별도 사업장에서 생화 꽃 장식을 예식장에 설치해 고객에게 공급하면 별도 사업장이라는 이유만으로 면세인가요?',
         '재화·용역의 실질과 예식용역에 부수되는지 구분하고 사업장 분리만으로 면세를 단정하지 않는다.'),
        ('622927','여러 국외사업장이 있는 내국법인의 외국납부세액 공제에서 특정 국가의 결손을 어떻게 고려하나요? 이 판결이 적용한 규정을 기준으로 설명해주세요.',
         '판결의 공제한도 계산 규정과 조세조약의 역할을 분리하고 적용 법령 버전을 명시한다.'),
        ('621977','여신금융기관이 법정 상한을 위반하여 지급한 대부중개수수료도 수익과 관련된 비용이면 손금으로 인정되나요?',
         '수익 관련성만으로 인정하지 않고 상한 위반 비용에 대한 판결의 판단과 범위를 설명한다.'),
        ('622257','상속받은 토지를 나중에 매각한 가격을 상속 당시 시가로 사용할 때, 가격 변동 여부와 증명책임은 어떻게 판단하나요?',
         '평가기준일과 매매계약일 사이 가격 변동 및 과세관청의 증명책임을 구분한다.'),
    ]
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    indexed={r['id']:r for r in manifest['records']}
    cases=[]
    for pid, question, instruction in selected:
        if pid not in indexed: continue
        entry=indexed[pid]
        body=json.loads((root/entry['file']).read_text(encoding='utf-8'))['PrecService']
        cases.append(dict(id='precedent-'+pid,group='precedent-'+pid,split='dev',stage='answer',adapter='recorded',
            review=dict(status='draft',basis='official_source',notes='API 원문 수집/쟁점 기반 초안. 원문 전체·관련 심급·구법/부칙 및 인간 검수 미완료.'),
            input=dict(query=question,review_card=dict(case_number=entry['case_number'],
                decision_date=entry['decision_date'],source_file=entry['file'],source_hash=entry['sha256'],
                issues_html=body.get('판시사항',''),holding_html=body.get('판결요지',''),
                cited_laws_html=body.get('참조조문',''),required_claims=[instruction],
                forbidden_claims=['이 사건 결론을 사실관계와 적용 시점에 관계없이 모든 현재 사례에 일반화한다.'],
                approval_todo=['사실관계 정리 및 결론 누출 없는 질문 검수','파기환송/후속심 및 동일 사건 그룹 연결',
                               '적용 귀속기간·구법·부칙 확인','정확한 hard negative와 정상/오답 대조 사례 작성'],
                tax_period=None,reference_verified=False)),
            source_url=entry['source_url'],tags=['precedent','draft','not-for-training'],
            rubric=[dict(id='case-reasoning',dimension='factuality',instruction=instruction,critical=True),
                    dict(id='temporal-scope',dimension='temporal',instruction='판결 선고일과 과세 귀속기간을 구별하고 현행법으로 소급 대체하지 않는다.',critical=True)]))
    dataset=Dataset(name='precedent-pilot',version='0.1.0',description='수집 판례 5건의 검수 초안. 법적 정답 승인 및 Judge 실행 전.',cases=cases)
    write(root/'draft-cards.json',dataset.model_dump(mode='json'))
    lines=['# 판례 수집·검수 후보', '', '운영 DB/학습 미반영. 아래 카드는 전부 draft이며 법적 정답 승인이 아닙니다.', '',
           '| 사건번호 | 사건명 | 선고일 | 초안 선정 |','|---|---|---|---|']
    for entry in manifest['records']:
        lines.append(f'| {entry["case_number"]} | {entry["title"]} | {entry["decision_date"]} | {"선정" if entry["id"] in {s[0] for s in selected} else "후보 보존"} |')
    with (root/'README.md').open('x',encoding='utf-8') as file: file.write('\n'.join(lines)+'\n')
    print(json.dumps({'draft_cards':len(cases),'approved':0}))


if __name__ == '__main__':
    raise SystemExit(main())
