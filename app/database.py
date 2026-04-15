"""
database.py — PostgreSQL 커넥션 풀 단독 관리
앱 전역에서 get_pool()로 풀을 가져다 씁니다.
"""
from typing import Optional

import asyncpg
from pgvector.asyncpg import register_vector

from config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """싱글턴 커넥션 풀 반환. 없으면 생성."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            init=register_vector,
        )
    return _pool


async def close_pool() -> None:
    """앱 종료 시 커넥션 풀 정리."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
