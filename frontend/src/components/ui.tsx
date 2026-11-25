import { useEffect, type ReactNode } from "react";
import { STATE_LABEL, STATE_STYLE } from "../lib/format";

export function StateBadge({ state }: { state: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATE_STYLE[state] ?? "bg-slate-100"}`}
    >
      {STATE_LABEL[state] ?? state}
    </span>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-[var(--state-stalled-bg)] px-3 py-2 text-sm text-[var(--state-stalled-text)]">
      {error instanceof Error ? error.message : String(error)}
    </p>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-navy-950/60 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-lg sm:rounded-2xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-md px-2 text-2xl leading-none text-slate-500 hover:bg-slate-100"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Meter({
  label,
  used,
  limit,
}: {
  label: string;
  used: number;
  limit: number | null;
}) {
  const pct = limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-600">
        <span>{label}</span>
        <span>
          {used} / {limit ?? "∞"}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${pct > 85 ? "bg-crimson-600" : "bg-cyan-500"}`}
          style={{ width: `${limit ? pct : 8}%` }}
        />
      </div>
    </div>
  );
}

export function Loading() {
  return <p className="py-8 text-center text-sm text-slate-500">Cargando…</p>;
}
