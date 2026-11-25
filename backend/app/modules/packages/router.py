from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.core.deps import DB, CurrentTenant, CurrentUser, Owner
from app.core.phone import normalize_phone
from app.modules.notifications.service import send_arrival_task
from app.modules.packages import service
from app.modules.qr import service as qr_service
from app.schemas import (
    DeliveryIn,
    DeliveryPreview,
    PackageCreate,
    PackageDetail,
    PackageList,
    PackageOut,
    PackageUpdate,
    StateChange,
)

router = APIRouter(prefix="/packages", tags=["packages"])


@router.get("/suggest-buyer")
def suggest_buyer(db: DB, tenant: CurrentTenant, phone: str = Query(...)):
    try:
        normalized = normalize_phone(phone)
    except ValueError:
        raise HTTPException(422, "Teléfono inválido") from None
    return {"items": service.suggest_buyer_names(db, tenant.id, normalized)}


@router.get("", response_model=PackageList)
def list_packages(
    db: DB,
    tenant: CurrentTenant,
    q: str | None = None,
    state: str | None = None,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    service.refresh_stale(db, tenant.id)
    items, total = service.search(db, tenant.id, q, state, limit, offset)
    return {"items": items, "total": total}


@router.post("", response_model=PackageOut, status_code=201)
def create_package(
    data: PackageCreate, bg: BackgroundTasks, db: DB, tenant: CurrentTenant, user: CurrentUser
):
    pkg = service.register_package(db, tenant, user.id, data)
    bg.add_task(send_arrival_task, pkg.id)  # el aviso NO bloquea el registro
    return pkg


@router.get("/{package_id}", response_model=PackageDetail)
def package_detail(package_id: int, db: DB, tenant: CurrentTenant):
    pkg = service.get_owned(db, tenant.id, package_id)
    return PackageDetail(
        **PackageOut.model_validate(pkg).model_dump(),
        events=list(pkg.events),
        fees=service.compute_fees(tenant, pkg),
    )


@router.patch("/{package_id}", response_model=PackageOut)
def update_package(
    package_id: int,
    data: PackageUpdate,
    db: DB,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    pkg = service.get_owned(db, tenant.id, package_id)
    return service.update_package(db, pkg, data, user.id)


@router.get("/{package_id}/deliver-preview", response_model=DeliveryPreview)
def deliver_preview(package_id: int, db: DB, tenant: CurrentTenant):
    pkg = service.get_owned(db, tenant.id, package_id)
    if pkg.state in ("ENTREGADO", "DEVUELTO", "VENCIDO"):
        raise HTTPException(409, "El paquete ya está cerrado")
    fees = service.compute_fees(tenant, pkg)
    return DeliveryPreview(
        llegada=pkg.received_at,
        dias_custodia=fees["days_late"],
        custodia=fees["base"],
        recargo=fees["late"],
        total=fees["total"],
    )


@router.post("/{package_id}/deliver", response_model=PackageOut)
def deliver_package(
    package_id: int,
    data: DeliveryIn,
    db: DB,
    tenant: CurrentTenant,
    user: CurrentUser,
):
    pkg = service.get_owned(db, tenant.id, package_id)
    if data.via == "manual" and not data.identidad_verificada:
        raise HTTPException(422, "Verifica la identidad del comprador")
    fees = service.compute_fees(tenant, pkg)
    if fees["total"] > 0 and not data.confirmo_pago:
        raise HTTPException(422, "Confirma que recibiste el pago")
    return qr_service.deliver_package(
        db,
        tenant,
        pkg,
        user.id,
        method=data.metodo_pago,
        amount=None,
        via=data.via,
        identity_verified=data.identidad_verificada,
        confirm_payment=data.confirmo_pago,
        note=data.nota,
    )


@router.post("/{package_id}/state", response_model=PackageOut)
def manual_state(package_id: int, data: StateChange, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """Cambios manuales (p. ej. devolver al remitente). ENTREGADO solo se logra con QR validado."""
    pkg = service.get_owned(db, tenant.id, package_id)
    service.change_state(db, pkg, data.state, user.id, data.detail)
    db.commit()
    return pkg


@router.post("/{package_id}/anonymize", response_model=PackageOut)
def anonymize(package_id: int, db: DB, tenant: CurrentTenant, owner: Owner):
    """Eliminación de datos personales del comprador (privacidad, sección 17)."""
    pkg = service.get_owned(db, tenant.id, package_id)
    if pkg.state not in ("ENTREGADO", "DEVUELTO", "VENCIDO"):
        raise HTTPException(409, "Solo se pueden anonimizar paquetes cerrados")
    pkg.buyer_name = "(eliminado)"
    pkg.buyer_phone = "0000000000"
    service.add_event(db, pkg.id, "PRIVACIDAD", "Datos personales eliminados", owner.id)
    db.commit()
    return pkg
