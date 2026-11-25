import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorNote, Field, Loading, Modal, StateBadge } from "../../components/ui";
import { api } from "../../lib/api";
import { STATE_LABEL, dt } from "../../lib/format";
import type { Pkg } from "../../lib/types";

export default function PackagesPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const state = params.get("state") ?? "";
  const showNew = params.get("new") === "1";
  const list = useQuery({
    queryKey: ["packages", q, state],
    queryFn: () =>
      api.get<{ items: Pkg[]; total: number }>(
        `/packages?limit=100&q=${encodeURIComponent(q)}&state=${state}`,
      ),
  });
  const setParam = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p);
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Paquetes</h1>
        <button className="btn-accent" onClick={() => setParam("new", "1")}>
          + Registrar paquete
        </button>
      </header>

      <div className="flex flex-wrap gap-3">
        <input
          className="input max-w-xs"
          placeholder="Buscar por código, nombre o teléfono"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Buscar"
        />
        <select
          className="input max-w-[14rem]"
          value={state}
          onChange={(e) => setParam("state", e.target.value)}
          aria-label="Filtrar por estado"
        >
          <option value="">Todos los estados</option>
          {Object.entries(STATE_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>

      {list.isLoading ? (
        <Loading />
      ) : list.error ? (
        <ErrorNote error={list.error} />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-500">
              <tr>
                <th className="p-3">Código</th>
                <th className="p-3">Comprador</th>
                <th className="p-3">Remitente</th>
                <th className="p-3">Estante</th>
                <th className="p-3">Llegó</th>
                <th className="p-3">Estado</th>
              </tr>
            </thead>
            <tbody>
              {list.data!.items.map((p) => (
                <tr key={p.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="p-3 font-mono font-semibold">
                    <Link className="text-cyan-600 underline" to={`/packages/${p.id}`}>
                      {p.code}
                    </Link>
                  </td>
                  <td className="p-3">
                    {p.buyer_name || "—"}
                    <br />
                    <span className="text-xs text-slate-500">+{p.buyer_phone}</span>
                  </td>
                  <td className="p-3">{p.sender || "—"}</td>
                  <td className="p-3">{p.shelf_location || "—"}</td>
                  <td className="p-3">{dt(p.received_at)}</td>
                  <td className="p-3">
                    <StateBadge state={p.state} />
                  </td>
                </tr>
              ))}
              {list.data!.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-slate-500">
                    No hay paquetes con ese filtro.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {showNew && <NewPackage onClose={() => setParam("new", "")} />}
    </div>
  );
}

function NewPackage({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState({
    buyer_phone: "",
    buyer_name: "",
    sender: "",
    description: "",
    shelf_location: "",
  });
  const [created, setCreated] = useState<Pkg | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  useEffect(() => {
    if (f.buyer_name.trim() || f.buyer_phone.replace(/\D/g, "").length < 7) {
      setSuggestions([]);
      return;
    }
    const timer = window.setTimeout(() => {
      api.get<{ items: string[] }>(
        `/packages/suggest-buyer?phone=${encodeURIComponent(f.buyer_phone)}`,
      )
        .then((result) => setSuggestions(result.items))
        .catch(() => setSuggestions([]));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [f.buyer_phone, f.buyer_name]);
  const set = (k: string) => (e: { target: { value: string } }) =>
    setF({
      ...f,
      [k]: ["buyer_name", "sender", "description", "shelf_location"].includes(k)
        ? e.target.value.toUpperCase()
        : e.target.value,
    });
  const m = useMutation({
    mutationFn: () => api.post<Pkg>("/packages", f),
    onSuccess: (p) => {
      setCreated(p);
      void qc.invalidateQueries();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };

  if (created) {
    return (
      <Modal title="Paquete registrado" onClose={onClose}>
        <p className="text-sm text-slate-600">Código único (anótalo en el paquete):</p>
        <p className="my-3 rounded-lg bg-navy-900 py-4 text-center font-mono text-3xl font-bold tracking-wider text-white">
          {created.code}
        </p>
        <p className="text-sm text-slate-600">
          Se está avisando al comprador por WhatsApp. Puedes ver el resultado en el detalle.
        </p>
        <div className="mt-4 flex gap-2">
          <Link to={`/packages/${created.id}`} className="btn-primary flex-1">
            Ver detalle
          </Link>
          <button
            className="btn-ghost flex-1"
            onClick={() => {
              setCreated(null);
              setF({
                buyer_phone: "",
                buyer_name: "",
                sender: "",
                description: "",
                shelf_location: "",
              });
              m.reset();
            }}
          >
            Registrar otro
          </button>
        </div>
      </Modal>
    );
  }
  return (
    <Modal title="Registrar paquete" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Celular del comprador" hint="Recibirá el aviso por WhatsApp">
          <input
            required
            autoFocus
            inputMode="tel"
            className="input"
            placeholder="7xxxxxxx"
            value={f.buyer_phone}
            onChange={set("buyer_phone")}
          />
        </Field>
        <Field label="Nombre del comprador">
          <input className="input" value={f.buyer_name} onChange={set("buyer_name")} />
        </Field>
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((name) => (
              <button
                type="button"
                key={name}
                className="rounded-full border border-cyan-500 px-3 py-1 text-xs font-semibold text-cyan-600"
                onClick={() => setF((current) => ({ ...current, buyer_name: name.toUpperCase() }))}
              >
                ¿Es {name}?
              </button>
            ))}
          </div>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Remitente / vendedor">
            <input className="input" value={f.sender} onChange={set("sender")} />
          </Field>
          <Field label="Estante">
            <input
              className="input"
              placeholder="E2-5"
              value={f.shelf_location}
              onChange={set("shelf_location")}
            />
          </Field>
        </div>
        <Field label="Descripción">
          <input className="input" value={f.description} onChange={set("description")} />
        </Field>
        <ErrorNote error={m.error} />
        <button className="btn-accent w-full" disabled={m.isPending}>
          {m.isPending ? "Registrando…" : "Registrar y avisar"}
        </button>
      </form>
    </Modal>
  );
}
