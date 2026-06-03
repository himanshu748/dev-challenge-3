from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.settings import get_settings
from app.services.hf_mcp import HFMCPService, HireIQError
from app.services.hireiq import HireIQService
from app.services.runtime_store import RuntimeStore


STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BODY_BYTES = 160_000


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    runtime_store = RuntimeStore(settings.runtime_state_path)
    hf_client = HFMCPService(settings)
    app.state.hireiq_service = HireIQService(
        settings=settings,
        hf_client=hf_client,
        runtime_store=runtime_store,
    )
    try:
        yield
    finally:
        await hf_client.close()


app = FastAPI(
    title="HireIQ",
    description="AI recruiting pipeline powered by HuggingFace and Notion MCP.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def reject_large_requests(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        try:
            body_size = int(content_length) if content_length else 0
        except ValueError:
            body_size = MAX_REQUEST_BODY_BYTES + 1
        if body_size > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body is too large."},
            )
    return await call_next(request)


@app.exception_handler(HireIQError)
async def hireiq_error_handler(_: Request, exc: HireIQError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, **exc.extra})


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
