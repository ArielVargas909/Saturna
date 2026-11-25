from app.modules.packages.service import can_transition
from app.models import Package, User
from tests.conftest import make_tenant, new_package


def test_state_machine_rules():
    assert can_transition("REGISTRADO", "NOTIFICADO")
    assert can_transition("NOTIFICADO", "LISTO_PARA_RETIRO")
    assert not can_transition("REGISTRADO", "ENTREGADO")  # no hay entrega sin QR
    assert not can_transition("ENTREGADO", "REGISTRADO")


def test_register_notifies_in_background(client, owner):
    p = new_package(client, owner)
    assert p["code"].startswith("SAT-") and p["buyer_phone"] == "59171234567"
    detail = client.get(f"/packages/{p['id']}", headers=owner).json()
    assert detail["state"] == "REGISTRADO"
    assert [e["type"] for e in detail["events"]][:2] == ["REGISTRO", "AVISO_SIMULADO"]


def test_cannot_deliver_by_manual_state(client, owner):
    p = new_package(client, owner)
    r = client.post(f"/packages/{p['id']}/state", headers=owner, json={"state": "ENTREGADO"})
    assert r.status_code == 422  # ENTREGADO no es un estado manual válido

def test_manual_return_is_allowed_and_audited(client, owner):
    p = new_package(client, owner)
    r = client.post(
        f"/packages/{p['id']}/state",
        headers=owner,
        json={"state": "DEVUELTO", "detail": "Devuelto al remitente"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "DEVUELTO"
    detail = client.get(f"/packages/{p['id']}", headers=owner).json()
    assert any(e["type"] == "ESTADO" and "DEVUELTO" in e["detail"] for e in detail["events"])


def test_manual_ready_for_pickup_is_audited(client, owner):
    p = new_package(client, owner)
    r = client.post(
        f"/packages/{p['id']}/state",
        headers=owner,
        json={"state": "LISTO_PARA_RETIRO", "detail": "Preparado en ventanilla"},
    )
    assert r.status_code == 200
    detail = client.get(f"/packages/{p['id']}", headers=owner).json()
    assert any(e["type"] == "ESTADO" and "LISTO_PARA_RETIRO" in e["detail"] for e in detail["events"])


def test_seed_is_repeatable_and_creates_demo_data(db):
    from scripts.seed import run

    run()
    run()
    assert db.query(Package).count() == 18
    assert db.query(User).filter(User.email.in_(["dueno@saturna.com", "operador@saturna.com"])).count() == 2
    assert db.query(Package).filter(Package.state == "ESTANCADO").count() >= 4


def test_search(client, owner):
    new_package(client, owner, name="Carlos")
    new_package(client, owner, phone="76543210", name="Lucía")
    r = client.get("/packages?q=Luc", headers=owner).json()
    assert r["total"] == 1 and r["items"][0]["buyer_name"] == "LUCÍA"


def test_text_fields_normalize_to_uppercase(client, owner):
    p = new_package(client, owner, name="  lorena   pérez ")
    assert p["buyer_name"] == "LORENA PÉREZ"
    r = client.patch(
        f"/packages/{p['id']}",
        headers=owner,
        json={"sender": " tienda   central ", "description": " caja   pequeña ", "shelf_location": " e2  5 "},
    )
    assert r.status_code == 200
    assert r.json()["sender"] == "TIENDA CENTRAL"
    assert r.json()["description"] == "CAJA PEQUEÑA"
    assert r.json()["shelf_location"] == "E2 5"


def test_search_is_case_and_accent_insensitive(client, owner):
    new_package(client, owner, name="LUCÍA FLORES")
    r = client.get("/packages?q=lucia", headers=owner).json()
    assert r["total"] >= 1


def test_title_name_helper():
    from app.core.text import title_name
    assert title_name("LORENA PÉREZ") == "Lorena Pérez"


def test_buyer_suggestion_threshold_and_frequency(client, owner):
    new_package(client, owner, phone="71234567", name="Lorena Pérez")
    new_package(client, owner, phone="71234567", name="Lorena Pérez")
    first = client.get("/packages/suggest-buyer", headers=owner, params={"phone": "71234567"}).json()
    assert first["items"] == []

    new_package(client, owner, phone="71234567", name="Lorena Pérez")
    new_package(client, owner, phone="71234567", name="Ana López")
    result = client.get("/packages/suggest-buyer", headers=owner, params={"phone": "71234567"}).json()
    assert result["items"][:2] == ["LORENA PÉREZ", "ANA LÓPEZ"]


def test_buyer_suggestion_tenant_isolation_and_invalid_phone(client, owner):
    other = make_tenant(client, name="Paquetería Luna", email="luna@test.com")
    for _ in range(3):
        new_package(client, other, phone="72222222", name="OTRA PERSONA")
    result = client.get("/packages/suggest-buyer", headers=owner, params={"phone": "72222222"})
    assert result.status_code == 200
    assert result.json()["items"] == []
    assert client.get("/packages/suggest-buyer", headers=owner, params={"phone": "abc"}).status_code == 422


def test_buyer_suggestion_excludes_anonymized(client, owner):
    for i in range(3):
        p = new_package(client, owner, phone="73333333", name="Nombre Visible")
        if i == 0:
            client.post(
                f"/packages/{p['id']}/deliver",
                headers=owner,
                json={"via": "manual", "identidad_verificada": True},
            )
            client.post(f"/packages/{p['id']}/anonymize", headers=owner)
    result = client.get("/packages/suggest-buyer", headers=owner, params={"phone": "73333333"}).json()
    assert "Nombre Visible" not in result["items"]
