import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.phone import normalize_phone
from app.core.text import title_name
from app.models import AIConversation, Package, Tenant, User
from app.modules.ai_agent import llm, offline, tools
from app.modules.tenants import service as tenants

log = logging.getLogger("saturna.agent")
LIMIT_MSG = "Por ahora no puedo atender más consultas automáticas este mes. Acércate a ventanilla, por favor."
NO_PKG_MSG = "No encuentro paquetes asociados a tu número. Revisa que sea el mismo que dejaste en la paquetería."
MEMORY_TURNS = 6


def resolve_context(
    db: Session,
    phone: str,
    tenant_scope: int | None,
    text: str = "",
) -> tuple[tools.Ctx, Tenant | None]:
    """Identifica quién escribe: personal de una paquetería o comprador (por su teléfono y código)."""
    user = db.scalar(select(User).where(User.phone == phone, User.active.is_(True)))
    if user and (tenant_scope is None or user.tenant_id == tenant_scope):
        ctx = tools.Ctx(db=db, phone=phone, role=user.role, tenant_id=user.tenant_id, user_id=user.id)
        return ctx, db.get(Tenant, user.tenant_id)

    tid: int | None = None
    match = offline.CODE.search(text or "")
    if match:
        code = match.group(0).upper()
        code_stmt = select(Package.tenant_id).where(Package.buyer_phone == phone, Package.code == code)
        if tenant_scope:
            code_stmt = code_stmt.where(Package.tenant_id == tenant_scope)
        tid = db.scalar(code_stmt)

    if tid is None:
        stmt = select(Package.tenant_id).where(Package.buyer_phone == phone).order_by(Package.id.desc())
        if tenant_scope:
            stmt = stmt.where(Package.tenant_id == tenant_scope)
        tid = db.scalar(stmt)

    effective_scope = tenant_scope or tid
    ctx = tools.Ctx(db=db, phone=phone, role="buyer", tenant_scope=effective_scope)
    return ctx, (db.get(Tenant, tid) if tid else None)


def _recent_history(db: Session, tenant_id: int, phone: str) -> list[dict]:
    """Recupera los últimos turnos del chat (solo de ese tenant y teléfono) para memoria multi-turno."""
    rows = db.scalars(
        select(AIConversation)
        .where(AIConversation.tenant_id == tenant_id, AIConversation.phone == phone)
        .order_by(AIConversation.id.desc())
        .limit(MEMORY_TURNS)
    ).all()
    history: list[dict] = []
    for row in reversed(rows):
        if row.user_message:
            history.append({"role": "user", "content": row.user_message})
        if row.reply:
            history.append({"role": "assistant", "content": row.reply})
    return history


def _fallback_params(db: Session, ctx: tools.Ctx, tenant: Tenant) -> list[str] | None:
    if ctx.role != "buyer":
        return None
    pkg = db.get(Package, ctx.last_package_id) if ctx.last_package_id else None
    if pkg is None:
        pkg = db.scalar(
            select(Package)
            .where(Package.buyer_phone == ctx.phone, Package.tenant_id == tenant.id)
            .order_by(Package.id.desc())
        )
    if pkg is None:
        return None
    return [title_name(pkg.buyer_name) or "Cliente", pkg.code, tenant.name]


def handle_message(db: Session, raw_phone: str, text: str, tenant_scope: int | None = None) -> dict:
    try:
        phone = normalize_phone(raw_phone)
    except ValueError:
        return {
            "reply": "Número inválido.",
            "outbox": [],
            "role": "buyer",
            "tools": [],
            "mode": "offline",
            "tenant_id": None,
            "package_id": None,
            "fallback_params": None,
            "limit_reached": False,
        }

    ctx, tenant = resolve_context(db, phone, tenant_scope, text)
    if tenant is None:
        return {
            "reply": NO_PKG_MSG,
            "outbox": [],
            "role": ctx.role,
            "tools": [],
            "mode": "offline",
            "tenant_id": None,
            "package_id": None,
            "fallback_params": None,
            "limit_reached": False,
        }

    if tenants.limit_reached(db, tenant, "ai_queries"):
        db.add(
            AIConversation(
                tenant_id=tenant.id,
                phone=phone,
                role=ctx.role,
                user_message=text,
                reply=LIMIT_MSG,
                tools_used=[],
            )
        )
        db.commit()
        return {
            "reply": LIMIT_MSG,
            "outbox": [],
            "role": ctx.role,
            "tools": [],
            "mode": "offline",
            "tenant_id": tenant.id,
            "package_id": None,
            "fallback_params": _fallback_params(db, ctx, tenant),
            "limit_reached": True,
        }

    history = _recent_history(db, tenant.id, phone)
    used: list[str] = []
    mode = "offline"
    try:
        if get_settings().active_llm_api_key:
            reply, used = llm.run(ctx, text, history=history)
            mode = "llm"
        else:
            reply, used = offline.respond(ctx, text, history=history)
    except Exception as exc:  # si el LLM falla (red, 429/límite externo, etc.), responde el agente por reglas
        log.error("Fallo del LLM; usando agente offline: %s", str(exc)[:300])
        ctx.outbox.clear()
        reply, used = offline.respond(ctx, text, history=history)
        mode = "offline"

    reply = reply or "No pude entender tu consulta. ¿Me envías el código de tu paquete (SAT-XXXXXX)?"
    tenants.increment(db, tenant.id, "ai_queries")
    db.add(
        AIConversation(
            tenant_id=tenant.id,
            phone=phone,
            role=ctx.role,
            user_message=text,
            reply=reply,
            tools_used=used,
        )
    )
    db.commit()
    return {
        "reply": reply,
        "outbox": ctx.outbox,
        "role": ctx.role,
        "tools": used,
        "mode": mode,
        "tenant_id": tenant.id,
        "package_id": ctx.last_package_id,
        "fallback_params": _fallback_params(db, ctx, tenant),
        "limit_reached": False,
    }
