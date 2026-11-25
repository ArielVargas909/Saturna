from tests.conftest import make_tenant, new_package
from datetime import datetime, timedelta

from app.db.session import SessionLocal
from app.models import Payment, Package
from app.core.timeutil import utcnow


def test_free_plan_package_limit(client, owner):
    for i in range(30):
        new_package(client, owner, phone=f"7{i:07d}")
    r = client.post("/packages", headers=owner, json={"buyer_phone": "79999999"})
    assert r.status_code == 402


def test_simulated_notifications_do_not_count_usage(client, owner):
    for i in range(31):
        if i < 30:
            new_package(client, owner, phone=f"7{i:07d}")
    usage = client.get("/tenants/me/usage", headers=owner).json()
    assert usage["notifications"]["used"] == 0


def test_operator_limit(client, owner):
    body = {"name": "Op Uno", "email": "op1@sol.com", "password": "clave12345"}
    assert client.post("/users", headers=owner, json=body).status_code == 201
    body["email"] = "op2@sol.com"
    assert client.post("/users", headers=owner, json=body).status_code == 402  # free = 1 operador


def test_analytics_gated_by_plan_in_backend(client, owner):
    assert client.get("/analytics/revenue?granularity=day", headers=owner).status_code == 403
    basic = make_tenant(client, name="Basica", email="b@b.com", plan="basic")
    assert client.get("/analytics/revenue?granularity=day", headers=basic).status_code == 200
    assert client.get("/analytics/revenue?granularity=month", headers=basic).status_code == 403
    assert client.get("/analytics/export.csv", headers=basic).status_code == 403
    prem = make_tenant(client, name="Premium", email="p@p.com", plan="premium")
    for g, n in (("day", 14), ("week", 12), ("month", 12), ("year", 5)):
        assert len(client.get(f"/analytics/revenue?granularity={g}", headers=prem).json()) == n
    assert client.get("/analytics/export.csv", headers=prem).status_code == 200


def test_plan_limits_match_document(client, owner):
    plans = client.get("/plans").json()
    assert plans["free"]["max_packages"] == 30
    assert plans["free"]["max_operators"] == 1
    assert plans["basic"]["max_packages"] == 250
    assert plans["basic"]["max_notifications"] == 700
    assert plans["basic"]["max_operators"] == 2
    assert plans["premium"]["max_packages"] is None
    assert plans["premium"]["max_ai"] == 200
    assert plans["premium"]["max_notifications"] == 2000
    assert plans["premium"]["max_operators"] is None


def test_operator_cannot_manage_users_or_plan(client, owner):
    client.post("/users", headers=owner, json={"name": "Op Uno", "email": "op@sol.com", "password": "clave12345"})
    tok = client.post("/auth/login", json={"email": "op@sol.com", "password": "clave12345"}).json()
    op = {"Authorization": f"Bearer {tok['access_token']}"}
    new_user = {"name": "X Y", "email": "x@y.com", "password": "clave12345"}
    assert client.post("/users", headers=op, json=new_user).status_code == 403
    assert client.post("/tenants/me/plan", headers=op, json={"plan": "premium"}).status_code == 403


def test_auth_refresh_and_bad_login(client, owner):
    assert client.post("/auth/login", json={"email": "a@sol.com", "password": "mala"}).status_code == 401
    tok = client.post("/auth/login", json={"email": "a@sol.com", "password": "clave12345"}).json()
    assert client.post("/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": tok["access_token"]}).status_code == 401
    assert client.get("/packages").status_code == 401


def test_cierre_caja_bolivia_timezone(client, owner):
    p = new_package(client, owner)
    assert client.post(
        "/payments",
        headers=owner,
        json={"package_id": p["id"], "method": "cash", "amount": 12, "late_fee": 2},
    ).status_code == 201
    with SessionLocal() as db:
        payment = db.query(Payment).filter(Payment.package_id == p["id"]).one()
        payment.created_at = datetime(2026, 11, 21, 4, 30)
        db.commit()
    result = client.get("/analytics/cierre-caja", headers=owner, params={"fecha": "2026-11-21"})
    assert result.status_code == 200
    data = result.json()
    assert data["efectivo"] == 12.0
    assert data["total_cobrado"] == 12.0
    assert data["paquetes_pendientes"] >= 1
