from unittest.mock import AsyncMock
import pytest
from app.services.evidence import digest, has_missing_items
from app.services.law.source_recovery import recover_article


XML = '''<법령><기본정보><법령명_한글>시험법</법령명_한글><법종구분>법률</법종구분>
<시행일자>20260102</시행일자><공포일자>20251001</공포일자></기본정보>
<조문><조문단위><조문번호>39</조문번호><조문여부>조문</조문여부><조문제목>요건</조문제목>
<조문내용>제39조(요건)</조문내용><항><항번호>①</항번호><항내용>다음 각 호에 따른다.</항내용>
<호><호번호>1.</호번호><호내용>첫 번째 요건에 해당하는 경우</호내용></호>
<호><호번호>2.</호번호><호내용>두 번째 요건에 해당하는 경우</호내용></호></항></조문단위></조문></법령>'''


def row():
    return dict(id=17, law_name='시험법', article_no='제39조', article_title='요건',
                article_text='제39조\n① 다음 각 호에 따른다.', effective_date='20260102',
                amendment_date='20251001', source_url='https://www.law.go.kr/lsInfoP.do?lsiSeq=123',
                content_hash=digest('제39조\n① 다음 각 호에 따른다.'))


@pytest.mark.asyncio
async def test_recovers_only_complete_identical_version_without_writes():
    original = row()
    conn = AsyncMock()
    conn.fetchrow.return_value = dict(id=128, raw_xml=XML, content_hash=digest(XML))
    result = await recover_article(original, conn)
    assert has_missing_items(original['article_text'])
    assert not has_missing_items(result['article_text'])
    assert '1.' in result['article_text'] and '2.' in result['article_text']
    assert result['id'] == 'history_snapshot:128:제39조'
    assert result['content_hash'] == digest(result['article_text'])
    assert conn.fetchrow.call_args.args[1:3] == ('123', '시험법')
    conn.execute.assert_not_called()


@pytest.mark.parametrize('change', ['hash', 'date', 'law', 'amendment', 'missing_snapshot'])
@pytest.mark.asyncio
async def test_wrong_version_or_corrupt_source_stays_blocked(change):
    original = row()
    xml = XML
    if change == 'date':
        xml = xml.replace('20260102', '20250102')
    if change == 'law':
        xml = xml.replace('시험법', '다른법')
    if change == 'amendment':
        xml = xml.replace('20251001', '20241001')
    snapshot = dict(id=128, raw_xml=xml, content_hash='bad' if change == 'hash' else digest(xml))
    conn = AsyncMock()
    conn.fetchrow.return_value = None if change == 'missing_snapshot' else snapshot
    assert await recover_article(original, conn) is original
