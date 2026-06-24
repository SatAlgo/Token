"""SQLite engine + a tiny helper to get a DB session in route handlers."""
from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# check_same_thread=False is required because FastAPI may use the connection
# from different threads. SQLite is perfect for a single-shop pilot.
engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Importing models here guarantees the tables are registered before create_all.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
