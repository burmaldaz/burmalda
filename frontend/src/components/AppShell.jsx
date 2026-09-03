import { Outlet, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Library, Mic, LayoutDashboard, Leaf, Repeat, Mail, Sun, Moon, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import useTheme from "@/hooks/useTheme";
import { useAuth } from "@/hooks/AuthContext";

const nav = [
  { to: "/", label: "Обзор", icon: LayoutDashboard, testId: "nav-overview" },
  { to: "/record", label: "Новая лекция", icon: Mic, testId: "nav-record" },
  { to: "/library", label: "Библиотека", icon: Library, testId: "nav-library" },
  { to: "/review", label: "Повторение", icon: Repeat, testId: "nav-review" },
  { to: "/digest", label: "Дайджест", icon: Mail, testId: "nav-digest" },
];

export default function AppShell() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [cfg, setCfg] = useState(null);
  const [reviewStats, setReviewStats] = useState({ due: 0, total: 0 });
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();

  useEffect(() => {
    api.config().then(setCfg).catch(() => {});
    const load = () => api.reviewStats().then(setReviewStats).catch(() => {});
    load();
    const iv = setInterval(load, 30000);
    return () => clearInterval(iv);
  }, [pathname]);

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="paper-grain min-h-screen relative">
      <div className="relative z-10 flex min-h-screen">
        <aside
          className="hidden md:flex w-64 flex-col border-r border-[color:var(--border)] bg-[color:var(--paper)]"
          data-testid="app-sidebar"
        >
          <div className="p-6 border-b border-[color:var(--border)] flex items-start justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
                <Leaf className="w-4 h-4 text-white" strokeWidth={1.75} />
              </div>
              <div>
                <div className="font-serif-display text-xl leading-none">
                  upsidestudy
                </div>
                <div className="font-mono-label mt-1">Помощник по лекциям</div>
              </div>
            </div>
            <button
              onClick={toggle}
              data-testid="theme-toggle"
              title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
              className="border border-[color:var(--border)] hover:border-[color:var(--ink)] w-8 h-8 flex items-center justify-center"
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4" strokeWidth={1.5} />
              ) : (
                <Moon className="w-4 h-4" strokeWidth={1.5} />
              )}
            </button>
          </div>

          <nav className="flex-1 p-3">
            {nav.map(({ to, label, icon: Icon, testId }) => {
              const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  data-testid={testId}
                  end={to === "/"}
                  className={`flex items-center gap-3 px-4 py-3 mb-1 border transition-all ${
                    active
                      ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                      : "border-transparent hover:border-[color:var(--border)] text-[color:var(--ink-soft)] hover:text-[color:var(--ink)]"
                  }`}
                >
                  <Icon className="w-4 h-4" strokeWidth={1.5} />
                  <span className="text-sm">{label}</span>
                  {to === "/review" && reviewStats.due > 0 && (
                    <span
                      data-testid="review-due-badge"
                      className={`ml-auto text-[10px] px-1.5 py-0.5 border ${
                        active
                          ? "border-[color:var(--paper)] text-[color:var(--paper)]"
                          : "border-[color:var(--terracotta)] text-[color:var(--terracotta-deep)] bg-[color:var(--paper)]"
                      }`}
                    >
                      {reviewStats.due}
                    </span>
                  )}
                </NavLink>
              );
            })}
          </nav>

          <div className="p-4 border-t border-[color:var(--border)]">
            <div className="font-mono-label">Аккаунт</div>
            <div className="text-sm mt-1 text-[color:var(--ink)] truncate" data-testid="user-email">
              {user?.email || "—"}
            </div>
            <div className="flex items-center justify-between mt-2">
              <div className="text-xs text-[color:var(--muted)]">
                {cfg?.llm_mode === "deepseek" ? "DeepSeek" : "Gemini Flash"}
                {cfg?.email_enabled && " · Resend"}
              </div>
              <button
                onClick={onLogout}
                data-testid="logout-btn"
                title="Выйти"
                className="text-[color:var(--muted)] hover:text-[color:var(--terracotta)] p-1 border border-transparent hover:border-[color:var(--border)]"
              >
                <LogOut className="w-4 h-4" strokeWidth={1.5} />
              </button>
            </div>
            {cfg?.is_mocked && (
              <div
                className="mt-2 text-[11px] px-2 py-1 border border-[color:var(--terracotta)] text-[color:var(--terracotta-deep)] inline-block leading-tight"
                data-testid="llm-mocked-badge"
              >
                ЗАГЛУШКА · добавьте DEEPSEEK_API_KEY
              </div>
            )}
          </div>
        </aside>

        {/* Mobile top-nav */}
        <div className="md:hidden fixed top-0 left-0 right-0 z-20 bg-[color:var(--paper)] border-b border-[color:var(--border)] p-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
              <Leaf className="w-3.5 h-3.5 text-white" strokeWidth={1.75} />
            </div>
            <div className="font-serif-display text-lg leading-none">upsidestudy</div>
          </div>
          <div className="flex gap-1">
            <button onClick={toggle} data-testid="theme-toggle-mobile" className="p-2 border border-[color:var(--border)]">
              {theme === "dark" ? <Sun className="w-4 h-4" strokeWidth={1.5} /> : <Moon className="w-4 h-4" strokeWidth={1.5} />}
            </button>
            {nav.map(({ to, icon: Icon, testId }) => {
              const active = to === "/" ? pathname === "/" : pathname.startsWith(to);
              return (
                <NavLink
                  key={to}
                  to={to}
                  data-testid={`${testId}-mobile`}
                  end={to === "/"}
                  className={`p-2 border ${
                    active
                      ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                      : "border-[color:var(--border)]"
                  }`}
                >
                  <Icon className="w-4 h-4" strokeWidth={1.5} />
                </NavLink>
              );
            })}
          </div>
        </div>

        <main className="flex-1 md:pt-0 pt-16">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
