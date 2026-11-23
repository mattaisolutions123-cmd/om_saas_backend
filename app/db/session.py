import asyncio
import ssl
from typing import AsyncGenerator
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from app.core.config import settings

class Base(DeclarativeBase):
    pass

database_url = settings.DATABASE_URL
engine = None
AsyncSessionLocal = None
is_async_native = False

if "postgresql" in database_url:
    # 1. Attempt standard asyncpg engine first (production / Linux / Docker / Render)
    async_db_url = database_url
    if not async_db_url.startswith("postgresql+asyncpg://"):
        async_db_url = async_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    connect_args = {}
    if "sslmode=require" in async_db_url:
        async_db_url = async_db_url.replace("sslmode=require", "ssl=require")

    if "ssl=require" in async_db_url:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx
        async_db_url = async_db_url.replace("?ssl=require", "").replace("&ssl=require", "")

    # Strip parameters unsupported by asyncpg like channel_binding
    if "channel_binding=" in async_db_url:
        import re
        async_db_url = re.sub(r"[?&]channel_binding=[^&]*", "", async_db_url)

    try:
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        engine = create_async_engine(
            async_db_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
            connect_args=connect_args,
        )
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        is_async_native = True
    except (ImportError, Exception) as e:
        # Fallback to pure-Python pg8000 on Windows environments where asyncpg binary is restricted
        parsed = urlparse(database_url)
        sync_url = f"postgresql+pg8000://{parsed.username}:{parsed.password}@{parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}"
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        sync_engine = create_engine(
            sync_url,
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
            connect_args={"ssl_context": ctx},
        )
        engine = sync_engine
        SyncSessionLocal = sessionmaker(
            bind=sync_engine,
            class_=Session,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

        class AsyncSessionProxy:
            def __init__(self, sync_session):
                self._sync = sync_session

            async def execute(self, statement, parameters=None, execution_options=None):
                return await asyncio.to_thread(
                    self._sync.execute,
                    statement,
                    parameters,
                    execution_options=execution_options,
                )

            async def commit(self):
                return await asyncio.to_thread(self._sync.commit)

            async def rollback(self):
                return await asyncio.to_thread(self._sync.rollback)

            async def flush(self, objects=None):
                return await asyncio.to_thread(self._sync.flush, objects)

            async def refresh(self, instance, attribute_names=None, with_for_update=None):
                return await asyncio.to_thread(
                    self._sync.refresh,
                    instance,
                    attribute_names=attribute_names,
                    with_for_update=with_for_update,
                )

            def add(self, instance, _warn=True):
                self._sync.add(instance, _warn=_warn)

            def add_all(self, instances):
                self._sync.add_all(instances)

            async def delete(self, instance):
                return await asyncio.to_thread(self._sync.delete, instance)

            async def scalar(self, statement, parameters=None, execution_options=None):
                res = await self.execute(statement, parameters, execution_options=execution_options)
                return res.scalar()

            async def scalars(self, statement, parameters=None, execution_options=None):
                res = await self.execute(statement, parameters, execution_options=execution_options)
                return res.scalars()

            async def close(self):
                return await asyncio.to_thread(self._sync.close)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                if exc_type is not None:
                    await self.rollback()
                await self.close()

        def make_async_session():
            return AsyncSessionProxy(SyncSessionLocal())

        AsyncSessionLocal = make_async_session
        is_async_native = False

else:
    # SQLite configuration for tests
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    engine = create_async_engine(
        database_url,
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    is_async_native = True


async def get_db() -> AsyncGenerator:
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()
