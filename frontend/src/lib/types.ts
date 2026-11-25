export type Role = "owner" | "operator";
export interface User {
  id: number;
  name: string;
  email: string;
  role: Role;
  phone: string | null;
  active: boolean;
  tenant_id: number;
}
export interface Tenant {
  id: number;
  name: string;
  address: string;
  zone: string;
  plan: PlanKey;
  custody_days: number;
  qr_ttl_hours: number;
  custody_fee: string;
  late_fee_per_day: string;
  opening_hours: string;
}
export type PlanKey = "free" | "basic" | "premium";
export interface Plan {
  label: string;
  price_bs: number;
  max_packages: number | null;
  max_notifications: number | null;
  max_ai: number | null;
  max_operators: number | null;
  granularities: string[];
  export: boolean;
  ai_advanced: boolean;
}
export interface Pkg {
  id: number;
  code: string;
  buyer_phone: string;
  buyer_name: string;
  sender: string;
  description: string;
  state: string;
  shelf_location: string;
  received_at: string;
  delivered_at: string | null;
  custody_deadline: string;
}
export interface Fees {
  base: string;
  late: string;
  total: string;
  days_late: number;
}
export interface PkgEvent {
  id: number;
  type: string;
  detail: string;
  created_at: string;
}
export interface PkgDetail extends Pkg {
  events: PkgEvent[];
  fees: Fees;
}
export interface Summary {
  by_state: Record<string, number>;
  in_custody: number;
  received_today: number;
  delivered_today: number;
  late_packages: number;
  avg_stay_hours: number;
  note: string;
  revenue_today: { total: number; cash: number; qr: number; count: number };
}
export interface RevenuePoint {
  bucket: string;
  total: number;
  cash: number;
  qr: number;
  count: number;
}
export interface Usage {
  month: string;
  plan: PlanKey;
  packages: { used: number; limit: number | null };
  notifications: { used: number; limit: number | null };
  ai_queries: { used: number; limit: number | null };
  operators_limit: number | null;
  granularities: string[];
  export: boolean;
}
export interface QRIssued {
  token: string;
  expires_at: string;
  image: string;
}
export interface ValidateOut {
  package: Pkg;
  fees: Fees;
  expires_at: string;
}
export interface AgentReply {
  reply: string;
  outbox: { type: string; url: string; caption?: string }[];
  role: string;
  tools: string[];
  mode: "llm" | "offline";
}

export interface CierreCaja {
  fecha: string;
  total_cobrado: number;
  efectivo: number;
  qr: number;
  cantidad_entregas: number;
  recargos_cobrados: number;
  paquetes_pendientes: number;
  paquetes_estancados: number;
}

export interface DeliveryPreview {
  llegada: string;
  dias_custodia: number;
  custodia: number | string;
  recargo: number | string;
  total: number | string;
}
