from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")
_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
_pool_opts = {} if _is_sqlite else {"pool_recycle": 300}
engine = create_engine(settings.database_url, connect_args=_args, pool_pre_ping=True, **_pool_opts)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
