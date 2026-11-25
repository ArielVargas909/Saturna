from fastapi import APIRouter, Query, Response

from app.core.deps import DB, CurrentTenant
from app.modules.analytics import service
from app.modules.packages import service as pkgs

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
def summary(db: DB, tenant: CurrentTenant):
    pkgs.refresh_stale(db, tenant.id)
    return service.summary(db, tenant)


@router.get("/revenue")
def revenue(db: DB, tenant: CurrentTenant, granularity: str = Query("day")):
    """El BACKEND decide qué granularidades entrega según el plan (no solo el frontend)."""
    return service.revenue_series(db, tenant, granularity)


@router.get("/export.csv")
def export(db: DB, tenant: CurrentTenant):
    return Response(
        service.export_csv(db, tenant),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=saturna_cobros.csv"},
    )


@router.get("/cierre-caja")
def cierre(db: DB, tenant: CurrentTenant, fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
    return service.cierre_caja(db, tenant, fecha)
