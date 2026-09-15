import {
  LayoutDashboard,
  LineChart,
  LogOut,
  MessagesSquare,
  PiggyBank,
  Sparkles,
  Wallet,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import DisclaimerFooter from "./DisclaimerFooter";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/assets", label: "Assets", icon: PiggyBank },
  { to: "/cash-flows", label: "Cash Flows", icon: Wallet },
  { to: "/forecast", label: "Forecast", icon: LineChart },
  { to: "/what-if", label: "What-If", icon: Sparkles },
  { to: "/chat", label: "AI Chat", icon: MessagesSquare },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const initial = (user?.username || "?").charAt(0).toUpperCase();

  return (
    <div className="min-h-screen flex" style={{ background: "var(--bg)" }}>
      <aside
        className="w-60 shrink-0 hidden md:flex flex-col"
        style={{ background: "var(--surface)", borderRight: "1px solid var(--border)" }}
      >
        <div className="h-16 flex items-center gap-2 px-5" style={{ borderBottom: "1px solid var(--border)" }}>
          <div
            className="w-8 h-8 rounded-lg flex items-center justify-center text-white shrink-0"
            style={{ background: "linear-gradient(135deg, var(--brand-500), var(--brand-700))" }}
          >
            <Wallet size={16} />
          </div>
          <div className="font-semibold text-[15px] leading-tight" style={{ fontFamily: "var(--font-display)", color: "var(--ink-900)" }}>
            Cash-flow<br />Forecast
          </div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "nav-link-active" : "nav-link-idle"
                }`
              }
            >
              <item.icon size={17} strokeWidth={2} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3" style={{ borderTop: "1px solid var(--border)" }}>
          <div className="flex items-center gap-2.5 px-2 py-2 rounded-lg">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold shrink-0"
              style={{ background: "var(--brand-100)", color: "var(--brand-700)" }}
            >
              {initial}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate" style={{ color: "var(--ink-900)" }}>{user?.username}</div>
              <div className="text-xs capitalize" style={{ color: "var(--ink-400)" }}>{user?.role || "regular"}</div>
            </div>
            <button onClick={logout} className="btn-ghost !px-2 !py-1.5" title="Logout">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-w-0">
        <header
          className="h-16 flex md:hidden items-center justify-between px-4"
          style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}
        >
          <div className="font-semibold" style={{ fontFamily: "var(--font-display)" }}>Cash-flow Forecast</div>
          <button onClick={logout} className="btn-ghost !px-2 !py-1.5"><LogOut size={16} /></button>
        </header>

        <nav className="flex md:hidden gap-1 px-3 py-2 overflow-x-auto" style={{ background: "var(--surface)", borderBottom: "1px solid var(--border)" }}>
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) => `tab-btn shrink-0 ${isActive ? "active" : ""}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <main className="flex-1 w-full mx-auto px-5 md:px-8 py-6 max-w-6xl">
          <Outlet />
        </main>
        <DisclaimerFooter />
      </div>
    </div>
  );
}
