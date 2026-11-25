from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.modules.ai_agent.router import router as agent_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.notifications.router import router as notif_router
from app.modules.packages.router import router as packages_router
from app.modules.payments.router import router as payments_router
from app.modules.qr.router import router as qr_router
from app.modules.tenants.router import router as tenants_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.database_url.startswith("sqlite"):  # desarrollo rápido sin Docker
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan,
              description="Saturna: gestión inteligente, aviso IA y QR de seguridad para paqueterías.")
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
def health():
    return {"status": "ok"}
