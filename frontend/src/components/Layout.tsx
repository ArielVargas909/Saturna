import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../features/auth/AuthProvider";

const NAV = [
  { to: "/", label: "Panel", icon: "▦", end: true },
  { to: "/packages", label: "Paquetes", icon: "▣" },
  { to: "/scanner", label: "Escanear QR", icon: "◈" },
  { to: "/agent", label: "Agente IA", icon: "✦" },
  { to: "/team", label: "Equipo", icon: "☻", owner: true },
  { to: "/settings", label: "Ajustes", icon: "⚙", owner: true },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const items = NAV.filter((n) => !n.owner || user?.role === "owner");
  return (
    <div className="relative min-h-screen overflow-hidden lg:grid lg:grid-cols-[15rem_1fr]">
      <div className="pointer-events-none fixed -right-40 top-20 h-80 w-80 rounded-full bg-cyan-500/10 blur-3xl" />
      <aside className="relative hidden flex-col overflow-hidden bg-brand-900 p-4 text-slate-200 shadow-[12px_0_36px_rgba(11,20,69,0.16)] lg:flex">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_110%_-10%,rgba(31,182,245,0.18),transparent_45%),radial-gradient(circle_at_-20%_110%,rgba(247,37,75,0.12),transparent_38%)]" />
        <div className="relative flex items-center gap-3 px-3 py-4">
          <img src={`${import.meta.env.BASE_URL}logo-icon.svg`} alt="Saturna" className="h-11 w-11 rounded-xl" />
          <p className="text-2xl font-black tracking-tight text-white">Saturna</p>
        </div>
        <nav className="relative mt-2 flex flex-1 flex-col gap-1">
          {items.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 ${isActive ? "bg-cyan-500 text-brand-900 shadow-[0_8px_22px_rgba(31,182,245,0.22)]" : "text-slate-200 hover:translate-x-1 hover:bg-brand-700"}`
              }
            >
              <span aria-hidden className="w-5 text-center text-cyan-500">
                {n.icon}
              </span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="relative border-t border-white/10 px-3 pt-3 text-xs">
          <p className="truncate font-semibold text-white">{user?.name}</p>
          <p className="mb-2 text-slate-400">
            {user?.role === "owner" ? "Propietario" : "Operador"}
          </p>
          <button onClick={logout} className="underline hover:text-white">
            Cerrar sesión
          </button>
        </div>
      </aside>

      <main className="min-w-0 p-4 pb-24 sm:p-8 lg:pb-8">
        <Outlet />
      </main>

      <nav
        className="fixed inset-x-0 bottom-0 z-40 grid border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] lg:hidden"
        style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}
      >
        {items.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.end}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium transition-all duration-200 ${isActive ? "-translate-y-0.5 text-cyan-600" : "text-slate-500"}`
            }
          >
            <span aria-hidden className="text-lg leading-none">
              {n.icon}
            </span>
            {n.label.split(" ")[0]}
          </NavLink>
        ))}
        <button
          onClick={logout}
          className="flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium text-slate-500"
        >
          <span aria-hidden className="text-lg leading-none">
            ⎋
          </span>
          Salir
        </button>
      </nav>
    </div>
  );
}
