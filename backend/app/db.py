from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config
from .models import Base

engine = create_engine(config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# create_all only creates missing *tables*, so a column added to a model after a
# database file already exists has to be added by hand. Each entry is
# (table, column, column DDL); the DDL needs a default so existing rows stay valid.
_COLUMN_MIGRATIONS = [
    ("extracted_fields", "original_value", "VARCHAR NOT NULL DEFAULT ''"),
]


def _apply_column_migrations() -> None:
    with engine.begin() as conn:
        for table, column, ddl in _COLUMN_MIGRATIONS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    Base.metadata.create_all(engine)
    _apply_column_migrations()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
