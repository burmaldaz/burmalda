import { useState } from "react";
import { Link, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/AuthContext";
import { formatApiError } from "@/lib/api";
import { Leaf, Loader2 } from "lucide-react";
import { toast } from "sonner";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
function goToGoogle() {
  const redirectUrl = window.location.origin + "/auth/callback";
  window.location.href =
    `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
}

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

            <div className="flex items-center gap-3 my-5">
              <div className="flex-1 h-px bg-[color:var(--border)]" />
              <span className="font-mono-label">или</span>
              <div className="flex-1 h-px bg-[color:var(--border)]" />
            </div>

            <button
              type="button"
              onClick={goToGoogle}
              data-testid="google-signin"
              className="w-full inline-flex items-center justify-center gap-3 px-5 py-3 bg-[color:var(--paper)] text-[color:var(--ink)] border border-[color:var(--ink)] shadow-offset-sm hover-lift"
            >
              <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
                <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.9 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.5 5.6 29.5 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>
                <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.6 15 18.9 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.5 5.6 29.5 4 24 4 16.3 4 9.6 8.4 6.3 14.7z"/>
                <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.2 26.7 36 24 36c-5.3 0-9.7-3.1-11.3-7.6l-6.5 5C9.5 39.5 16.2 44 24 44z"/>
                <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.1-4.1 5.6l6.2 5.2C40.7 35.6 44 30.3 44 24c0-1.3-.1-2.4-.4-3.5z"/>
              </svg>
              <span>Войти через Google</span>
            </button>

            <div className="mt-6 text-center text-sm text-[color:var(--ink-soft)]">
              {mode === "register" ? (
                <>Уже есть аккаунт?{" "}
                  <Link data-testid="auth-switch-login" to="/login" className="underline decoration-dotted text-[color:var(--ink)]">Войти</Link>
                </>
              ) : (
                <>
                  <div className="mb-2">
                    <Link data-testid="link-forgot" to="/forgot-password" className="underline decoration-dotted text-[color:var(--ink)]">
                      Забыли пароль?
                    </Link>
                  </div>
                  Впервые здесь?{" "}
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
