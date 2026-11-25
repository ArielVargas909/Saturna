from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Tenant, User

bearer = HTTPBearer(auto_error=False)
DB = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> User:
    if cred is None:
        raise HTTPException(401, "Falta el token de acceso")
    user_id = decode_token(cred.credentials, "access")
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.active:
        raise HTTPException(401, "Sesión inválida o expirada")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_owner(user: CurrentUser) -> User:
    if user.role != "owner":
        raise HTTPException(403, "Solo el propietario puede hacer esto")
    return user


Owner = Annotated[User, Depends(require_owner)]


def get_tenant(db: DB, user: CurrentUser) -> Tenant:
    """Dependencia común: el tenant sale SIEMPRE del usuario autenticado, nunca del cliente."""
    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != "active":
        raise HTTPException(403, "Paquetería inactiva")
    return tenant


CurrentTenant = Annotated[Tenant, Depends(get_tenant)]
