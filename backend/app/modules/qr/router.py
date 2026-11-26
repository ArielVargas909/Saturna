from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from app.core.deps import DB, CurrentTenant, CurrentUser
from app.core.ratelimit import check_rate
from app.modules.notifications import service as notif_service
from app.modules.notifications.service import send_pickup_ready_task
from app.modules.packages import service as pkgs
from app.modules.qr import service
from app.schemas import ConfirmIn, PackageOut, QRIssued, QRSentOut, TokenIn, ValidateOut

router = APIRouter(tags=["qr"])


@router.post("/packages/{package_id}/qr", response_model=QRIssued)
def issue_qr(package_id: int, bg: BackgroundTasks, db: DB, tenant: CurrentTenant, user: CurrentUser):
    pkg = pkgs.get_owned(db, tenant.id, package_id)
    token, expires = service.issue_token(db, tenant, pkg, user.id)
    bg.add_task(send_pickup_ready_task, pkg.id, user.id, token, expires)
    return QRIssued(token=token, expires_at=expires, image=service.qr_data_uri(token))


@router.post("/packages/{package_id}/send-qr", response_model=QRSentOut)
def send_qr_to_client(package_id: int, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """Emite un QR de un solo uso y lo envía de inmediato al WhatsApp del cliente."""
    pkg = pkgs.get_owned(db, tenant.id, package_id)
    if pkg.state in ("ENTREGADO", "DEVUELTO", "VENCIDO"):
        raise HTTPException(409, "El paquete ya está cerrado")
    token, expires = service.issue_token(db, tenant, pkg, user.id)
    note = notif_service.send_qr_to_buyer(db, pkg, tenant, user.id, token, expires)
    if note.status == "failed":
        raise HTTPException(502, f"No se pudo enviar el QR al cliente: {note.detail}")
    return QRSentOut(
        token=token,
        expires_at=expires,
        image=service.qr_data_uri(token),
        status=note.status,
        detail=note.detail,
    )


@router.post("/qr/validate", response_model=ValidateOut)
def validate_qr(data: TokenIn, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """Verifica el token escaneado SIN consumirlo."""
    check_rate(f"qr:{user.id}", 40)  # evita adivinación de tokens
    qr, pkg = service.lookup(db, tenant.id, data.token)
    return ValidateOut(
        package=PackageOut.model_validate(pkg),
        fees=pkgs.compute_fees(tenant, pkg),
        expires_at=qr.expires_at,
    )


@router.post("/qr/confirm", response_model=PackageOut)
def confirm_qr(data: ConfirmIn, db: DB, tenant: CurrentTenant, user: CurrentUser):
    """Confirma la entrega (tras cobrar) y consume el token de forma atómica."""
    check_rate(f"qr:{user.id}", 40)
    return service.confirm_delivery(db, tenant, user.id, data.token, data.payment_method, data.amount)


@router.get("/qr/image/{token}.png")
def qr_image(token: str):
    """Imagen PNG del QR (la usa WhatsApp para enviar la imagen). El token ya es el secreto."""
    return Response(service.qr_png_bytes(token), media_type="image/png")
