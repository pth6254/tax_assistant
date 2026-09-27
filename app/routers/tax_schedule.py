"""
routers/tax_schedule.py — 세무 일정 조회 엔드포인트
GET /api/tax-schedule  로그인 사용자의 사업자 유형 기준 다가오는 신고·납부 기한 목록
"""
from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.tax_schedule import TaxScheduleResponse
from app.services import auth_service
from app.services.tax_schedule_service import compute_upcoming_deadlines
from app.services.official_tax_calendar import CalendarUnavailable, get_official_month
from app.services import personal_tax_calendar_service as personal
from app.core.security import verify_token

router = APIRouter(prefix="/api/tax-schedule", tags=["tax-schedule"])


class WatchEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due_date: date
    title: str = Field(min_length=1, max_length=300)


class EventStatus(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['watching', 'preparing', 'done', 'not_applicable']


@router.get('/personal')
async def personal_events(year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
                          month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
                          user: dict = Depends(verify_token)):
    return await personal.list_events(user['id'], year, month)


@router.get('/personal/upcoming')
async def upcoming_personal_events(user: dict = Depends(verify_token)):
    return await personal.list_events(user['id'], upcoming=True)


@router.post('/personal', status_code=201)
async def watch_official_event(body: WatchEvent, user: dict = Depends(verify_token)):
    return await personal.watch_event(user['id'], body.due_date, body.title)


@router.patch('/personal/{event_id}')
async def update_personal_event(event_id: str, body: EventStatus,
                                user: dict = Depends(verify_token)):
    return await personal.set_status(user['id'], event_id, body.status)


@router.delete('/personal/{event_id}')
async def delete_personal_event(event_id: str, user: dict = Depends(verify_token)):
    return await personal.remove_event(user['id'], event_id)


@router.get("/official")
async def get_official_tax_calendar(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    refresh: bool = False,
    user: dict = Depends(verify_token),
):
    if year > date.today().year + 1:
        raise HTTPException(status_code=422, detail="다음 연도까지만 조회할 수 있습니다.")
    try:
        return await get_official_month(year, month, refresh=refresh)
    except CalendarUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=TaxScheduleResponse)
async def get_tax_schedule(user: dict = Depends(verify_token)):
    profile = await auth_service.get_me(user["id"])
    business_type = profile["business_type"]
    deadlines = compute_upcoming_deadlines(business_type)
    return TaxScheduleResponse(
        business_type=business_type,
        items=[
            {
                "tax_type": d.tax_type,
                "label":    d.label,
                "due_date": d.due_date.isoformat(),
                "d_day":    d.d_day,
            }
            for d in deadlines
        ],
    )
