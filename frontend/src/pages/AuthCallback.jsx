import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/AuthContext";
import { toast } from "sonner";

/** Emergent Auth returns to /auth/callback#session_id=... — we exchange it
 *  server-side for our own JWT cookies, then land on the dashboard.
 *  REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
export default function AuthCallback() {
  const location = useLocation();
  const nav = useNavigate();
  const { refresh } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = location.hash || window.location.hash || "";
    const m = hash.match(/session_id=([^&]+)/);
    if (!m) {
      toast.error("Не удалось получить сессию Google.");
      nav("/login", { replace: true });
      return;
    }
    const sessionId = decodeURIComponent(m[1]);
    (async () => {
      try {
        await api.emergentSession(sessionId);
        // Clear the fragment so refresh doesn't retry, then load user.
        window.history.replaceState({}, "", "/");
        await refresh();
        toast.success("Вход через Google выполнен.");
        nav("/", { replace: true });
      } catch (e) {
        toast.error("Google-вход не удался.");
        nav("/login", { replace: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="paper-grain min-h-screen flex items-center justify-center">
      <div className="text-center text-[color:var(--muted)] font-mono-label">
        подтверждаем аккаунт Google…
      </div>
    </div>
  );
}
