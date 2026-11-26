import base64
import hashlib
import secrets
import struct
import zlib
from datetime import timedelta
from decimal import Decimal

import segno
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import Package, Payment, QRToken, Tenant
from app.modules.packages import service as pkgs


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def qr_png_bytes(token: str, scale: int = 8, border: int = 4) -> bytes:
    """Genera un PNG RGB de 8 bits/canal (Meta WhatsApp rechaza PNGs de 1 bit con error 131053)."""
    matrix = segno.make(token, error="m").matrix
    size = len(matrix)
    total = (size + border * 2) * scale
    white_px = b"\xff\xff\xff"
    black_px = b"\x00\x00\x00"
    white_row = b"\x00" + white_px * total

    raw = bytearray()
    for _ in range(border * scale):
        raw.extend(white_row)
    for row in matrix:
        line = bytearray(b"\x00")
        line.extend(white_px * (border * scale))
        for cell in row:
            line.extend((black_px if cell else white_px) * scale)
        line.extend(white_px * (border * scale))
        for _ in range(scale):
            raw.extend(line)
    for _ in range(border * scale):
        raw.extend(white_row)

    ihdr = struct.pack(">IIBBBBB", total, total, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
        + _png_chunk(b"IEND", b"")
    )


def qr_data_uri(token: str) -> str:
    return "data:image/png;base64," + base64.b64encode(qr_png_bytes(token)).decode()


def issue_token(db: Session, tenant: Tenant, pkg: Package, user_id: int | None) -> tuple[str, object]:
    if pkg.state in ("ENTREGADO", "DEVUELTO"):
        raise HTTPException(409, "El paquete ya está cerrado")
    now = utcnow()
    # un solo QR vigente por paquete: se revocan los anteriores
    db.execute(
        update(QRToken)
        .where(QRToken.package_id == pkg.id, QRToken.used_at.is_(None), QRToken.expires_at > now)
        .values(expires_at=now)
    )
    token = secrets.token_urlsafe(32)  # valor opaco: no contiene datos del paquete
    expires = now + timedelta(hours=tenant.qr_ttl_hours)
    db.add(QRToken(package_id=pkg.id, token_hash=hash_token(token), expires_at=expires))
    if pkg.state != "LISTO_PARA_RETIRO":
        pkgs.change_state(db, pkg, "LISTO_PARA_RETIRO", user_id, "QR de retiro emitido")
    else:
        pkgs.add_event(db, pkg.id, "QR", "QR reemitido", user_id)
    db.commit()
    return token, expires


def lookup(db: Session, tenant_id: int, token: str) -> tuple[QRToken, Package]:
    row = db.execute(
        select(QRToken, Package)
        .join(Package, Package.id == QRToken.package_id)
        .where(QRToken.token_hash == hash_token(token), Package.tenant_id == tenant_id)
    ).first()
    if row is None:  # inexistente o de otra paquetería: misma respuesta
        raise HTTPException(404, "QR no válido")
    qr, pkg = row
    if qr.used_at is not None:
        raise HTTPException(409, "Este QR ya fue utilizado")
    if qr.expires_at <= utcnow():
        raise HTTPException(410, "Este QR expiró o fue reemplazado")
    return qr, pkg


def deliver_package(
    db: Session,
    tenant: Tenant,
    pkg: Package,
    user_id: int,
    *,
    method: str | None,
    amount: Decimal | None,
    via: str,
    identity_verified: bool = False,
    confirm_payment: bool = False,
    note: str = "",
) -> Package:
    if pkg.tenant_id != tenant.id:
        raise HTTPException(404, "Paquete no encontrado")
    if pkg.state in ("ENTREGADO", "DEVUELTO", "VENCIDO"):
        raise HTTPException(409, "El paquete ya está cerrado")

    fees = pkgs.compute_fees(tenant, pkg)
    paid_before = db.scalar(
        select(Payment.id).where(Payment.package_id == pkg.id, Payment.tenant_id == tenant.id)
    )
    if fees["total"] > 0:
        if method is None and paid_before is None:
            raise HTTPException(422, "Selecciona el método de pago")
        if not confirm_payment and paid_before is None:
            raise HTTPException(422, "Confirma que recibiste el pago")
    if via == "manual" and not identity_verified:
        raise HTTPException(422, "Verifica la identidad del comprador")
    if paid_before is not None and method is not None:
        raise HTTPException(409, "El paquete ya tiene un cobro registrado")

    now = utcnow()
    won = db.execute(
        update(Package)
        .where(
            Package.id == pkg.id,
            Package.tenant_id == tenant.id,
            Package.state.in_(pkgs.OPEN_STATES),
        )
        .values(state="ENTREGADO", delivered_at=now)
        .returning(Package.id)
    ).first()
    if won is None:
        db.rollback()
        raise HTTPException(409, "El paquete ya fue entregado o ya no está disponible")

    db.execute(
        update(QRToken)
        .where(QRToken.package_id == pkg.id, QRToken.used_at.is_(None))
        .values(used_at=now, used_by=user_id)
    )

    if method is not None:
        total = amount if amount is not None else fees["total"]
        db.add(
            Payment(
                tenant_id=tenant.id,
                package_id=pkg.id,
                amount=total,
                late_fee=fees["late"],
                method=method,
                registered_by=user_id,
            )
        )
        pkgs.add_event(db, pkg.id, "COBRO", f"Bs {total} ({method}) confirmado por el operador", user_id)

    event_type = "ENTREGA_MANUAL" if via == "manual" else "ENTREGA"
    detail = "Entrega manual confirmada"
    if note.strip():
        detail += f": {note.strip()}"
    pkgs.add_event(db, pkg.id, event_type, detail, user_id)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El paquete ya tiene un cobro registrado") from None
    db.refresh(pkg)
    return pkg


def confirm_delivery(
    db: Session,
    tenant: Tenant,
    user_id: int,
    token: str,
    method: str | None,
    amount: Decimal | None,
) -> Package:
    qr, pkg = lookup(db, tenant.id, token)
    fees = pkgs.compute_fees(tenant, pkg)
    paid_before = db.scalar(
        select(Payment.id).where(Payment.package_id == pkg.id, Payment.tenant_id == tenant.id)
    )
    if fees["total"] > 0 and method is None and paid_before is None:
        raise HTTPException(422, "Registra el cobro de la custodia (efectivo o QR) antes de entregar")
    return deliver_package(
        db,
        tenant,
        pkg,
        user_id,
        method=method,
        amount=amount,
        via="qr",
        confirm_payment=method is not None or paid_before is not None,
    )
