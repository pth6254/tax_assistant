"""Read-only recovery of truncated current provisions from the SAME official version.

Never selects the latest archive version or modifies live rows/embeddings.
Law identity, MST, effective date, XML hash and parsed metadata must all match.
"""
from datetime import date
import logging
from urllib.parse import parse_qs, urlparse

from app.services.evidence import digest, has_missing_items
from app.services.law.parser_service import parse_articles

logger = logging.getLogger(__name__)

_SNAPSHOT = '''SELECT s.id, s.raw_xml, s.content_hash
    FROM law_history.versions v JOIN law_history.snapshots s ON s.version_id=v.id
    WHERE v.mst=$1 AND v.law_name=$2 AND v.effective_date=$3
      AND v.fetch_status='complete'
    ORDER BY s.collected_at DESC, s.id DESC LIMIT 1'''


async def recover_article(row, conn):
    if not has_missing_items(row['article_text']):
        return row
    url = urlparse(row.get('source_url') or '')
    if url.hostname not in {'www.law.go.kr', 'law.go.kr'}:
        return row
    mst = parse_qs(url.query).get('lsiSeq', [''])[0]
    if not mst.isdigit():
        return row
    try:
        effective = date.fromisoformat(row['effective_date'])
        snapshot = await conn.fetchrow(_SNAPSHOT, mst, row['law_name'], effective)
        if not snapshot or digest(snapshot['raw_xml']) != snapshot['content_hash']:
            return row
        articles = parse_articles(snapshot['raw_xml'])
        matching = [article for article in articles if article.law_name == row['law_name']
                    and article.article_no == row['article_no']
                    and date.fromisoformat(article.effective_date) == effective
                    and article.amendment_date.replace('-', '') == row['amendment_date'].replace('-', '')]
        if len(matching) != 1 or has_missing_items(matching[0].article_text):
            return row
        article = matching[0]
        if len(article.article_text) <= len(row['article_text']):
            return row
        return dict(row) | {'id': f"history_snapshot:{snapshot['id']}:{article.article_no}",
                            'article_text': article.article_text,
                            'article_title': article.article_title,
                            'content_hash': digest(article.article_text)}
    except Exception as exc:
        # Missing archive/invalid metadata never makes incomplete text admissible.
        logger.warning('Official source recovery unavailable (%s)', type(exc).__name__)
        return row
