"""Async database engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import database_url

engine = create_async_engine(database_url(), echo=False, pool_pre_ping=True)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        yield session
