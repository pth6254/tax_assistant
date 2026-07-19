"""
test_api_calculator.py — 세금 계산기 엔드포인트 테스트
"""


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


# ── 정상 응답 (DB 세율표 실측값 — 001/007 시드와 동일 조건) ────────

def test_vat_general_calculation(client, auth_cookie):
    resp = client.post(
        "/api/calculator/vat",
        json={"sales": 100000000, "purchases": 60000000},
        cookies=auth_cookie,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tax_type"] == "부가가치세"
    assert body["final_tax"] == 4000000


def test_penalty_tax_no_filing_calculation(client, auth_cookie):
    resp = client.post(
        "/api/calculator/penalty-tax",
        json={"unpaid_tax": 10000000, "penalty_type": "무신고"},
        cookies=auth_cookie,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tax_type"] == "가산세"
    assert body["final_tax"] == 12000000
