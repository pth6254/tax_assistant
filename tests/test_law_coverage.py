from unittest.mock import AsyncMock

import pytest

from app.schemas.law import LawSummary
from app.services.law import coverage_service as coverage
from app.services.law import ingestion_service as ingestion


@pytest.mark.asyncio
async def test_discovery_accepts_current_ministry_and_rejects_unrelated(monkeypatch):
    monkeypatch.setattr(ingestion, '_TAX_SEARCH_KEYWORDS', ['소득세'])
    laws = [LawSummary(str(i), name, '', '', ministry) for i, (name, ministry) in enumerate([
        ('소득세법 시행령', '재정경제부'),
        ('소득세법 시행규칙', '기획재정부'),
        ('지방세법 시행령', '행정안전부'),
        ('무관 법령', '환경부'),
    ])]
    monkeypatch.setattr(ingestion, 'search_law_all_pages', AsyncMock(return_value=laws))
    result = await ingestion.discover_tax_laws()
    assert [r['law_name'] for r in result] == [x.law_name for x in laws[:3]]


@pytest.mark.asyncio
async def test_coverage_manifest_and_existing_names(monkeypatch):
    pool = AsyncMock()
    pool.fetch.return_value = [{'law_name': '소득세법시행령'}]
    monkeypatch.setattr(coverage, 'get_pool', AsyncMock(return_value=pool))
    assert len(coverage.REQUIRED_SUBORDINATE_LAWS) == 14
    missing = await coverage.missing_subordinate_laws()
    assert len(missing) == 13
    assert '소득세법 시행령' not in [r['law_name'] for r in missing]
    assert "law_type <> '법령해석례'" in pool.fetch.call_args.args[0]
