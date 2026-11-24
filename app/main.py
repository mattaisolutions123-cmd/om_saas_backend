from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.core.config import settings
from app.db.session import get_db
from app.api.v1.auth import router as auth_router
from app.api.v1.audit import router as audit_router
from app.api.v1.settings import settings_router
from app.api.v1.clients import router as clients_router
from app.api.v1.services import router as services_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.suppliers import router as suppliers_router
from app.api.v1.procurement import router as procurement_router
from app.api.v1.tickets import router as tickets_router
from app.api.v1.sales import router as sales_router
from app.api.v1.cashbox import router as cashbox_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.public import router as public_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.automation import router as automation_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.reports import router as reports_router
from app.api.v1.notices import router as notices_router
from app.api.v1.uploads import router as uploads_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup tasks
    print(f"🚀 Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    try:
        import app.models  # Ensures all models are registered in Base.metadata
        from app.db.session import engine, is_async_native, Base
        if is_async_native and engine is not None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        elif engine is not None:
            Base.metadata.create_all(bind=engine)

        from app.scripts.seed_admin import seed_admin_user
        await seed_admin_user()
    except Exception as e:
        print(f"Startup bootstrap notice: {e}")
    yield
    # Shutdown tasks
    print("🛑 Shutting down OmniSuite backend...")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request performance & response header middleware
    @app.middleware("http")
    async def add_process_time_header(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = f"{process_time:.4f}s"
        return response

    # Routers
    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(audit_router, prefix=settings.API_V1_STR)
    app.include_router(settings_router, prefix=settings.API_V1_STR)
    app.include_router(clients_router, prefix=settings.API_V1_STR)
    app.include_router(services_router, prefix=settings.API_V1_STR)
    app.include_router(inventory_router, prefix=settings.API_V1_STR)
    app.include_router(suppliers_router, prefix=settings.API_V1_STR)
    app.include_router(procurement_router, prefix=settings.API_V1_STR)
    app.include_router(tickets_router, prefix=settings.API_V1_STR)
    app.include_router(sales_router, prefix=settings.API_V1_STR)
    app.include_router(cashbox_router, prefix=settings.API_V1_STR)
    app.include_router(tasks_router, prefix=settings.API_V1_STR)
    app.include_router(public_router, prefix="/public")
    app.include_router(public_router, prefix=f"{settings.API_V1_STR}/public")
    app.include_router(notifications_router, prefix=settings.API_V1_STR)
    app.include_router(automation_router, prefix=settings.API_V1_STR)
    app.include_router(campaigns_router, prefix=settings.API_V1_STR)
    app.include_router(analytics_router, prefix=settings.API_V1_STR)
    app.include_router(reports_router, prefix=settings.API_V1_STR)
    app.include_router(notices_router, prefix=settings.API_V1_STR)
    app.include_router(uploads_router, prefix=settings.API_V1_STR)

    @app.get("/", tags=["Health"])
    async def root_ping():
        return {
            "status": "online",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
        }

    @app.get("/health", tags=["Health"])
    @app.get(f"{settings.API_V1_STR}/health", tags=["Health"])
    async def health_check(db: AsyncSession = Depends(get_db)):
        try:
            start_t = time.time()
            res = await db.execute(text("SELECT 1"))
            latency_ms = (time.time() - start_t) * 1000
            val = res.scalar()
            db_status = "connected" if val == 1 else "unexpected_result"
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database health check failed: {str(e)}",
            )

        return {
            "status": "healthy",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "database": {
                "status": db_status,
                "latency_ms": round(latency_ms, 2),
            },
        }

    return app


app = create_app()
