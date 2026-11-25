from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- auth / usuarios ----
class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class RegisterIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=120)
    address: str = ""
    zone: Literal["La Paz", "El Alto"] = "La Paz"
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    name: str
    email: str
    role: str
    phone: str | None
    active: bool
    tenant_id: int


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = None


# ---- tenant ----
class TenantOut(ORM):
    id: int
    name: str
    address: str
    zone: str
    plan: str
    custody_days: int
    qr_ttl_hours: int
    custody_fee: Decimal
    late_fee_per_day: Decimal
    opening_hours: str


class TenantUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=120)
    address: str | None = None
    zone: Literal["La Paz", "El Alto"] | None = None
    custody_days: int | None = Field(None, ge=1, le=60)
    qr_ttl_hours: int | None = Field(None, ge=1, le=168)
    custody_fee: Decimal | None = Field(None, ge=0, le=1000)
    late_fee_per_day: Decimal | None = Field(None, ge=0, le=1000)
    opening_hours: str | None = Field(None, max_length=120)


class PlanChange(BaseModel):
    plan: Literal["free", "basic", "premium"]


# ---- paquetes ----
class PackageCreate(BaseModel):
    buyer_phone: str = Field(min_length=7, max_length=20)
    buyer_name: str = Field("", max_length=120)
    sender: str = Field("", max_length=120)
    description: str = Field("", max_length=240)
    shelf_location: str = Field("", max_length=40)

    @field_validator("buyer_name", "sender", "description", "shelf_location", mode="before")
    @classmethod
    def normalize_upper_text(cls, value):
        if value is None:
            return value
        return " ".join(str(value).split()).upper()


class PackageUpdate(BaseModel):
    buyer_name: str | None = Field(None, max_length=120)
    sender: str | None = Field(None, max_length=120)
    description: str | None = Field(None, max_length=240)
    shelf_location: str | None = Field(None, max_length=40)

    @field_validator("buyer_name", "sender", "description", "shelf_location", mode="before")
    @classmethod
    def normalize_upper_text(cls, value):
        if value is None:
            return value
        return " ".join(str(value).split()).upper()


class PackageOut(ORM):
    id: int
    code: str
    buyer_phone: str
    buyer_name: str
    sender: str
    description: str
    state: str
    shelf_location: str
    received_at: datetime
    delivered_at: datetime | None
    custody_deadline: datetime


class EventOut(ORM):
    id: int
    type: str
    detail: str
    user_id: int | None
    created_at: datetime


class Fees(BaseModel):
    base: Decimal
    late: Decimal
    total: Decimal
    days_late: int


class PackageDetail(PackageOut):
    events: list[EventOut]
    fees: Fees


class PackageList(BaseModel):
    items: list[PackageOut]
    total: int


class StateChange(BaseModel):
    state: Literal["DEVUELTO", "VENCIDO", "NOTIFICADO", "LISTO_PARA_RETIRO"]
    detail: str = ""


# ---- QR ----
class QRIssued(BaseModel):
    token: str
    expires_at: datetime
    image: str  # data URI PNG


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class ConfirmIn(TokenIn):
    payment_method: Literal["cash", "qr"] | None = None
    amount: Decimal | None = Field(None, ge=0)


class ValidateOut(BaseModel):
    package: PackageOut
    fees: Fees
    expires_at: datetime


class DeliveryIn(BaseModel):
    metodo_pago: Literal["cash", "qr"] | None = None
    via: Literal["manual", "qr"]
    identidad_verificada: bool = False
    confirmo_pago: bool = False
    nota: str = ""


class DeliveryPreview(BaseModel):
    llegada: datetime
    dias_custodia: int
    custodia: Decimal
    recargo: Decimal
    total: Decimal


# ---- pagos ----
class PaymentCreate(BaseModel):
    package_id: int
    method: Literal["cash", "qr"]
    amount: Decimal | None = Field(None, ge=0)


class PaymentOut(ORM):
    id: int
    package_id: int
    amount: Decimal
    late_fee: Decimal
    method: str
    created_at: datetime


# ---- agente ----
class SimulateIn(BaseModel):
    phone: str = Field(min_length=7, max_length=20)
    message: str = Field(min_length=1, max_length=1000)
