import asyncio
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.session import engine
from app.models.base import Base
from app.models.notice_board import NoticeBoardPost, NoticeResponse


async def init_tables():
    print("Creating NoticeBoardPost and NoticeResponse tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Phase 10 tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_tables())
