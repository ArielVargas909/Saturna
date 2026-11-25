import { useState, type FormEvent } from "react";
import { ErrorNote, Field } from "../../components/ui";
import { useAuth } from "./AuthProvider";

export default function LoginPage() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [f, setF] = useState({
    tenant_name: "",
    address: "",
    zone: "La Paz",
    name: "",
    email: "",
    password: "",
    phone: "",
  });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string) => (e: { target: { value: string } }) =>
    setF({ ...f, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await login(f.email, f.password);
      else await register({ ...f, phone: f.phone || null });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-brand-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="login-cosmos absolute inset-0 opacity-30" />
        <div className="relative flex items-center gap-3">
          <img src={`${import.meta.env.BASE_URL}logo-icon.svg`} alt="Saturna" className="h-14 w-14" />
          <h1 className="text-3xl font-black tracking-tight">Saturna</h1>
        </div>
        <div className="relative max-w-md rounded-2xl border border-white/10 bg-brand-900/50 p-6 backdrop-blur-sm">
          <p className="text-4xl font-extrabold leading-tight">
            Entregas inteligentes, retiros en segundos.
          </p>
          <p className="mt-4 text-slate-300">
            Registra, avisa por WhatsApp y entrega con un QR de un solo uso. Sin cuadernos, sin
            paquetes perdidos.
          </p>
        </div>
        <p className="relative text-sm text-slate-400">Para paqueterías de La Paz y El Alto</p>
      </section>

      <section className="flex items-center justify-center bg-app-bg p-6 lg:bg-brand-900">
        <form onSubmit={submit} className="glass-card w-full max-w-sm space-y-4 rounded-3xl border border-white/80 bg-white/95 p-6 shadow-xl">
          <div className="flex justify-center pb-1 lg:hidden">
            <img src={`${import.meta.env.BASE_URL}logo-icon.svg`} alt="Saturna" className="h-16 w-16" />
          </div>
          <h2 className="text-2xl font-bold">
            {mode === "login" ? "Ingresa a tu paquetería" : "Crea tu cuenta gratuita"}
          </h2>
          {mode === "register" && (
            <>
              <Field label="Nombre de la paquetería">
                <input
                  required
                  minLength={2}
                  className="input"
                  value={f.tenant_name}
                  onChange={set("tenant_name")}
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Zona">
                  <select className="input" value={f.zone} onChange={set("zone")}>
                    <option>La Paz</option>
                    <option>El Alto</option>
                  </select>
                </Field>
                <Field label="Tu celular" hint="Para el copiloto por WhatsApp">
                  <input
                    className="input"
                    inputMode="tel"
                    value={f.phone}
                    onChange={set("phone")}
                    placeholder="7xxxxxxx"
                  />
                </Field>
              </div>
              <Field label="Dirección">
                <input className="input" value={f.address} onChange={set("address")} />
              </Field>
              <Field label="Tu nombre">
                <input
                  required
                  minLength={2}
                  className="input"
                  value={f.name}
                  onChange={set("name")}
                />
              </Field>
            </>
          )}
          <Field label="Correo">
            <input
              required
              type="email"
              className="input"
              autoComplete="email"
              value={f.email}
              onChange={set("email")}
            />
          </Field>
          <Field label="Contraseña" hint={mode === "register" ? "Mínimo 8 caracteres" : undefined}>
            <input
              required
              type="password"
              minLength={mode === "register" ? 8 : 1}
              className="input"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={f.password}
              onChange={set("password")}
            />
          </Field>
          <ErrorNote error={error} />
          <button className="btn-accent w-full" disabled={busy}>
            {busy ? "Un momento…" : mode === "login" ? "Ingresar" : "Crear cuenta"}
          </button>
          <button
            type="button"
            className="w-full text-sm text-cyan-600 underline"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
          >
            {mode === "login" ? "¿Primera vez? Registra tu paquetería" : "Ya tengo cuenta"}
          </button>
        </form>
      </section>
    </div>
  );
}
