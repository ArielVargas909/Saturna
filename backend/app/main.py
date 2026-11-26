import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.modules.ai_agent.router import router as agent_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.notifications.router import router as notif_router
from app.modules.notifications.service import dispatch_due_scheduled_qrs
from app.modules.packages.router import router as packages_router
from app.modules.payments.router import router as payments_router
from app.modules.qr.router import router as qr_router
from app.modules.tenants.router import router as tenants_router

settings = get_settings()
log = logging.getLogger("saturna.main")


async def _scheduled_qr_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(dispatch_due_scheduled_qrs)
        except Exception as exc:
            log.error("Error en planificador de QR programados: %s", str(exc)[:200])
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url.startswith("sqlite"):  # desarrollo rápido sin Docker
        Base.metadata.create_all(engine)
    task = asyncio.create_task(_scheduled_qr_loop()) if settings.environment != "test" else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    description="Saturna: gestión inteligente, aviso IA y QR de seguridad para paqueterías.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth_router, tenants_router, packages_router, qr_router, payments_router,
          notif_router, analytics_router, agent_router):
    app.include_router(r)


@app.get("/health", tags=["meta"])
def health(bg: BackgroundTasks):
    if settings.environment != "test":
        bg.add_task(dispatch_due_scheduled_qrs)
    return {"status": "ok"}
