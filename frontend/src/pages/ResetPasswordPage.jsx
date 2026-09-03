import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { useAuth } from "@/hooks/AuthContext";
import { Leaf, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { refresh } = useAuth();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (password !== confirm) {
      setErr("Пароли не совпадают.");
      return;
    }
    if (!token) {
      setErr("Ссылка неверная — нет токена.");
      return;
    }
    setBusy(true);
    try {
      await api.resetPassword(token, password);
      await refresh();
      toast.success("Пароль обновлён. Вход выполнен.");
      nav("/", { replace: true });
    } catch (e) {
      setErr(formatApiError(e?.response?.data?.detail, "Не удалось обновить пароль."));
    } finally { setBusy(false); }
  };

  return (
    <div className="paper-grain min-h-screen relative" data-testid="reset-page">
      <div className="relative z-10 flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 justify-center mb-8">
            <div className="w-10 h-10 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
              <Leaf className="w-5 h-5 text-white" strokeWidth={1.75} />
            </div>
            <div className="font-serif-display text-3xl leading-none">upsidestudy</div>
          </div>
          <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 md:p-8 shadow-offset">
            <div className="font-mono-label mb-2">— Новый пароль</div>
            <h1 className="font-serif-display text-3xl mb-6 leading-tight">
              Задайте новый пароль.
            </h1>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="block font-mono-label mb-1">Новый пароль</label>
                <input
                  data-testid="reset-password"
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                  placeholder="минимум 6 символов"
                />
              </div>
              <div>
                <label className="block font-mono-label mb-1">Ещё раз</label>
                <input
                  data-testid="reset-confirm"
                  type="password"
                  required
                  minLength={6}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                  placeholder="повторите"
                />
              </div>
              {err && (
                <div data-testid="reset-error" className="text-sm text-[color:var(--terracotta-deep)] border border-[color:var(--terracotta)] p-2">
                  {err}
                </div>
              )}
              <button
                type="submit"
                disabled={busy}
                data-testid="reset-submit"
                className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-60"
              >
                {busy && <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} />}
                Сохранить пароль
              </button>
            </form>
            <div className="mt-5 text-center text-sm">
              <Link to="/login" className="underline decoration-dotted text-[color:var(--ink-soft)] hover:text-[color:var(--ink)]">
                Вернуться ко входу
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
