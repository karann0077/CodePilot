import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup, with graceful fallback."""
    try:
        from app.database import Base, get_engine
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as exc:
        logger.error("Failed to initialize database: %s", exc)
        logger.warning("App will start without database — some endpoints may fail")
    yield


app = FastAPI(
    title="CodePilot API",
    version="1.0.0",
    description="AI-powered code intelligence platform",
    lifespan=lifespan,
)

settings = get_settings()
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
if not origins:
    origins = ["*"]
allow_all_origins = origins == ["*"]

logger.info("CORS allowed origins: %s", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers — imported lazily so the app starts even if optional deps are absent
# ---------------------------------------------------------------------------
try:
    from app.routers import repos, index, query, diagnose, patch, sandbox, docs

    app.include_router(repos.router, prefix="/api")
    app.include_router(index.router, prefix="/api")
    app.include_router(query.router, prefix="/api")
    app.include_router(diagnose.router, prefix="/api")
    app.include_router(patch.router, prefix="/api")
    app.include_router(sandbox.router, prefix="/api")
    app.include_router(docs.router, prefix="/api")
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}


@app.get("/", tags=["system"])
def root():
    return {"message": "CodePilot API is running", "docs": "/docs"}
