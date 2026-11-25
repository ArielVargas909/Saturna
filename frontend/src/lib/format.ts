export function bs(value: number | string | null | undefined): string {
  const n = Number(value ?? 0);
  return `Bs ${n.toLocaleString("es-BO", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** El backend envía fechas UTC sin zona; se interpretan como UTC y se muestran en hora local. */
export function dt(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
  return d.toLocaleString("es-BO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export const STATE_LABEL: Record<string, string> = {
  REGISTRADO: "Registrado",
  NOTIFICADO: "Avisado",
  LISTO_PARA_RETIRO: "Listo para retiro",
  ENTREGADO: "Entregado",
  ESTANCADO: "Estancado",
  DEVUELTO: "Devuelto",
  VENCIDO: "Vencido",
};

export const STATE_STYLE: Record<string, string> = {
  REGISTRADO: "bg-[var(--state-registered-bg)] text-[var(--state-registered-text)]",
  NOTIFICADO: "bg-[var(--state-notified-bg)] text-[var(--state-notified-text)]",
  LISTO_PARA_RETIRO: "bg-[var(--state-ready-bg)] text-[var(--state-ready-text)]",
  ENTREGADO: "bg-[var(--state-delivered-bg)] text-[var(--state-delivered-text)]",
  ESTANCADO: "bg-[var(--state-stalled-bg)] text-[var(--state-stalled-text)]",
  DEVUELTO: "bg-[var(--state-returned-bg)] text-[var(--state-returned-text)]",
  VENCIDO: "bg-[var(--state-expired-bg)] text-[var(--state-expired-text)]",
};

export const PLAN_LABEL = { free: "Gratuito", basic: "Básico", premium: "Premium" } as const;
