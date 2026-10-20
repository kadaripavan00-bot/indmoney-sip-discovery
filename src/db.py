"""Database engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

_settings = settings()
_url = _settings["database_url"]
_connect_args = {"check_same_thread": False} if _url.startswith("sqlite") else {}

engine = create_engine(_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    if _url.startswith("sqlite:///"):
        db_path = Path(_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
