import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.phone import normalize_phone
from app.models import AIConversation, Package, Tenant, User
from app.modules.ai_agent import llm, offline, tools
from app.modules.tenants import service as tenants

log = logging.getLogger("saturna.agent")
LIMIT_MSG = "Por ahora no puedo atender más consultas automáticas este mes. Acércate a ventanilla, por favor."
NO_PKG_MSG = "No encuentro paquetes asociados a tu número. Revisa que sea el mismo que dejaste en la paquetería."


def resolve_context(db: Session, phone: str, tenant_scope: int | None) -> tuple[tools.Ctx, Tenant | None]:
    """Identifica quién escribe: personal de una paquetería o comprador (por su teléfono)."""
    user = db.scalar(select(User).where(User.phone == phone, User.active.is_(True)))
    if user and (tenant_scope is None or user.tenant_id == tenant_scope):
        ctx = tools.Ctx(db=db, phone=phone, role=user.role, tenant_id=user.tenant_id, user_id=user.id)
        return ctx, db.get(Tenant, user.tenant_id)
    ctx = tools.Ctx(db=db, phone=phone, role="buyer", tenant_scope=tenant_scope)
    stmt = select(Package.tenant_id).where(Package.buyer_phone == phone).order_by(Package.id.desc())
    if tenant_scope:
        stmt = stmt.where(Package.tenant_id == tenant_scope)
    tid = db.scalar(stmt)
    return ctx, (db.get(Tenant, tid) if tid else None)


def handle_message(db: Session, raw_phone: str, text: str, tenant_scope: int | None = None) -> dict:
    try:
        phone = normalize_phone(raw_phone)
    except ValueError:
        return {"reply": "Número inválido.", "outbox": [], "role": "buyer", "tools": [], "mode": "offline"}
    ctx, tenant = resolve_context(db, phone, tenant_scope)
    if tenant is None:
        return {"reply": NO_PKG_MSG, "outbox": [], "role": ctx.role, "tools": [], "mode": "offline"}
    if tenants.limit_reached(db, tenant, "ai_queries"):
        db.commit()
        return {"reply": LIMIT_MSG, "outbox": [], "role": ctx.role, "tools": [], "mode": "offline"}

    used: list[str] = []
    mode = "offline"
    try:
        if get_settings().llm_api_key:
            reply, used = llm.run(ctx, text)
            mode = "llm"
        else:
            reply, used = offline.respond(ctx, text)
    except Exception as exc:  # si el LLM falla, se responde con el agente por reglas
        log.error("Fallo del LLM; usando agente offline: %s", str(exc)[:300])
        reply, used = offline.respond(ctx, text)
        mode = "offline"
    reply = reply or "No pude entender tu consulta. ¿Me envías el código de tu paquete (SAT-XXXXXX)?"

    tenants.increment(db, tenant.id, "ai_queries")
    db.add(AIConversation(tenant_id=tenant.id, phone=phone, role=ctx.role, user_message=text,
                          reply=reply, tools_used=used))
    db.commit()
    return {"reply": reply, "outbox": ctx.outbox, "role": ctx.role, "tools": used, "mode": mode}
