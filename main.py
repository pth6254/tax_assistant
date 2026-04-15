"""
main.py — 앱 진입점

FastAPI 백엔드 실행:
    uvicorn main:app --reload --port 8000

React 프론트엔드 실행:
    cd frontend
    npm run dev
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import close_pool, get_pool
from app.routers import auth, chat, upload
from app.utils.embeddings import close_http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await get_pool()
    print("✅ PostgreSQL 커넥션 풀 생성 완료")
    print(f"🤖 LLM: Ollama qwen3.5:35b-a3b")
    print(f"🔢 임베딩: Ollama qwen3-embedding:4b (2560차원)")
    yield
    # shutdown
    await close_pool()
    await close_http_client()
    print("🔌 종료 완료")


app = FastAPI(
    title="세무 자동화 어시스턴트 API",
    version="6.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(chat.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)