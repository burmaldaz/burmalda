import { useState } from "react";
import { Link, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/AuthContext";
import { formatApiError } from "@/lib/api";
import { Leaf, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AuthPage({ mode = "login" }) {
  const { user, login, register } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  if (user && user !== false) {
    const to = location.state?.from || "/";
    return <Navigate to={to} replace />;
  }

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      if (mode === "register") {
        await register(email.trim().toLowerCase(), password, name.trim() || null);
        toast.success(`Добро пожаловать, ${name || email}!`);
      } else {
        await login(email.trim().toLowerCase(), password);
        toast.success("С возвращением.");
      }
      nav(location.state?.from || "/", { replace: true });
    } catch (e) {
      setErr(formatApiError(e?.response?.data?.detail, "Не удалось войти."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="paper-grain min-h-screen relative" data-testid="auth-page">
      <div className="relative z-10 flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 justify-center mb-8">
            <div className="w-10 h-10 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
              <Leaf className="w-5 h-5 text-white" strokeWidth={1.75} />
            </div>
            <div className="font-serif-display text-3xl leading-none">upsidestudy</div>
          </div>

          <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 md:p-8 shadow-offset">
            <div className="font-mono-label mb-2">
              {mode === "register" ? "— Регистрация" : "— Вход"}
            </div>
            <h1 className="font-serif-display text-3xl md:text-4xl mb-6 leading-tight">
              {mode === "register" ? "Начнём с вашей почты." : "С возвращением."}
            </h1>

            <form onSubmit={submit} className="space-y-4">
              {mode === "register" && (
                <div>
                  <label className="block font-mono-label mb-1">Имя (необязательно)</label>
                  <input
                    data-testid="auth-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                    placeholder="как к вам обращаться"
                  />
                </div>
              )}
              <div>
                <label className="block font-mono-label mb-1">Почта</label>
                <input
                  data-testid="auth-email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                  placeholder="you@university.edu"
                />
              </div>
              <div>
                <label className="block font-mono-label mb-1">Пароль</label>
                <input
                  data-testid="auth-password"
                  type="password"
                  required
                  minLength={6}
                  autoComplete={mode === "register" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                  placeholder="минимум 6 символов"
                />
              </div>

              {err && (
                <div data-testid="auth-error" className="text-sm text-[color:var(--terracotta-deep)] border border-[color:var(--terracotta)] p-2">
                  {err}
                </div>
              )}

              <button
                data-testid="auth-submit"
                type="submit"
                disabled={busy}
                className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-60 mt-2"
              >
                {busy && <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} />}
                {mode === "register" ? "Создать аккаунт" : "Войти"}
              </button>
            </form>

            <div className="mt-6 text-center text-sm text-[color:var(--ink-soft)]">
              {mode === "register" ? (
                <>Уже есть аккаунт?{" "}
                  <Link data-testid="auth-switch-login" to="/login" className="underline decoration-dotted text-[color:var(--ink)]">Войти</Link>
                </>
              ) : (
                <>Впервые здесь?{" "}
                  <Link data-testid="auth-switch-register" to="/register" className="underline decoration-dotted text-[color:var(--ink)]">Регистрация</Link>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
