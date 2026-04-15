"""
main.py — 앱 진입점
라우터 등록과 앱 생명주기(startup/shutdown)만 담당합니다.
실제 비즈니스 로직은 routers / services / utils 레이어에 있습니다.

실행:
  uvicorn main:app --reload --port 8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.database import close_pool, get_pool
from app.routers import auth, chat, upload

app = FastAPI(title="세무 자동화 어시스턴트 API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(chat.router)

# ── 앱 생명주기 ────────────────────────────────────────────────
@app.on_event("startup")
async def startup() -> None:
    await get_pool()
    print("✅ PostgreSQL 커넥션 풀 생성 완료")


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_pool()
    print("🔌 PostgreSQL 커넥션 풀 종료")


# ── 프론트엔드 서빙 ────────────────────────────────────────────
_HTML_FILE = Path(__file__).parent / "tax_chatbot.html"


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if not _HTML_FILE.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="tax_chatbot.html 파일을 찾을 수 없습니다.")
    return HTMLResponse(_HTML_FILE.read_text(encoding="utf-8"))


# ── 개발 서버 직접 실행 ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
