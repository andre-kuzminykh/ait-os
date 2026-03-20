"""Database setup and session management."""

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import DATABASE_URL

# Ensure data directory exists for SQLite
if DATABASE_URL.startswith("sqlite"):
    db_path = DATABASE_URL.split("///")[-1]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Create all tables and apply lightweight migrations."""
    from bot.models import Base  # noqa: F811
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migrations for columns added after initial schema
        await _add_column_if_missing(conn, "published_pages", "pdf_path", "VARCHAR(500)")


async def _add_column_if_missing(conn, table: str, column: str, col_type: str):
    """Add a column to an existing table, ignoring if it already exists."""
    from sqlalchemy import text
    try:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
    except Exception:
        pass  # Column already exists


async def get_session() -> AsyncSession:
    """Get a new database session."""
    async with async_session() as session:
        yield session
