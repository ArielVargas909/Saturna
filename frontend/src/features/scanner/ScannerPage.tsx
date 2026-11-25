import { Scanner } from "@yudiel/react-qr-scanner";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorNote, StateBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { bs } from "../../lib/format";
import type { ValidateOut } from "../../lib/types";
import DeliveryModal from "../../components/DeliveryModal";

export default function ScannerPage() {
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [manual, setManual] = useState("");
  const [method, setMethod] = useState<"cash" | "qr">("cash");
  const [amount, setAmount] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [deliveryOpen, setDeliveryOpen] = useState(false);

  const validate = useMutation({
    mutationFn: (t: string) => api.post<ValidateOut>("/qr/validate", { token: t }),
    onSuccess: (d) => {
      setAmount(String(d.fees.total));
      setDone(null);
      setDeliveryOpen(true);
    },
  });
  const confirmM = useMutation({
    mutationFn: (body: { metodo_pago: "cash" | "qr" | undefined; confirmo_pago: boolean }) =>
      api.post("/qr/confirm", {
        token,
        payment_method: body.metodo_pago,
        amount: body.metodo_pago ? validate.data?.fees.total : undefined,
      }),
    onSuccess: () => {
      setDone(validate.data!.package.code);
      validate.reset();
      setToken("");
      void qc.invalidateQueries();
    },
  });

  const onToken = (t: string) => {
    if (t && t !== token) {
      setToken(t);
      validate.mutate(t);
    }
  };
  const reset = () => {
    validate.reset();
    confirmM.reset();
    setToken("");
    setManual("");
  };
  const v = validate.data;

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-bold">Validar retiro</h1>

      {done && (
        <div className="rounded-xl bg-[var(--success-bg)] p-4 text-[var(--success-text)]">
          <p className="font-bold">Entrega confirmada ✔</p>
          <p className="text-sm">
            Paquete {done}. El QR quedó invalidado y el inventario se actualizó.
          </p>
        </div>
      )}

      {!v && (
        <>
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-black">
            <Scanner
              onScan={(codes) => onToken(codes[0]?.rawValue ?? "")}
              formats={["qr_code"]}
              onError={() => undefined}
              components={{ finder: true }}
              styles={{ container: { width: "100%" } }}
            />
          </div>
          <p className="text-center text-sm text-slate-500">
            Apunta la cámara al QR del comprador. Si no se puede, pega el código:
          </p>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              onToken(manual.trim());
            }}
          >
            <input
              className="input"
              placeholder="Código del QR"
              value={manual}
              onChange={(e) => setManual(e.target.value)}
              aria-label="Código del QR"
            />
            <button className="btn-primary">Validar</button>
          </form>
          {validate.isPending && <p className="text-sm text-slate-500">Verificando…</p>}
          <ErrorNote error={validate.error} />
          {validate.error && (
            <button className="btn-ghost" onClick={reset}>
              Escanear de nuevo
            </button>
          )}
        </>
      )}

      {v && (
        <div className="card space-y-4">
          {deliveryOpen && (
            <DeliveryModal
              preview={{
                llegada: v.package.received_at,
                dias_custodia: v.fees.days_late,
                custodia: v.fees.base,
                recargo: v.fees.late,
                total: v.fees.total,
              }}
              via="qr"
              busy={confirmM.isPending}
              error={confirmM.error}
              onClose={() => setDeliveryOpen(false)}
              onConfirm={(body) => confirmM.mutate(body)}
            />
          )}
          <div className="flex items-center justify-between">
            <p className="font-mono text-2xl font-bold">{v.package.code}</p>
            <StateBadge state={v.package.state} />
          </div>
          <p className="text-sm">
            Entregar a: <strong>{v.package.buyer_name || "(sin nombre)"}</strong> · +
            {v.package.buyer_phone}
          </p>
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            Verifica el carnet del comprador antes de entregar.
          </p>
          <div className="rounded-lg bg-slate-50 p-3 text-sm">
            Cobro de custodia: <strong>{bs(v.fees.total)}</strong>
            {v.fees.days_late > 0 && (
              <span className="text-crimson-600">
                {" "}
                (incluye recargo de {v.fees.days_late} día(s))
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            {(["cash", "qr"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMethod(m)}
                aria-pressed={method === m}
                className={`rounded-lg border-2 py-3 text-sm font-semibold ${method === m ? "border-cyan-500 bg-cyan-500/15 text-brand-900" : "border-app-border text-ink"}`}
              >
                {m === "cash" ? "Efectivo" : "QR / transferencia"}
              </button>
            ))}
          </div>
          <label className="block text-sm">
            <span className="mb-1 block font-medium">Monto cobrado (Bs)</span>
            <input
              className="input"
              type="number"
              min="0"
              step="0.5"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <span className="mt-1 block text-xs text-slate-500">
              Confirma que el dinero ya llegó. Saturna no acepta capturas de pantalla como prueba de
              pago.
            </span>
          </label>
          <ErrorNote error={confirmM.error} />
          <div className="flex gap-2">
            <button
              className="btn-accent flex-1"
              disabled={confirmM.isPending}
              onClick={() => confirmM.mutate({ metodo_pago: method, confirmo_pago: true })}
            >
              Confirmar cobro y entrega
            </button>
            <button className="btn-ghost" onClick={reset}>
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
