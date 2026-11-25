import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ErrorNote, Field, Loading } from "../../components/ui";
import { api } from "../../lib/api";
import type { User } from "../../lib/types";

export default function TeamPage() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => api.get<User[]>("/users") });
  const [f, setF] = useState({ name: "", email: "", password: "", phone: "" });
  const set = (k: string) => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value });
  const add = useMutation({
    mutationFn: () => api.post("/users", { ...f, phone: f.phone || null }),
    onSuccess: () => {
      setF({ name: "", email: "", password: "", phone: "" });
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
  const toggle = useMutation({
    mutationFn: (id: number) => api.patch(`/users/${id}/toggle`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["users"] }),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold">Equipo</h1>
      <div className="card">
        {users.isLoading ? (
          <Loading />
        ) : (
          <ul className="divide-y divide-slate-100">
            {users.data!.map((u) => (
              <li key={u.id} className="flex items-center justify-between gap-3 py-3 text-sm">
                <div>
                  <p className="font-semibold">
                    {u.name} {!u.active && <span className="text-xs text-crimson-600">(inactivo)</span>}
                  </p>
                  <p className="text-slate-500">
                    {u.email} · {u.role === "owner" ? "Propietario" : "Operador"}
                  </p>
                </div>
                {u.role !== "owner" && (
                  <button className="btn-ghost" onClick={() => toggle.mutate(u.id)}>
                    {u.active ? "Desactivar" : "Activar"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        <ErrorNote error={toggle.error} />
      </div>
      <form onSubmit={submit} className="card space-y-3">
        <h2 className="font-semibold">Agregar operador</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Nombre">
            <input required minLength={2} className="input" value={f.name} onChange={set("name")} />
          </Field>
          <Field label="Celular (opcional)">
            <input className="input" inputMode="tel" value={f.phone} onChange={set("phone")} />
          </Field>
          <Field label="Correo">
            <input
              required
              type="email"
              className="input"
              value={f.email}
              onChange={set("email")}
            />
          </Field>
          <Field label="Contraseña inicial">
            <input
              required
              minLength={8}
              type="password"
              className="input"
              value={f.password}
              onChange={set("password")}
            />
          </Field>
        </div>
        <ErrorNote error={add.error} />
        <button className="btn-primary" disabled={add.isPending}>
          Agregar operador
        </button>
      </form>
    </div>
  );
}
