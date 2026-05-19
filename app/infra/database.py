from typing import AsyncGenerator
from fastapi import Request
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Declarative base class for models
Base = declarative_base()

def init_db_engine(database_url: str):
    """
    Creates and returns the async SQLAlchemy engine.
    This should be loaded during the application lifespan and disposed of on shutdown (Standard 3).
    """
    return create_async_engine(
        database_url,
        echo=False,  # Set to True in dev if query logging is needed
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection provider for database sessions (Standard 2).
    Gets the shared engine from request.app.state.db_engine, spawns an AsyncSession,
    and yields it to the route handler. Ensures clean session teardown.
    """
    engine = getattr(request.app.state, "db_engine", None)
    if engine is None:
        raise RuntimeError("Database engine has not been initialized in application lifespan state.")

    # Create the session maker bound to the lifespan engine
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
