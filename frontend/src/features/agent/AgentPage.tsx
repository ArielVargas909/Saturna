import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ErrorNote } from "../../components/ui";
import { api } from "../../lib/api";
import type { AgentReply } from "../../lib/types";

interface Msg {
  from: "me" | "bot";
  text: string;
  image?: string;
  tools?: string[];
  mode?: "llm" | "offline";
}

export default function AgentPage() {
  const [phone, setPhone] = useState("");
  const [text, setText] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const send = useMutation({
    mutationFn: (message: string) => api.post<AgentReply>("/agent/simulate", { phone, message }),
    onSuccess: (r) =>
      setMsgs((m) => [
        ...m,
        { from: "bot", text: r.reply, tools: r.tools, mode: r.mode },
        ...r.outbox
          .filter((o) => o.type === "image")
          .map((o) => ({ from: "bot" as const, text: o.caption ?? "QR", image: o.url })),
      ]),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!text.trim() || !phone.trim()) return;
    setMsgs((m) => [...m, { from: "me", text }]);
    send.mutate(text);
    setText("");
  };

  return (
    <div className="mx-auto max-w-xl space-y-3">
      <h1 className="text-2xl font-bold">Agente de IA (simulador de WhatsApp)</h1>
      <p className="text-sm text-slate-600">
        Escribe como si fueras un comprador: usa el celular que registraste en un paquete. Para
        probar el copiloto financiero (plan Premium) usa el celular del propietario. Aquí no se
        envían mensajes reales.
      </p>
      <input
        className="input"
        inputMode="tel"
        placeholder="Celular de quien escribe (ej. 71234567)"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
        aria-label="Celular"
      />
      <div className="h-96 space-y-2 overflow-y-auto rounded-xl bg-app-bg p-3">
        {msgs.length === 0 && (
          <p className="pt-8 text-center text-sm text-slate-500">
            Prueba: “hola, ¿cómo va mi paquete SAT-XXXXXX?” o “quiero mi QR”
          </p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.from === "me" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] whitespace-pre-line rounded-xl px-3 py-2 text-sm shadow-sm ${m.from === "me" ? "bg-cyan-500 text-brand-900" : "bg-white text-ink"}`}
            >
              {m.image ? <img src={m.image} alt={m.text} className="w-44 rounded" /> : m.text}
              {m.mode && (
                <p className="mt-1 text-[10px] font-semibold text-slate-500">
                  {m.mode === "llm" ? "IA real" : "Respaldo por reglas"}
                </p>
              )}
              {m.tools && m.tools.length > 0 && (
                <p className="mt-1 text-[10px] text-slate-400">
                  herramientas: {m.tools.join(", ")}
                </p>
              )}
            </div>
          </div>
        ))}
        {send.isPending && <p className="text-xs text-slate-500">escribiendo…</p>}
      </div>
      <ErrorNote error={send.error} />
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="input"
          placeholder="Escribe un mensaje"
          value={text}
          onChange={(e) => setText(e.target.value)}
          aria-label="Mensaje"
        />
        <button className="btn-accent" disabled={send.isPending}>
          Enviar
        </button>
      </form>
    </div>
  );
}
