import { useState } from "react";
import { Link } from "react-router-dom";
import { api, formatApiError } from "@/lib/api";
import { Leaf, Loader2, Mail, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch (err) {
      toast.error(formatApiError(err?.response?.data?.detail));
    } finally { setBusy(false); }
  };

  return (
    <div className="paper-grain min-h-screen relative" data-testid="forgot-page">
      <div className="relative z-10 flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="flex items-center gap-2 justify-center mb-8">
            <div className="w-10 h-10 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
              <Leaf className="w-5 h-5 text-white" strokeWidth={1.75} />
            </div>
            <div className="font-serif-display text-3xl leading-none">upsidestudy</div>
          </div>

          <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 md:p-8 shadow-offset">
            <div className="font-mono-label mb-2">— Восстановление пароля</div>
            {sent ? (
              <>
                <h1 className="font-serif-display text-3xl mb-3 leading-tight">
                  Проверьте почту.
                </h1>
                <p className="text-[color:var(--ink-soft)] mb-6 leading-relaxed">
                  Если такой аккаунт существует, мы отправили письмо со
                  ссылкой на сброс пароля. Ссылка живёт один час.
                </p>
                <Link
                  to="/login"
                  data-testid="forgot-back-login"
                  className="inline-flex items-center gap-2 px-4 py-2 border border-[color:var(--ink)] shadow-offset-sm hover-lift bg-[color:var(--paper)] text-sm"
                >
                  <ArrowLeft className="w-4 h-4" strokeWidth={1.5} /> Вернуться ко входу
                </Link>
              </>
            ) : (
              <>
                <h1 className="font-serif-display text-3xl mb-3 leading-tight">
                  Ничего страшного.
                </h1>
                <p className="text-[color:var(--ink-soft)] mb-6">
                  Введите свою почту — пришлём ссылку для восстановления.
                </p>
                <form onSubmit={submit} className="space-y-4">
                  <div>
                    <label className="block font-mono-label mb-1">Почта</label>
                    <input
                      data-testid="forgot-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full px-3 py-2.5 border border-[color:var(--ink)] bg-[color:var(--paper)] focus:outline-none focus:shadow-offset-sm"
                      placeholder="you@university.edu"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy}
                    data-testid="forgot-submit"
                    className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-60"
                  >
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} /> : <Mail className="w-4 h-4" strokeWidth={2} />}
                    Отправить ссылку
                  </button>
                </form>
                <div className="mt-5 text-center text-sm">
                  <Link data-testid="forgot-to-login" to="/login" className="underline decoration-dotted text-[color:var(--ink-soft)] hover:text-[color:var(--ink)]">
                    Вспомнили пароль? Войти
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
