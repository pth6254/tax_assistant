"""
test_api_tax_schedule.py — 세무 일정 엔드포인트 테스트
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch


def test_tax_schedule_without_auth_returns_401(client):
    resp = client.get("/api/tax-schedule")
    assert resp.status_code == 401


def test_tax_schedule_returns_items_for_business_type(client, auth_cookie):
    profile = {
        "id": "u1", "email": "test@example.com", "name": "", "phone": "",
        "business_type": "법인", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with patch("app.routers.tax_schedule.auth_service.get_me", AsyncMock(return_value=profile)):
        resp = client.get("/api/tax-schedule", cookies=auth_cookie)
    assert resp.status_code == 200
    body = resp.json()
    assert body["business_type"] == "법인"
    assert len(body["items"]) == 6  # 부가세 4 + 종합소득세 1 + 원천세 1
    tax_types = {item["tax_type"] for item in body["items"]}
    assert tax_types == {"부가가치세", "종합소득세", "원천세"}


def test_tax_schedule_items_sorted_by_due_date(client, auth_cookie):
    profile = {
        "id": "u1", "email": "test@example.com", "name": "", "phone": "",
        "business_type": "개인_간이과세", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with patch("app.routers.tax_schedule.auth_service.get_me", AsyncMock(return_value=profile)):
        resp = client.get("/api/tax-schedule", cookies=auth_cookie)
    due_dates = [item["due_date"] for item in resp.json()["items"]]
    assert due_dates == sorted(due_dates)
