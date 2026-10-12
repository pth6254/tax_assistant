"""
test_api_calculator.py — 세금 계산기 엔드포인트 테스트
"""
import pytest


# ── 인증 검사 ────────────────────────────────────────────────────

def test_income_tax_without_auth_returns_401(client):
    resp = client.post("/api/calculator/income-tax", json={"income": 50000000})
    assert resp.status_code == 401


def test_vat_without_auth_returns_401(client):
    resp = client.post("/api/calculator/vat", json={"sales": 100000000})
    assert resp.status_code == 401


def test_penalty_tax_without_auth_returns_401(client):
    resp = client.post("/api/calculator/penalty-tax", json={"unpaid_tax": 10000000})
    assert resp.status_code == 401


# ── 유효성 검사 ──────────────────────────────────────────────────

def test_vat_missing_sales_returns_422(client, auth_cookie):
    resp = client.post("/api/calculator/vat", json={}, cookies=auth_cookie)
    assert resp.status_code == 422


def test_penalty_tax_missing_unpaid_tax_returns_422(client, auth_cookie):
    resp = client.post("/api/calculator/penalty-tax", json={}, cookies=auth_cookie)
    assert resp.status_code == 422


# ── 정상 응답 (세율표는 공식 사례 테스트와 같은 고정값; 실제 DB를 읽지 않는다) ────────

@pytest.fixture
def stored_rates(monkeypatch):
    from app.services.calculator import penalty_tax, vat
    from tests.test_vat_penalty import penalty_params, vat_params

    async def vat_rates(as_of=None):
        return vat_params()

    async def penalty_rates(as_of=None):
        return penalty_params()
    monkeypatch.setattr(vat, "load_parameters", vat_rates)
    monkeypatch.setattr(penalty_tax, "load_parameters", penalty_rates)


def test_vat_general_calculation(client, auth_cookie, stored_rates):
    resp = client.post(
        "/api/calculator/vat",
        json={"sales": 100000000, "purchases": 60000000},
        cookies=auth_cookie,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tax_type"] == "부가가치세"
    assert body["final_tax"] == 4000000


def test_penalty_tax_no_filing_calculation(client, auth_cookie, stored_rates):
    resp = client.post(
        "/api/calculator/penalty-tax",
        json={"unpaid_tax": 10000000, "penalty_type": "무신고"},
        cookies=auth_cookie,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tax_type"] == "가산세"
    assert body["final_tax"] == 12000000
