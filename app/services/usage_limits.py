"""Daily question limits: each answer costs paid model calls, so a shared link must not run up the bill.

Every accepted question or regeneration is recorded in chat_usage before the answer starts, so a
stopped or failed answer still counts (its model calls were already paid for). The day is the
Korean calendar day. A limit of 0 means no limit.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import config

KST = ZoneInfo("Asia/Seoul")


def day_start(now: datetime | None = None) -> datetime:
    now = (now or datetime.now(KST)).astimezone(KST)
    return datetime.combine(now.date(), time.min, tzinfo=KST)


async def reserve_question(conn, user_id, kind: str, *, now: datetime | None = None) -> None:
    """Record one question for today, or refuse with 429 when a daily limit is reached."""
    per_user, total = config.CHAT_DAILY_LIMIT_PER_USER, config.CHAT_DAILY_LIMIT_TOTAL
    since = day_start(now)
    async with conn.transaction():
        # One reservation at a time, so two tabs cannot both take the last question.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('chat_usage'))")
        if per_user:
            used = await conn.fetchval(
                "SELECT count(*) FROM chat_usage WHERE user_id = $1 AND created_at >= $2", user_id, since)
            if used >= per_user:
                raise HTTPException(status_code=429, detail={
                    "code": "daily_question_limit",
                    "message": f"오늘 질문 한도({per_user}회)를 모두 사용했습니다. 내일 다시 이용해 주세요."})
        if total:
            used_all = await conn.fetchval("SELECT count(*) FROM chat_usage WHERE created_at >= $1", since)
            if used_all >= total:
                raise HTTPException(status_code=429, detail={
                    "code": "daily_service_limit",
                    "message": "오늘 서비스 전체 질문 한도에 도달했습니다. 내일 다시 이용해 주세요."})
        await conn.execute("INSERT INTO chat_usage (user_id, kind) VALUES ($1, $2)", user_id, kind)
