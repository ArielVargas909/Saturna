import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { ErrorNote, Field, Loading, Meter } from "../../components/ui";
import { api } from "../../lib/api";
import type { Plan, PlanKey, Tenant, Usage } from "../../lib/types";

export default function SettingsPage() {
  const qc = useQueryClient();
  const tenant = useQuery({ queryKey: ["tenant"], queryFn: () => api.get<Tenant>("/tenants/me") });
  const plans = useQuery({
    queryKey: ["plans"],
    queryFn: () => api.get<Record<PlanKey, Plan>>("/plans"),
  });
  const usage = useQuery({
    queryKey: ["usage"],
    queryFn: () => api.get<Usage>("/tenants/me/usage"),
  });
  const [f, setF] = useState<Partial<Tenant>>({});
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (tenant.data) setF(tenant.data);
  }, [tenant.data]);
  const set = (k: keyof Tenant) => (e: { target: { value: string } }) => {
    setSaved(false);
    setF({ ...f, [k]: e.target.value });
  };

  const save = useMutation({
    mutationFn: () =>
      api.patch("/tenants/me", {
        name: f.name,
        address: f.address,
        zone: f.zone,
        opening_hours: f.opening_hours,
        custody_days: Number(f.custody_days),
        qr_ttl_hours: Number(f.qr_ttl_hours),
        custody_fee: Number(f.custody_fee),
        late_fee_per_day: Number(f.late_fee_per_day),
      }),
    onSuccess: () => {
      setSaved(true);
      void qc.invalidateQueries();
    },
  });
  const changePlan = useMutation({
    mutationFn: (plan: PlanKey) => api.post("/tenants/me/plan", { plan }),
    onSuccess: () => void qc.invalidateQueries(),
  });
  const exp = useMutation({
    mutationFn: () => api.download("/analytics/export.csv", "saturna_cobros.csv"),
  });

  if (tenant.isLoading || plans.isLoading) return <Loading />;
  const current = tenant.data!.plan;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold">Ajustes</h1>

      <section>
        <h2 className="mb-3 font-semibold">Plan de suscripción</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {(Object.entries(plans.data!) as [PlanKey, Plan][]).map(([k, p]) => (
            <div key={k} className={`card ${current === k ? "border-2 border-orbit" : ""}`}>
              <p className="font-bold">{p.label}</p>
              <p className="text-2xl font-extrabold">
                Bs {p.price_bs}
                <span className="text-sm font-normal text-slate-500">/mes</span>
              </p>
              <ul className="my-3 space-y-1 text-xs text-slate-600">
                <li>{p.max_packages ?? "Ilimitados"} paquetes/mes</li>
                <li>{p.max_notifications} avisos WhatsApp</li>
                <li>{p.max_ai} consultas de IA</li>
                <li>{p.max_operators ?? "Ilimitados"} operador(es)</li>
                <li>
                  Gráficas: {p.granularities.length ? p.granularities.join(", ") : "no incluidas"}
                </li>
                {p.ai_advanced && <li>Copiloto financiero y alertas</li>}
                {p.export && <li>Reportes exportables (CSV)</li>}
              </ul>
              <button
                className={current === k ? "btn-ghost w-full" : "btn-primary w-full"}
                disabled={current === k || changePlan.isPending}
                onClick={() => changePlan.mutate(k)}
              >
                {current === k ? "Plan actual" : "Cambiar a este plan"}
              </button>
            </div>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Demostración: el cambio de plan es manual. El cobro automático de suscripciones queda
          fuera del MVP.
        </p>
        <ErrorNote error={changePlan.error} />
      </section>

      {usage.data && (
        <section className="card grid gap-4 sm:grid-cols-3">
          <Meter label="Paquetes" {...usage.data.packages} />
          <Meter label="Avisos" {...usage.data.notifications} />
          <Meter label="Consultas IA" {...usage.data.ai_queries} />
        </section>
      )}

      <form onSubmit={submit} className="card space-y-3">
        <h2 className="font-semibold">Mi paquetería</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nombre">
            <input className="input" value={f.name ?? ""} onChange={set("name")} />
          </Field>
          <Field label="Zona">
            <select className="input" value={f.zone ?? "La Paz"} onChange={set("zone")}>
              <option>La Paz</option>
              <option>El Alto</option>
            </select>
          </Field>
          <Field label="Dirección">
            <input className="input" value={f.address ?? ""} onChange={set("address")} />
          </Field>
          <Field label="Horario de atención" hint="Lo usa el agente de IA">
            <input
              className="input"
              value={f.opening_hours ?? ""}
              onChange={set("opening_hours")}
            />
          </Field>
          <Field label="Días de custodia gratuita del plazo">
            <input
              type="number"
              min={1}
              className="input"
              value={f.custody_days ?? 5}
              onChange={set("custody_days")}
            />
          </Field>
          <Field label="Vigencia del QR (horas)">
            <input
              type="number"
              min={1}
              className="input"
              value={f.qr_ttl_hours ?? 24}
              onChange={set("qr_ttl_hours")}
            />
          </Field>
          <Field label="Cobro de custodia (Bs)">
            <input
              type="number"
              min={0}
              step="0.5"
              className="input"
              value={f.custody_fee ?? 0}
              onChange={set("custody_fee")}
            />
          </Field>
          <Field label="Recargo por día de demora (Bs)">
            <input
              type="number"
              min={0}
              step="0.5"
              className="input"
              value={f.late_fee_per_day ?? 0}
              onChange={set("late_fee_per_day")}
            />
          </Field>
        </div>
        <ErrorNote error={save.error} />
        <div className="flex items-center gap-3">
          <button className="btn-primary" disabled={save.isPending}>
            Guardar cambios
          </button>
          {saved && <span className="text-sm text-[var(--success-text)]">Guardado ✔</span>}
        </div>
      </form>

      <section className="card">
        <h2 className="mb-2 font-semibold">Reportes</h2>
        <button className="btn-ghost" onClick={() => exp.mutate()} disabled={exp.isPending}>
          Exportar cobros (CSV)
        </button>
        <p className="mt-2 text-xs text-slate-500">Disponible en el plan Premium.</p>
        <ErrorNote error={exp.error} />
      </section>
    </div>
  );
}
