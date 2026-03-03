from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import DATA_DIR
from backend.app.database import engine
from backend.app.models import Base
from backend.app.queue import close_redis
from backend.app.routes.jobs import router as jobs_router
from backend.app.routes.voice import router as voice_router

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="Spreadsheet Analysis Service",
    version="0.1.0",
    description="Upload a spreadsheet, ask questions, get answers with charts.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)
app.include_router(voice_router)

# Serve job artifacts (charts, outputs) at /files/jobs/{job_id}/...
app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")
