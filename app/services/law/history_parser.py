"""Lossless historical XML units, independent of live article filtering."""
from datetime import datetime
import hashlib
import re
import xml.etree.ElementTree as ET

PARSER_VERSION = '1'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def redact(text, secret=''):
    if secret:
        text = text.replace(secret, '[REDACTED]')
    return re.sub(r'(?i)(\bOC=)[^&\s<>"\']+', r'\1[REDACTED]', text)


def date(value, required=False):
    if not value and not required:
        return None
    return datetime.strptime(value, '%Y%m%d').date()


def text(node, tag):
    return (node.findtext(tag) or '').strip()


def tree(node):
    return dict(tag=node.tag, attributes=dict(node.attrib), text=node.text or '',
                tail=node.tail or '', children=[tree(c) for c in node])


def listing(xml, law_id):
    root = ET.fromstring(xml)
    if root.tag != 'LawSearch' or root.find('totalCnt') is None:
        raise ValueError('Invalid history listing envelope')
    total = int(text(root, 'totalCnt'))
    rows = []
    for node in root.findall('law'):
        if text(node, '법령ID').lstrip('0') != law_id.lstrip('0'):
            raise ValueError('History listing law identity mismatch')
        mst = text(node, '법령일련번호')
        if not mst.isdigit():
            raise ValueError('Invalid MST')
        rows.append(dict(law_id=law_id, mst=mst,
            effective_date=date(text(node, '시행일자'), True),
            law_name=text(node, '법령명한글'), law_type=text(node, '법령구분명'),
            promulgation_date=date(text(node, '공포일자')),
            promulgation_number=text(node, '공포번호'), revision_type=text(node, '제개정구분명'),
            listing_status=text(node, '현행연혁코드'),
            metadata={c.tag: redact(c.text or '') for c in node if c.tag != '법령상세링크'}))
    return rows, total


def parse(xml, *, law_id=None, effective_date=None, promulgation_date=None):
    root = ET.fromstring(xml)
    basic = root.find('기본정보')
    if root.tag != '법령' or basic is None:
        raise ValueError('Invalid law detail envelope')
    identity = text(basic, '법령ID')
    if not identity.isdigit():
        raise ValueError('Missing law identity')
    if law_id is not None and identity.lstrip('0') != law_id.lstrip('0'):
        raise ValueError('Detail law identity mismatch')
    if effective_date is not None and date(text(basic, '시행일자'), True) != effective_date:
        raise ValueError('Detail effective date mismatch')
    if promulgation_date is not None and date(text(basic, '공포일자')) != promulgation_date:
        raise ValueError('Detail promulgation date mismatch')
    articles = []
    for order, node in enumerate(root.findall('./조문/조문단위')):
        # Keep headings/deletions and all paragraph/item text; never skip old units.
        content_tags = {'조문내용','항번호','항내용','호번호','호내용','목번호','목내용'}
        body = '\n'.join((n.text or '').strip() for n in node.iter()
                         if n.tag in content_tags and (n.text or '').strip())
        articles.append(dict(source_order=order, source_key=node.get('조문키',''),
            article_number=text(node,'조문번호'), article_branch=text(node,'조문가지번호'),
            unit_kind=text(node,'조문여부'), title=text(node,'조문제목'), body=body,
            content_hash=sha(body), structure=tree(node)))
    supplements = [dict(source_order=i, source_key=n.get('부칙키',''),
        body='\n'.join(t.strip() for t in n.itertext() if t.strip()), structure=tree(n))
        for i,n in enumerate(root.findall('./부칙/부칙단위'))]
    if not articles and not supplements:
        raise ValueError('Empty law detail')
    return dict(law_id=identity, name=text(basic,'법령명_한글'), articles=articles, supplements=supplements)
