"""Modelo de datos (sección 5 de la guía). Todas las tablas de negocio llevan tenant_id."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import utcnow
from app.db.base import Base

MONEY = Numeric(10, 2)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str] = mapped_column(String(200), default="")
    zone: Mapped[str] = mapped_column(String(40), default="La Paz")  # La Paz | El Alto
    plan: Mapped[str] = mapped_column(String(20), default="free")
    status: Mapped[str] = mapped_column(String(20), default="active")
    # Configuración que define el propietario
    custody_days: Mapped[int] = mapped_column(Integer, default=5)
    qr_ttl_hours: Mapped[int] = mapped_column(Integer, default=24)
    custody_fee: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("5.00"))
    late_fee_per_day: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("2.00"))
    opening_hours: Mapped[str] = mapped_column(String(120), default="Lun-Sáb 09:00 a 19:00")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="operator")  # owner | operator
    phone: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    active: Mapped[bool] = mapped_column(default=True)


class Package(Base):
    __tablename__ = "packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    buyer_phone: Mapped[str] = mapped_column(String(20), index=True)
    buyer_name: Mapped[str] = mapped_column(String(120), default="")
    sender: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(String(240), default="")
    state: Mapped[str] = mapped_column(String(24), default="REGISTRADO", index=True)
    shelf_location: Mapped[str] = mapped_column(String(40), default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    custody_deadline: Mapped[datetime] = mapped_column(DateTime)
    events: Mapped[list["PackageEvent"]] = relationship(
        back_populates="package", order_by="PackageEvent.id", cascade="all, delete-orphan"
    )


class PackageEvent(Base):
    """Bitácora de auditoría."""

    __tablename__ = "package_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    package: Mapped[Package] = relationship(back_populates="events")


class QRToken(Base):
    """Solo se guarda el hash SHA-256 del token; el QR contiene el token opaco."""

    __tablename__ = "qr_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("package_id", name="uq_payments_package_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    late_fee: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    method: Mapped[str] = mapped_column(String(10))  # cash | qr
    registered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True)
    package_id: Mapped[int | None] = mapped_column(ForeignKey("packages.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued | sent | failed | simulated
    meta_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detail: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AIConversation(Base):
    __tablename__ = "ai_conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    phone: Mapped[str] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(12), default="buyer")
    user_message: Mapped[str] = mapped_column(Text)
    reply: Mapped[str] = mapped_column(Text)
    tools_used: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessedMessage(Base):
    __tablename__ = "processed_messages"
    message_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), primary_key=True)
    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM
    packages: Mapped[int] = mapped_column(Integer, default=0)
    notifications: Mapped[int] = mapped_column(Integer, default=0)
    ai_queries: Mapped[int] = mapped_column(Integer, default=0)
