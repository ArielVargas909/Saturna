from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from app.db.session import SessionLocal
from app.models import Package, Payment, QRToken, Tenant
from app.modules.qr import service as qr
from tests.conftest import make_tenant, new_package


def _issue(client, headers, pid):
    r = client.post(f"/packages/{pid}/qr", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_full_flow_and_single_use(client, owner):
    p = new_package(client, owner)
    q = _issue(client, owner, p["id"])
    assert q["image"].startswith("data:image/png;base64,")
    v = client.post("/qr/validate", headers=owner, json={"token": q["token"]})
    assert v.status_code == 200 and v.json()["package"]["code"] == p["code"]
    # sin cobro no se entrega (custodia > 0)
    assert client.post("/qr/confirm", headers=owner, json={"token": q["token"]}).status_code == 422
    ok = client.post("/qr/confirm", headers=owner, json={"token": q["token"], "payment_method": "cash"})
    assert ok.status_code == 200 and ok.json()["state"] == "ENTREGADO"
    again = client.post("/qr/confirm", headers=owner, json={"token": q["token"], "payment_method": "cash"})
    assert again.status_code == 409
    assert client.get("/analytics/summary", headers=owner).json()["revenue_today"]["cash"] == 5.0


def test_token_is_stored_hashed(client, owner, db):
    p = new_package(client, owner)
    q = _issue(client, owner, p["id"])
    row = db.query(QRToken).one()
    assert row.token_hash != q["token"] and row.token_hash == qr.hash_token(q["token"])


def test_reissue_revokes_previous(client, owner):
    p = new_package(client, owner)
    old = _issue(client, owner, p["id"])
    new = _issue(client, owner, p["id"])
    assert client.post("/qr/validate", headers=owner, json={"token": old["token"]}).status_code == 410
    assert client.post("/qr/validate", headers=owner, json={"token": new["token"]}).status_code == 200


def test_expired_token(client, owner, db):
    p = new_package(client, owner)
    q = _issue(client, owner, p["id"])
    from datetime import timedelta
    row = db.query(QRToken).one()
    row.expires_at = row.expires_at - timedelta(days=3)
    db.commit()
    assert client.post("/qr/validate", headers=owner, json={"token": q["token"]}).status_code == 410


def test_concurrent_confirmations_only_one_wins(client, owner, db):
    p = new_package(client, owner)
    token = _issue(client, owner, p["id"])["token"]

    def attempt(_):
        with SessionLocal() as s:
            tenant = s.get(Tenant, s.get(Package, p["id"]).tenant_id)
            try:
                qr.confirm_delivery(s, tenant, 1, token, "cash", None)
                return "ok"
            except HTTPException as e:
                return e.status_code

    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(attempt, range(8)))
    assert results.count("ok") == 1, results
    assert all(r in ("ok", 409) for r in results), results
    assert len(db.query(Payment).all()) == 1


def test_tenant_isolation(client, owner):
    other = make_tenant(client, name="Paquetería Luna", email="b@luna.com")
    p = new_package(client, owner)
    token = _issue(client, owner, p["id"])["token"]
    assert client.get(f"/packages/{p['id']}", headers=other).status_code == 404
    assert client.post("/qr/validate", headers=other, json={"token": token}).status_code == 404
    assert client.post(f"/packages/{p['id']}/qr", headers=other).status_code == 404
    assert client.get("/packages", headers=other).json()["total"] == 0


def test_validate_rate_limit(client, owner):
    fake = "x" * 43
    codes = [client.post("/qr/validate", headers=owner, json={"token": fake}).status_code for _ in range(45)]
    assert codes.count(404) == 40 and codes.count(429) == 5


def test_two_manual_payments_second_fails(client, owner):
    p = new_package(client, owner)
    body = {"package_id": p["id"], "method": "cash", "amount": 5}
    assert client.post("/payments", headers=owner, json=body).status_code == 201
    r = client.post("/payments", headers=owner, json=body)
    assert r.status_code == 409
    assert "ya tiene un cobro" in r.json()["detail"].lower()


def test_manual_payment_then_qr_confirmation_creates_no_second(client, owner):
    p = new_package(client, owner)
    assert client.post(
        "/payments",
        headers=owner,
        json={"package_id": p["id"], "method": "cash", "amount": 5},
    ).status_code == 201
    q = _issue(client, owner, p["id"])
    r = client.post("/qr/confirm", headers=owner, json={"token": q["token"]})
    assert r.status_code == 200


def test_manual_delivery_preview_and_confirm(client, owner):
    p = new_package(client, owner)
    preview = client.get(f"/packages/{p['id']}/deliver-preview", headers=owner)
    assert preview.status_code == 200
    assert float(preview.json()["total"]) == 5.0

    missing = client.post(
        f"/packages/{p['id']}/deliver",
        headers=owner,
        json={"via": "manual", "metodo_pago": "cash", "confirmo_pago": False, "identidad_verificada": True},
    )
    assert missing.status_code == 422

    result = client.post(
        f"/packages/{p['id']}/deliver",
        headers=owner,
        json={"via": "manual", "metodo_pago": "cash", "confirmo_pago": True, "identidad_verificada": True},
    )
    assert result.status_code == 200
    assert result.json()["state"] == "ENTREGADO"
    detail = client.get(f"/packages/{p['id']}", headers=owner).json()
    assert any(e["type"] == "ENTREGA_MANUAL" for e in detail["events"])


def test_manual_delivery_without_checkboxes_fails(client, owner):
    p = new_package(client, owner)
    r = client.post(
        f"/packages/{p['id']}/deliver",
        headers=owner,
        json={"via": "manual", "metodo_pago": "cash"},
    )
    assert r.status_code == 422


def test_manual_delivery_zero_fee_needs_no_method(client, owner):
    from app.db.session import SessionLocal
    from app.models import Tenant
    p = new_package(client, owner)
    with SessionLocal() as db:
        tenant = db.get(Tenant, 1)
        tenant.custody_fee = 0
        db.commit()
    r = client.post(
        f"/packages/{p['id']}/deliver",
        headers=owner,
        json={"via": "manual", "identidad_verificada": True},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "ENTREGADO"


def test_manual_delivery_invalidates_qr(client, owner):
    p = new_package(client, owner)
    q = _issue(client, owner, p["id"])
    r = client.post(
        f"/packages/{p['id']}/deliver",
        headers=owner,
        json={"via": "manual", "metodo_pago": "cash", "confirmo_pago": True, "identidad_verificada": True},
    )
    assert r.status_code == 200
    assert client.post("/qr/validate", headers=owner, json={"token": q["token"]}).status_code in (409, 410)


def test_manual_delivery_two_simultaneous_requests(client, owner, db):
    p = new_package(client, owner)
    body = {"via": "manual", "metodo_pago": "cash", "confirmo_pago": True, "identidad_verificada": True}
    import concurrent.futures
    def attempt(_):
        return client.post(f"/packages/{p['id']}/deliver", headers=owner, json=body).status_code
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        codes = list(pool.map(attempt, range(8)))
    assert codes.count(200) == 1
    assert all(code in (200, 409) for code in codes)
    assert len(db.query(Payment).all()) == 1


def test_manual_delivery_tenant_isolation(client, owner):
    other = make_tenant(client, name="Paquetería B", email="b@b.com")
    p = new_package(client, owner)
    r = client.post(
        f"/packages/{p['id']}/deliver",
        headers=other,
        json={"via": "manual", "metodo_pago": "cash", "confirmo_pago": True, "identidad_verificada": True},
    )
    assert r.status_code == 404
