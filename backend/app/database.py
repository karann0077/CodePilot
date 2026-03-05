from collections.abc import Generator
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def get_engine():
    """Lazily create and cache the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url
        # Log host only (no credentials)
        host_part = db_url.split("@")[-1] if "@" in db_url else "configured-host"
        logger.info("Creating database engine for host: %s", host_part)
        _engine = create_engine(
            db_url,
            pool_pre_ping=True,
            # Conservative pool settings suitable for Render's free tier
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def _get_session_factory() -> sessionmaker:
    """Lazily create and cache the sessionmaker."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


class _LazyEngine:
    """Proxy that defers engine creation until first use."""
    def __getattr__(self, name):
        return getattr(get_engine(), name)

    def __repr__(self):
        return repr(get_engine())


class _LazySessionLocal:
    """Proxy that defers sessionmaker creation until first use."""
    def __call__(self, *args, **kwargs):
        return _get_session_factory()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(_get_session_factory(), name)


engine = _LazyEngine()
SessionLocal = _LazySessionLocal()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
