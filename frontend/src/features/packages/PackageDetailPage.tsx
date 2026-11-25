import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ErrorNote, Loading, Modal, StateBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { bs, dt } from "../../lib/format";
import type { PkgDetail, QRIssued } from "../../lib/types";
import type { DeliveryPreview } from "../../lib/types";
import DeliveryModal from "../../components/DeliveryModal";

export default function PackageDetailPage() {
  const { id } = useParams();
  const qc = useQueryClient();
  const key = ["package", id];
  const q = useQuery({ queryKey: key, queryFn: () => api.get<PkgDetail>(`/packages/${id}`) });
  const [qr, setQr] = useState<QRIssued | null>(null);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const refresh = () => qc.invalidateQueries();
  const preview = useQuery({
    queryKey: ["delivery-preview", id],
    queryFn: () => api.get<DeliveryPreview>(`/packages/${id}/deliver-preview`),
    enabled: deliveryOpen,
  });
  const deliver = useMutation({
    mutationFn: (body: {
      metodo_pago: "cash" | "qr" | undefined;
      via: "manual" | "qr";
      identidad_verificada: boolean;
      confirmo_pago: boolean;
      nota: string;
    }) => api.post<PkgDetail>(`/packages/${id}/deliver`, body),
    onSuccess: () => {
      setDeliveryOpen(false);
      void refresh();
    },
  });

  const issue = useMutation({
    mutationFn: () => api.post<QRIssued>(`/packages/${id}/qr`),
    onSuccess: (d) => {
      setQr(d);
      void refresh();
    },
  });
  const notify = useMutation({
    mutationFn: () => api.post<{ status: string; detail: string }>(`/packages/${id}/notify`),
    onSuccess: () => void refresh(),
  });
  const giveBack = useMutation({
    mutationFn: () =>
      api.post(`/packages/${id}/state`, { state: "DEVUELTO", detail: "Devuelto al remitente" }),
    onSuccess: () => void refresh(),
  });

  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorNote error={q.error} />;
  const p = q.data!;
  const open = !["ENTREGADO", "DEVUELTO"].includes(p.state);

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Link to="/packages" className="text-sm text-cyan-600 underline">
        ← Paquetes
      </Link>
      <div className="card space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="font-mono text-3xl font-bold">{p.code}</p>
            <p className="mt-1 text-sm text-slate-500">{p.description || "Sin descripción"}</p>
          </div>
          <StateBadge state={p.state} />
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-500">Comprador</dt>
            <dd className="font-medium">{p.buyer_name || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Celular</dt>
            <dd className="font-medium">+{p.buyer_phone}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Remitente</dt>
            <dd className="font-medium">{p.sender || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Estante</dt>
            <dd className="font-medium">{p.shelf_location || "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Llegó</dt>
            <dd className="font-medium">{dt(p.received_at)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Custodia hasta</dt>
            <dd className="font-medium">{dt(p.custody_deadline)}</dd>
          </div>
        </dl>
        {open && (
          <div className="rounded-lg bg-slate-50 p-3 text-sm">
            Cobro a la fecha: <strong>{bs(p.fees.total)}</strong>
            <span className="text-slate-500">
              {" "}
              (custodia {bs(p.fees.base)}
              {p.fees.days_late > 0 &&
                ` + recargo ${bs(p.fees.late)} por ${p.fees.days_late} día(s)`}
              )
            </span>
          </div>
        )}
        <ErrorNote error={issue.error ?? notify.error ?? giveBack.error} />
        {notify.data && (
          <p className="text-sm text-slate-600">
            {notify.data.status === "sent" && "Aviso enviado ✔"}
            {notify.data.status === "simulated" && "Aviso simulado"}
            {notify.data.status === "failed" && `Aviso fallido: ${notify.data.detail}`}
          </p>
        )}
        {open && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-accent" onClick={() => setDeliveryOpen(true)}>
              Entregar
            </button>
            <button
              className="btn-accent"
              onClick={() => issue.mutate()}
              disabled={issue.isPending}
            >
              Emitir QR de retiro
            </button>
            <button
              className="btn-ghost"
              onClick={() => notify.mutate()}
              disabled={notify.isPending}
            >
              Reenviar aviso
            </button>
            <button
              className="btn-ghost !border-crimson-600 !text-crimson-600"
              onClick={() => confirm("¿Devolver al remitente?") && giveBack.mutate()}
            >
              Devolver
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <h2 className="mb-3 font-semibold">Bitácora de auditoría</h2>
        <ol className="space-y-2 border-l-2 border-slate-200 pl-4">
          {p.events.map((e) => (
            <li key={e.id} className="text-sm">
              <span className="font-semibold">{e.type}</span>{" "}
              <span className="text-slate-500">· {dt(e.created_at)}</span>
              <p className="text-slate-600">{e.detail}</p>
            </li>
          ))}
        </ol>
      </div>

      {deliveryOpen && preview.data && (
        <DeliveryModal
          preview={preview.data}
          via="manual"
          busy={deliver.isPending}
          error={deliver.error}
          onClose={() => setDeliveryOpen(false)}
          onConfirm={(body) => deliver.mutate(body)}
        />
      )}

      {qr && (
        <Modal title={`QR de retiro ${p.code}`} onClose={() => setQr(null)}>
          <img
            src={qr.image}
            alt="Código QR de retiro"
            className="mx-auto w-64 rounded-lg border"
          />
          <p className="mt-3 text-center text-sm text-slate-600">
            Sirve una sola vez. Vence el {dt(qr.expires_at)}.
          </p>
          <p className="mt-1 text-center text-xs text-slate-500">
            Este QR solo se muestra ahora; si se pierde, emite uno nuevo (el anterior queda sin
            efecto).
          </p>
        </Modal>
      )}
    </div>
  );
}
