import { LayoutDashboard, Briefcase, ShieldCheck, Settings, ScrollText, Moon, Sun, Monitor } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useCurrentUser } from "../api/hooks";
import { useThemeStore } from "../stores/themeStore";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/engagements", label: "Engagements", icon: Briefcase },
  { to: "/audit-trail", label: "Audit Trail", icon: ShieldCheck },
  { to: "/admin", label: "Admin", icon: Settings },
];

const THEME_CYCLE = { light: "dark", dark: "system", system: "light" } as const;
const THEME_ICON = { light: Sun, dark: Moon, system: Monitor } as const;

export function Layout() {
  const { data: user } = useCurrentUser();
  const location = useLocation();
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  const initials = user ? user.role.slice(0, 2).toUpperCase() : "..";
  const ThemeIcon = THEME_ICON[theme];

  return (
    <div className="min-h-screen flex" style={{ background: "var(--page-plane)" }}>
      <aside className="w-60 shrink-0 flex flex-col text-slate-100" style={{ background: "var(--sidebar-bg)" }}>
        <div className="px-5 py-5 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: "var(--series-blue)" }}>
            <ScrollText size={17} color="white" />
          </div>
          <div className="leading-tight">
            <div className="font-semibold text-sm text-white">Audit Sampling</div>
            <div className="text-[11px] text-slate-400">ISA 530 engine</div>
          </div>
        </div>

        <nav className="flex-1 px-3 py-2 space-y-0.5">
          {NAV.map((item) => {
            const active = location.pathname === item.to;
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors"
                style={active
                  ? { background: "rgba(42,120,214,0.18)", color: "white", fontWeight: 600 }
                  : { color: "#9ca3af" }}
              >
                <Icon size={17} strokeWidth={2} color={active ? "var(--series-blue)" : "#9ca3af"} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-2">
          <button
            onClick={() => setTheme(THEME_CYCLE[theme])}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            title={`Theme: ${theme} (click to change)`}
          >
            <ThemeIcon size={17} />
            <span className="capitalize">{theme}</span>
          </button>
        </div>

        <div className="px-3 py-4 border-t border-white/10">
          <div className="flex items-center gap-2.5 px-2 py-2">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0"
              style={{ background: "var(--series-violet)" }}
            >
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm text-white truncate">{user?.role ?? "..."}</div>
              <div className="text-[11px] text-slate-400 truncate">standalone</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
