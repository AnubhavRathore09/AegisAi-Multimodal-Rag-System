from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

import asyncio
from src.config import settings
from src.routes.auth import router as auth_router
from src.routes.chat import router as chat_router
from src.routes.upload import router as upload_router
from src.routes.compat import router as compat_router
from src.services.logging_service import app_logger
from src.services.llm import llm_service
from src.services.web_search import tavily_healthcheck

from pathlib import Path
import time
import uuid

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.cors_origins != ["*"] else [
        "https://aegis-ai-multimodal-rag-system.vercel.app",
        "https://aegis-ai-multimodal-rag-system-oxg1vluip.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(compat_router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"


@app.on_event("startup")
async def startup_event() -> None:
    message = f"Loaded model: {settings.model_name}"
    print(message)
    print("RUNTIME_MAIN_FILE", __file__, flush=True)
    try:
        from src.services import rag as rag_module
        from src.routes import chat as chat_module
        print("RUNTIME_RAG_FILE", rag_module.__file__, flush=True)
        print("RUNTIME_CHAT_ROUTE_FILE", chat_module.__file__, flush=True)
    except Exception as exc:
        print("RUNTIME_MODULE_PROBE_FAILED", str(exc), flush=True)
    tavily_ok = await asyncio.to_thread(tavily_healthcheck)
    if tavily_ok:
        print("TAVILY_HEALTHCHECK_OK", flush=True)
    else:
        print("TAVILY_HEALTHCHECK_FAILED", flush=True)
    gemini_ok = await llm_service.healthcheck_async()
    if gemini_ok:
        print("GEMINI_HEALTHCHECK_OK", flush=True)
    else:
        print("GEMINI_HEALTHCHECK_FAILED", flush=True)
    await asyncio.to_thread(
        app_logger.log,
        "startup",
        provider="gemini",
        model=settings.model_name,
        base_url=settings.gemini_base_url,
        message=message,
    )

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
        "app": settings.app_name,
        "provider": "gemini",
        "model": settings.model_name,
    }


@app.get("/")
async def root():
    try:
        return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return HTMLResponse(
            "<h2>AegisAI Running</h2><p>Open /frontend/index.html</p>"
        )


@app.get("/frontend")
async def frontend_root():
    return RedirectResponse(url="/frontend/index.html", status_code=307)


@app.get("/frontend/{asset_path:path}")
async def frontend_asset(asset_path: str):
    safe_path = (FRONTEND_DIR / asset_path).resolve()
    if not str(safe_path).startswith(str(FRONTEND_DIR.resolve())):
      return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if not safe_path.exists() or not safe_path.is_file():
      return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if safe_path.suffix.lower() == ".html":
      return HTMLResponse(safe_path.read_text(encoding="utf-8"))
    return FileResponse(safe_path)


@app.get("/frontend/index.html", include_in_schema=False)
async def frontend_index():
    try:
        return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"detail": "Frontend index.html not found"})
