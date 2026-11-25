import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["WHATSAPP_TOKEN"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["WHATSAPP_APP_SECRET"] = ""
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET"] = "saturna-test-secret-32-bytes-minimo"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.ratelimit import reset_rate_limits  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Tenant  # noqa: E402
from app.modules.notifications import whatsapp  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    reset_rate_limits()
    whatsapp.SENT_LOG.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s


def make_tenant(client, name="Paquetería Sol", email="a@sol.com", plan="free", phone=None):
    r = client.post("/auth/register", json={
        "tenant_name": name, "name": "Dueño", "email": email, "password": "clave12345",
        "phone": phone, "zone": "La Paz"})
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    if plan != "free":
        with SessionLocal() as s:
            tid = client.get("/tenants/me", headers=headers).json()["id"]
            s.get(Tenant, tid).plan = plan
            s.commit()
    return headers


def new_package(client, headers, phone="71234567", name="Ana"):
    r = client.post("/packages", headers=headers, json={"buyer_phone": phone, "buyer_name": name,
                                                        "sender": "Tienda X", "description": "Caja"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def owner(client):
    return make_tenant(client)
