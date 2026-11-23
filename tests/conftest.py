import os
import sys
from pathlib import Path
import pytest
import pytest_asyncio

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.session import AsyncSessionLocal, engine
from app.models.base import Base


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Provides a transactional AsyncSession for tests."""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()
