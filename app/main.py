from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.chat import router as chat_router
from app.routes.upload import router as upload_router
from app.routes.compat import router as compat_router

from pathlib import Path
import time
import uuid

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://aegis-ai-multimodal-rag-system.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(compat_router)

app.include_router(chat_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(compat_router, prefix="/api")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"

app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.middleware("http")
async def middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    start = time.time()

    try:
        response = await call_next(request)
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "request_id": request_id},
        )

    process_time = round((time.time() - start) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    return response


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "app": settings.app_name
    }


@app.get("/")
async def root():
    try:
        return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return HTMLResponse(
            "<h2>AegisAI Running</h2><p>Open /frontend/index.html</p>"
        )