from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DB, CurrentTenant, CurrentUser
from app.models import AIConversation
from app.modules.ai_agent import service
from app.schemas import SimulateIn

router = APIRouter(prefix="/agent", tags=["ai"])


@router.post("/simulate")
def simulate(data: SimulateIn, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """Simulador de WhatsApp para probar el agente. Está limitado al tenant del usuario y
    nunca envía mensajes reales."""
    return service.handle_message(db, data.phone, data.message, tenant_scope=tenant.id)


@router.get("/conversations")
def conversations(db: DB, tenant: CurrentTenant, limit: int = 30):
    rows = db.scalars(
        select(AIConversation).where(AIConversation.tenant_id == tenant.id)
        .order_by(AIConversation.id.desc()).limit(min(limit, 100))
    ).all()
    return [{"id": c.id, "role": c.role, "user_message": c.user_message, "reply": c.reply,
             "tools_used": c.tools_used, "created_at": c.created_at} for c in rows]
