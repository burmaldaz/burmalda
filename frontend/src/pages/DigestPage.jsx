import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Send, Mail, Loader2, Copy, Calendar } from "lucide-react";

export default function DigestPage() {
  const [digest, setDigest] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.digestPreview().then(setDigest).catch(() => toast.error("Не удалось собрать дайджест."));
    api.config().then(setCfg).catch(() => {});
  }, []);

  const send = async () => {
    setBusy(true);
    try {
      const r = await api.digestSend();
      toast.success(`Отправлено на ${r.to}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось отправить.");
    } finally { setBusy(false); }
  };

  const copyHtml = async () => {
    try {
      await navigator.clipboard.writeText(digest.html);
      toast.success("HTML скопирован в буфер.");
    } catch (_) { toast.error("Не удалось скопировать."); }
  };

  return (
    <div className="p-6 md:p-10 max-w-5xl" data-testid="digest-page">
      <div className="flex items-start justify-between gap-4 mb-8 flex-wrap">
        <div>
          <div className="font-mono-label mb-3">— Еженедельный дайджест</div>
          <h1 className="font-serif-display text-4xl sm:text-5xl leading-tight">
            Как прошла неделя.
          </h1>
          <p className="text-[color:var(--ink-soft)] mt-3 max-w-2xl">
            Сводка новых лекций и карточек к повторению за последние 7 дней.
            {cfg?.digest_email_fallback && (
              <>
                {" "}Тестовый режим Resend — письма уходят на{" "}
                <span className="font-mono-label text-[color:var(--ink)]">
                  {cfg.digest_email_fallback}
                </span>{". "}
              </>
            )}
            Расписание:
            <span className="inline-flex items-center gap-1 ml-1 font-mono-label text-[color:var(--ink)]">
              <Calendar className="w-3.5 h-3.5" strokeWidth={1.5} />
              {cfg?.digest_schedule || "—"}
            </span>
            .
          </p>
        </div>
        <div className="flex gap-2">
          <button
            data-testid="digest-copy-btn"
            onClick={copyHtml}
            disabled={!digest}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm disabled:opacity-50"
          >
            <Copy className="w-4 h-4" strokeWidth={1.5} /> Скопировать HTML
          </button>
          <button
            data-testid="digest-send-btn"
            onClick={send}
            disabled={busy || !cfg?.email_enabled}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} />
                  : <Send className="w-4 h-4" strokeWidth={2} />}
            {cfg?.email_enabled ? "Отправить себе" : "Email не настроен"}
          </button>
        </div>
      </div>

      {digest ? (
        <div className="grid grid-cols-2 md:grid-cols-4 border border-[color:var(--border)] bg-[color:var(--paper)] mb-8">
          {[
            { label: "Новых лекций", value: digest.new_lectures },
            { label: "К повторению", value: digest.due_count },
            { label: "Средний балл", value: `${digest.avg_score}%` },
            { label: "Email", value: cfg?.email_enabled ? "ON" : "OFF" },
          ].map((t, i) => (
            <div key={t.label} className={`p-5 ${i < 3 ? "md:border-r border-[color:var(--border)]" : ""} ${i < 2 ? "border-b md:border-b-0 border-[color:var(--border)]" : ""}`}>
              <div className="font-mono-label mb-2">{t.label}</div>
              <div className="font-serif-display text-3xl">{t.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="p-10 font-mono-label">Собираем дайджест…</div>
      )}

      <div className="mb-3 flex items-baseline justify-between">
        <div className="font-mono-label flex items-center gap-2">
          <Mail className="w-4 h-4" strokeWidth={1.5} /> Предпросмотр письма
        </div>
        <div className="font-mono-label">Тема · {digest?.subject || "…"}</div>
      </div>
      <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] shadow-offset overflow-hidden">
        {digest ? (
          <iframe
            data-testid="digest-preview-frame"
            title="digest-preview"
            srcDoc={digest.html}
            className="w-full min-h-[720px] bg-white"
          />
        ) : null}
      </div>
    </div>
  );
}
