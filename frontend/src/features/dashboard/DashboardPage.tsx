import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorNote, Loading, Meter, StateBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { PLAN_LABEL, bs } from "../../lib/format";
import type { CierreCaja, RevenuePoint, Summary, Usage } from "../../lib/types";
import { Link } from "react-router-dom";

const GRAN = [
  ["day", "Diaria"],
  ["week", "Semanal"],
  ["month", "Mensual"],
  ["year", "Anual"],
] as const;

export default function DashboardPage() {
  const [gran, setGran] = useState<string>("day");
  const summary = useQuery({
    queryKey: ["summary"],
    queryFn: () => api.get<Summary>("/analytics/summary"),
    refetchInterval: 30000,
  });
  const usage = useQuery({
    queryKey: ["usage"],
    queryFn: () => api.get<Usage>("/tenants/me/usage"),
  });
  const boliviaDate = new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const cierre = useQuery({
    queryKey: ["cierre-caja", boliviaDate],
    queryFn: () => api.get<CierreCaja>(`/analytics/cierre-caja?fecha=${boliviaDate}`),
  });
  const allowed = usage.data?.granularities ?? [];
  const active = allowed.includes(gran) ? gran : allowed[0];
  const revenue = useQuery({
    queryKey: ["revenue", active],
    enabled: !!active,
    queryFn: () => api.get<RevenuePoint[]>(`/analytics/revenue?granularity=${active}`),
  });

  if (summary.isLoading) return <Loading />;
  if (summary.error) return <ErrorNote error={summary.error} />;
  const s = summary.data!;
  const stats: [string, string | number][] = [
    ["En custodia", s.in_custody],
    ["Recibidos hoy", s.received_today],
    ["Entregados hoy", s.delivered_today],
    ["Permanencia media", `${s.avg_stay_hours} h`],
  ];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Panel de control</h1>
          <p className="text-sm text-slate-500">Plan {PLAN_LABEL[usage.data?.plan ?? "free"]}</p>
        </div>
        <Link to="/packages?new=1" className="btn-accent">
          + Registrar paquete
        </Link>
      </header>

      {s.late_packages > 0 && (
        <Link
          to="/packages?state=ESTANCADO"
          className="block rounded-xl border border-crimson-600/30 bg-[var(--state-stalled-bg)] p-4 text-sm text-[var(--state-stalled-text)]"
        >
          <strong>{s.late_packages}</strong> paquete(s) superaron el plazo de custodia y generan
          recargo. Ver detalle
        </Link>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {stats.map(([k, v]) => (
          <div key={k} className="card">
            <p className="text-xs text-slate-500">{k}</p>
            <p className="mt-1 text-2xl font-bold">{v}</p>
          </div>
        ))}
        <div className="card col-span-2 border-cyan-500/40 bg-[var(--state-notified-bg)] lg:col-span-1">
          <p className="text-xs text-slate-600">Cobrado hoy</p>
          <p className="mt-1 text-2xl font-bold">{bs(s.revenue_today.total)}</p>
          <p className="text-xs text-slate-600">
            Efectivo {bs(s.revenue_today.cash)} · QR {bs(s.revenue_today.qr)}
          </p>
        </div>
      </section>

      {cierre.data && (
        <section className="card">
          <h2 className="font-semibold">Cierre del día</h2>
          <p className="mb-3 text-xs text-slate-500">Fecha Bolivia: {cierre.data.fecha}</p>
          <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <p>Total <strong>{bs(cierre.data.total_cobrado)}</strong></p>
            <p>Efectivo <strong>{bs(cierre.data.efectivo)}</strong></p>
            <p>QR <strong>{bs(cierre.data.qr)}</strong></p>
            <p>Entregas <strong>{cierre.data.cantidad_entregas}</strong></p>
            <p>Recargos <strong>{bs(cierre.data.recargos_cobrados)}</strong></p>
            <p>Pendientes <strong>{cierre.data.paquetes_pendientes}</strong></p>
            <p>Estancados <strong>{cierre.data.paquetes_estancados}</strong></p>
          </div>
          <p className="mt-3 text-xs text-slate-500">Cobros registrados; no es utilidad neta.</p>
        </section>
      )}

      <section className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold">Ingresos por cobros de custodia</h2>
            <div className="flex gap-1" role="tablist">
              {GRAN.map(([k, label]) => {
                const ok = allowed.includes(k);
                return (
                  <button
                    key={k}
                    role="tab"
                    aria-selected={active === k}
                    disabled={!ok}
                    onClick={() => setGran(k)}
                    title={ok ? "" : "Disponible en el plan Premium"}
                    className={`rounded-md px-2.5 py-1 text-xs font-semibold ${active === k ? "bg-brand-900 text-white" : "bg-app-bg text-app-muted"} disabled:opacity-40`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
          {!active ? (
            <p className="rounded-lg bg-slate-50 p-6 text-center text-sm text-slate-500">
              Las gráficas de ingresos están disponibles desde el plan Básico.{" "}
              <Link className="text-cyan-600 underline" to="/settings">
                Ver planes
              </Link>
            </p>
          ) : revenue.isLoading ? (
            <Loading />
          ) : (
            <div className="h-64">
              <ResponsiveContainer>
                <BarChart data={revenue.data}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="bucket"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: string) =>
                      v.slice(active === "day" || active === "week" ? 5 : 0)
                    }
                  />
                  <YAxis tick={{ fontSize: 11 }} width={40} />
                  <Tooltip formatter={(v: number) => bs(v)} />
                  <Legend />
                  <Bar dataKey="cash" name="Efectivo" stackId="a" fill="var(--cyan-500)" />
                  <Bar dataKey="qr" name="QR" stackId="a" fill="var(--crimson-600)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
          <p className="mt-2 text-xs text-slate-500">{s.note}</p>
        </div>

        <div className="space-y-4">
          <div className="card">
            <h2 className="mb-3 font-semibold">Inventario por estado</h2>
            <ul className="space-y-2">
              {Object.entries(s.by_state).map(([st, n]) => (
                <li key={st} className="flex items-center justify-between text-sm">
                  <StateBadge state={st} />
                  <span className="font-semibold">{n}</span>
                </li>
              ))}
              {Object.keys(s.by_state).length === 0 && (
                <li className="text-sm text-slate-500">Aún no hay paquetes.</li>
              )}
            </ul>
          </div>
          {usage.data && (
            <div className="card space-y-3">
              <h2 className="font-semibold">Uso del mes ({usage.data.month})</h2>
              <Meter label="Paquetes" {...usage.data.packages} />
              <Meter label="Avisos WhatsApp" {...usage.data.notifications} />
              <Meter label="Consultas de IA" {...usage.data.ai_queries} />
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
