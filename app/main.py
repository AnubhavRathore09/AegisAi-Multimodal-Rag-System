from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routes.chat import router as chat_router
from app.routes.compat import router as compat_router
from app.routes.upload import router as upload_router
from app.services.logging_service import app_logger
from app.services.rate_limiter import rate_limiter

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(compat_router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.middleware("http")
async def production_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    path = request.url.path
    client_ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()

    if path.startswith("/api") and path not in {"/api/health"}:
        allowed, retry_after = await rate_limiter.allow(client_ip)
        if not allowed:
            payload = {"detail": "Rate limit exceeded", "retry_after": retry_after, "request_id": request_id}
            try:
                app_logger.log(
                    "rate_limit",
                    request_id=request_id,
                    path=path,
                    client_ip=client_ip,
                    retry_after=retry_after,
                )
            except Exception:
                pass
            return JSONResponse(
                status_code=429,
                content=payload,
                headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
            )

    try:
        response = await call_next(request)
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            app_logger.log(
                "request_error",
                request_id=request_id,
                method=request.method,
                path=path,
                client_ip=client_ip,
                latency_ms=latency_ms,
                error=str(exc),
            )
        except Exception:
            pass
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )

    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    try:
        app_logger.log(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=path,
            status_code=response.status_code,
            client_ip=client_ip,
            latency_ms=latency_ms,
        )
    except Exception:
        pass
    return response


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "default_model": settings.groq_model,
        "available_models": settings.available_models,
        "role_modes": settings.role_modes,
    }


@app.get("/")
async def root() -> HTMLResponse:
    try:
        return HTMLResponse(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return HTMLResponse(
            "<!doctype html><html><head><meta charset='utf-8'><title>AegisAI</title></head>"
            "<body style='font-family:sans-serif;padding:24px;background:#0b0d12;color:#eef2ff'>"
            "<h2>AegisAI</h2><p>The frontend could not be loaded from the root route.</p>"
            "<p>Open <a href='/frontend/index.html' style='color:#7bb0ff'>/frontend/index.html</a>.</p>"
            "</body></html>",
            status_code=200,
        )

