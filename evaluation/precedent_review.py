"""Export a standalone, read-only HTML document from a collected batch."""
import argparse
import html
import json
from pathlib import Path
import re


def plain(value):
    text = re.sub(r'<br\s*/?>', '\n', str(value), flags=re.I)
    return html.unescape(re.sub(r'<[^>]*>', '', text))


def export(batch):
    root = Path(batch)
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    cards = json.loads((root/'draft-cards.json').read_text(encoding='utf-8'))['cases']
    indexed = {c['id'].removeprefix('precedent-'):c for c in cards}
    esc = html.escape
    sections, links = [], []
    for record in manifest['records']:
        pid = record['id']
        if not pid.isdigit() or record['file'] != f'{pid}.json':
            raise ValueError('Unexpected source filename')
        data = json.loads((root/record['file']).read_text(encoding='utf-8'))['PrecService']
        title = f'{record["case_number"]} · {record["title"]}'
        card = indexed.get(pid)
        label = '평가 초안 있음' if card else '수집 후보 — 평가 초안 없음'
        links.append(f'<li><a href="#case-{pid}">{esc(title)}</a> <small>{label}</small></li>')
        section = [f'<article id="case-{pid}"><h2>{esc(title)}</h2>',
            f'<p>{esc(str(data.get("법원명", "")))} · 선고일 {esc(str(data.get("선고일자", "")))} · {esc(str(data.get("사건종류명", "")))}</p>',
            f'<p><strong>{label} / 미승인</strong> · <a href="https://www.law.go.kr/precInfoP.do?precSeq={pid}" target="_blank" rel="noopener noreferrer">공식 출처 열기</a></p>']
        if card:
            section += ['<h3>평가 질문 초안</h3>',f'<p>{esc(card["input"]["query"])}</p>',
                        '<h3>채점 기준 초안 — 검수 필요</h3><ul>']
            section += [f'<li>{esc(r["instruction"])}</li>' for r in card['rubric']]
            section += ['</ul><h3>검수할 사항</h3><ul>']
            section += [f'<li>{esc(t)}</li>' for t in card['input']['review_card']['approval_todo']]
            section += ['</ul>']
        for field in ['판시사항','판결요지','참조조문','참조판례','판례내용']:
            section += [f'<h3>{field}</h3><pre>{esc(plain(data.get(field, "제공되지 않음")))}</pre>']
        section += ['<p><a href="#top">목록으로 돌아가기</a></p></article>']
        sections.append('\n'.join(section))
    content = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>세무 판례 검수 자료</title><style>
body{max-width:1050px;margin:36px auto;padding:0 20px;color:#202b38;background:#f5f7fa;font:17px/1.8 system-ui,sans-serif}
article,header{background:white;border:1px solid #dde3eb;border-radius:12px;padding:24px;margin:24px 0}
h2{font-size:23px}h3{margin-top:28px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
a{color:#1256a0}small{color:#526175}li{margin:8px 0}@media print{article{break-before:page}body{background:white}}
</style><header id="top"><h1>세무 판례 검수 자료</h1>
<p>수집 원문 10건과 평가 질문 초안 5건입니다. 확정된 정답셋이 아닙니다.
판결요지는 공식 API 제공 내용이며 채점 기준은 별도로 작성한 미검수 초안입니다.</p>
<p>읽기 전용 파일입니다. 체크·승인·메모 저장 기능은 없으며 원본 JSON이나 검수 상태를 변경하지 않습니다.
사건번호와 함께 수정할 내용·근거 문장을 알려주세요. 전체 본문은 요약하지 않고 줄바꿈과 HTML 표기만 정리했습니다.</p><ol>'''
    content += '\n'.join(links) + '</ol></header>' + '\n'.join(sections) + '</html>'
    target = root/'검수자료.html'
    with target.open('x',encoding='utf-8') as file:
        file.write(content)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', required=True)
    args = parser.parse_args()
    print(export(args.batch))
