"""Datos de demostración: python -m scripts.seed  (ejecutar desde backend/)."""
import random
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.timeutil import utcnow
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models import (
    AIConversation,
    Notification,
    Package,
    PackageEvent,
    Payment,
    QRToken,
    Tenant,
    UsageCounter,
    User,
)
from app.modules.packages.service import add_event, generate_code

random.seed(7)
NAMES = ["ANA QUISPE", "CARLOS MAMANI", "LUCÍA FLORES", "JORGE CONDORI", "MARÍA CHOQUE", "PEDRO TICONA",
         "ROSA APAZA", "LUIS HUANCA", "ELENA VARGAS", "MARIO COLQUE"]
SENDERS = ["TIENDA MODA LP", "ELECTRO EL ALTO", "COSMÉTICOS ANDINA", "LIBROS SOPOCACHI", "ZAPATOS SUR"]


def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        owner = db.scalar(select(User).where(User.email == "dueno@saturna.com"))
        t = db.get(Tenant, owner.tenant_id) if owner else None
        if t is None:
            t = Tenant(name="Paquetería Illimani", address="Av. 6 de Agosto 2170, La Paz", zone="La Paz",
                       plan="premium", opening_hours="Lun-Sáb 09:00 a 19:30")
            db.add(t)
            db.flush()
        else:
            t.name = "Paquetería Illimani"
            t.address = "Av. 6 de Agosto 2170, La Paz"
            t.zone = "La Paz"
            t.plan = "premium"
            t.opening_hours = "Lun-Sáb 09:00 a 19:30"
        package_ids = select(Package.id).where(Package.tenant_id == t.id)
        db.execute(delete(Payment).where(Payment.package_id.in_(package_ids)))
        db.execute(delete(PackageEvent).where(PackageEvent.package_id.in_(package_ids)))
        db.execute(delete(QRToken).where(QRToken.package_id.in_(package_ids)))
        db.execute(delete(Notification).where(Notification.tenant_id == t.id))
        db.execute(delete(AIConversation).where(AIConversation.tenant_id == t.id))
        db.execute(delete(UsageCounter).where(UsageCounter.tenant_id == t.id))
        db.execute(delete(Package).where(Package.tenant_id == t.id))
        pw = hash_password("saturna123")
        operator = db.scalar(select(User).where(User.email == "operador@saturna.com"))
        if owner is None:
            db.add(User(tenant_id=t.id, name="Dueña Illimani", email="dueno@saturna.com", password_hash=pw,
                        role="owner", phone="59170000001"))
        else:
            owner.name = "Dueña Illimani"
            owner.password_hash = pw
            owner.role = "owner"
            owner.phone = "59170000001"
            owner.active = True
        if operator is None:
            db.add(User(tenant_id=t.id, name="Operador Uno", email="operador@saturna.com", password_hash=pw,
                        role="operator", phone="59170000002"))
        else:
            operator.name = "Operador Uno"
            operator.password_hash = pw
            operator.role = "operator"
            operator.phone = "59170000002"
            operator.active = True
        now = utcnow()
        states = [
            "ENTREGADO", "ENTREGADO", "ENTREGADO", "ENTREGADO", "ENTREGADO",
            "NOTIFICADO", "NOTIFICADO", "NOTIFICADO",
            "REGISTRADO", "REGISTRADO", "REGISTRADO",
            "LISTO_PARA_RETIRO", "LISTO_PARA_RETIRO",
            "ESTANCADO", "ESTANCADO", "ESTANCADO", "ESTANCADO", "DEVUELTO",
        ]
        for i, state in enumerate(states):
            received = now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 8))
            deadline = received + timedelta(days=t.custody_days)
            p = Package(
                tenant_id=t.id, code=generate_code(db), buyer_phone=f"5917{random.randint(1000000, 7999999)}",
                buyer_name=random.choice(NAMES), sender=random.choice(SENDERS), description="Paquete",
                shelf_location=f"E{random.randint(1, 4)}-{random.randint(1, 9)}", state=state,
                received_at=received, custody_deadline=deadline,
            )
            if state == "ENTREGADO":
                p.delivered_at = min(now, received + timedelta(hours=random.randint(2, 70)))
                p.delivered_at = max(p.delivered_at, now - timedelta(days=min(i % 7, 6)))
            db.add(p)
            db.flush()
            add_event(db, p.id, "REGISTRO", "Paquete recibido (demo)")
            if state == "ENTREGADO":
                db.add(Payment(tenant_id=t.id, package_id=p.id, amount=5, late_fee=0,
                               method=random.choice(["cash", "qr"]), created_at=p.delivered_at))
                add_event(db, p.id, "ENTREGA", "Entrega confirmada (demo)")
        db.commit()
    print("Demo lista → dueno@saturna.com / operador@saturna.com  (clave: saturna123)")
    print("Teléfono del dueño para el simulador del agente: 70000001")


if __name__ == "__main__":
    run()
