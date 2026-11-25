import { useState, type FormEvent } from "react";
import { bs, dt } from "../lib/format";
import type { DeliveryPreview } from "../lib/types";
import { ErrorNote, Modal } from "./ui";

interface Props {
  preview: DeliveryPreview;
  via: "manual" | "qr";
  busy?: boolean;
  error?: unknown;
  onClose: () => void;
  onConfirm: (body: {
    metodo_pago: "cash" | "qr" | undefined;
    via: "manual" | "qr";
    identidad_verificada: boolean;
    confirmo_pago: boolean;
    nota: string;
  }) => void;
}

export default function DeliveryModal({ preview, via, busy, error, onClose, onConfirm }: Props) {
  const [method, setMethod] = useState<"cash" | "qr">("cash");
  const [identityVerified, setIdentityVerified] = useState(false);
  const [paymentConfirmed, setPaymentConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const payable = Number(preview.total) > 0;
  const canConfirm =
    !busy &&
    (via === "qr" || identityVerified) &&
    (!payable || paymentConfirmed);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!canConfirm) return;
    onConfirm({
      metodo_pago: payable ? method : undefined,
      via,
      identidad_verificada: via === "manual" ? identityVerified : false,
      confirmo_pago: payable ? paymentConfirmed : true,
      nota: note.trim(),
    });
  };

  return (
    <Modal title="Confirmar entrega" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 rounded-lg bg-slate-50 p-3 text-sm">
          <div><dt className="text-slate-500">Llegó</dt><dd className="font-semibold">{dt(preview.llegada)}</dd></div>
          <div><dt className="text-slate-500">Días en custodia</dt><dd className="font-semibold">{preview.dias_custodia}</dd></div>
          <div><dt className="text-slate-500">Custodia</dt><dd className="font-semibold">{bs(preview.custodia)}</dd></div>
          <div><dt className="text-slate-500">Recargo</dt><dd className="font-semibold">{bs(preview.recargo)}</dd></div>
          <div className="col-span-2"><dt className="text-slate-500">Total</dt><dd className="text-xl font-bold">{bs(preview.total)}</dd></div>
        </dl>

        {payable && (
          <>
            <div className="grid grid-cols-2 gap-3">
              {(["cash", "qr"] as const).map((option) => (
                <button
                  type="button"
                  key={option}
                  onClick={() => setMethod(option)}
                  aria-pressed={method === option}
                  className={`rounded-lg border-2 py-3 text-sm font-semibold ${method === option ? "border-cyan-500 bg-cyan-500/15 text-brand-900" : "border-app-border text-ink"}`}
                >
                  {option === "cash" ? "Efectivo" : "QR / transferencia"}
                </button>
              ))}
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" checked={paymentConfirmed} onChange={(event) => setPaymentConfirmed(event.target.checked)} />
              <span>Recibí el pago de {bs(preview.total)}</span>
            </label>
          </>
        )}

        {via === "manual" && (
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={identityVerified} onChange={(event) => setIdentityVerified(event.target.checked)} />
            <span>Verifiqué la identidad del comprador</span>
          </label>
        )}

        <label className="block text-sm">
          <span className="mb-1 block font-medium">Nota opcional</span>
          <input className="input" value={note} onChange={(event) => setNote(event.target.value)} />
        </label>
        <ErrorNote error={error} />
        <div className="flex gap-2">
          <button type="submit" className="btn-accent flex-1" disabled={!canConfirm}>
            {busy ? "Confirmando…" : "Confirmar entrega"}
          </button>
          <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>Cancelar</button>
        </div>
      </form>
    </Modal>
  );
}
