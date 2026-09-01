import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import Markdown from "@/components/Markdown";
import { Sparkles, GraduationCap, ArrowLeft, Loader2, History, Printer } from "lucide-react";

export default function LecturePage() {
  const { id } = useParams();
  const nav = useNavigate();
  const [lec, setLec] = useState(null);
  const [tests, setTests] = useState([]);
  const [attempts, setAttempts] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = async () => {
    try {
      const [l, t, a] = await Promise.all([
        api.getLecture(id),
        api.listTests(id),
        api.listAttempts(id),
      ]);
      setLec(l);
      setTests(t);
      setAttempts(a);
    } catch (e) {
      toast.error("Лекция не найдена.");
      nav("/library");
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const onGenerateSummary = async () => {
    setBusy("summary");
    try {
      const updated = await api.generateSummary(id);
      setLec(updated);
      toast.success("Конспект готов.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось создать конспект.");
    } finally { setBusy(null); }
  };

  const onGenerateTest = async () => {
    setBusy("test");
    try {
      const test = await api.generateTest(id);
      toast.success("Тест готов.");
      nav(`/lecture/${id}/test/${test.id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Не удалось создать тест.");
    } finally { setBusy(null); }
  };

  if (!lec) return <div className="p-10 font-mono-label">Загрузка…</div>;

  return (
    <div className="p-6 md:p-10 max-w-7xl" data-testid="lecture-page">
      <Link to="/library" className="inline-flex items-center gap-1 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-4">
        <ArrowLeft className="w-4 h-4" strokeWidth={1.5} /> К библиотеке
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-4 mb-8">
        <div className="min-w-0">
          <div className="font-mono-label mb-2">
            {sourceLabel(lec.source_type)} · {new Date(lec.created_at).toLocaleString("ru-RU")}
            {lec.duration_sec ? ` · ${Math.round(lec.duration_sec / 60)} мин` : ""}
          </div>
          <h1 className="font-serif-display text-4xl sm:text-5xl leading-[1.05]" data-testid="lecture-title">
            {lec.title}
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            data-testid="print-pdf-btn"
            disabled={!lec.summary}
            onClick={() => window.print()}
            title="Распечатать / сохранить как PDF"
            className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            <Printer className="w-4 h-4" strokeWidth={1.5} /> PDF
          </button>
          <button
            data-testid="generate-summary-btn"
            disabled={busy || !lec.transcript}
            onClick={onGenerateSummary}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            {busy === "summary" ? (
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={1.5} />
            ) : (
              <Sparkles className="w-4 h-4" strokeWidth={1.5} />
            )}
            {lec.summary ? "Перегенерировать конспект" : "Создать конспект"}
          </button>
          <button
            data-testid="generate-test-btn"
            disabled={busy || !lec.summary}
            onClick={onGenerateTest}
            className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-50 disabled:cursor-not-allowed text-sm"
          >
            {busy === "test" ? (
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} />
            ) : (
              <GraduationCap className="w-4 h-4" strokeWidth={2} />
            )}
            Сгенерировать тест
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 border border-[color:var(--border)] bg-[color:var(--paper)]">
        <div className="p-6 md:p-8 border-b lg:border-b-0 lg:border-r border-[color:var(--border)]">
          <div className="flex items-center justify-between mb-3">
            <div className="font-mono-label">Исходный транскрипт</div>
            <div className="font-mono-label">
              {lec.transcript.split(/\s+/).filter(Boolean).length} слов
            </div>
          </div>
          <div
            data-testid="transcript-view"
            className="whitespace-pre-wrap leading-relaxed text-[color:var(--ink-soft)] max-h-[70vh] overflow-auto"
            style={{ fontSize: "1.05rem" }}
          >
            {lec.transcript || "Транскрипта пока нет."}
          </div>
        </div>

        <div className="p-6 md:p-8">
          <div className="flex items-center justify-between mb-3">
            <div className="font-mono-label">Конспект от ИИ</div>
            {lec.summary && (
              <div className="font-mono-label">Движок · {lec.llm_mode}</div>
            )}
          </div>
          {lec.summary ? (
            <div data-testid="summary-view" className="max-h-[70vh] overflow-auto">
              <Markdown text={lec.summary} />
              {lec.key_points?.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[color:var(--border)]">
                  <div className="font-mono-label mb-2">Ключевые тезисы</div>
                  <ul className="list-disc pl-5 space-y-1">
                    {lec.key_points.map((k, i) => (
                      <li key={i} className="text-[color:var(--ink-soft)]">{k}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center p-8 border border-dashed border-[color:var(--border)]">
              <Sparkles className="w-8 h-8 mx-auto mb-3 text-[color:var(--muted)]" strokeWidth={1.25} />
              <p className="text-[color:var(--ink-soft)] mb-4">
                Конспект ещё не создан. Нажмите <strong>Создать
                конспект</strong>, чтобы структурировать транскрипт.
              </p>
            </div>
          )}
        </div>
      </div>

      {(tests.length > 0 || attempts.length > 0) && (
        <div className="mt-10">
          <h2 className="font-serif-display text-2xl mb-4 flex items-center gap-2">
            <History className="w-5 h-5" strokeWidth={1.5} /> История тестов
          </h2>
          <div className="border border-[color:var(--border)] bg-[color:var(--paper)]">
            {tests.length === 0 && (
              <div className="p-6 text-[color:var(--ink-soft)]">
                Тестов ещё нет.
              </div>
            )}
            {tests.map((t) => {
              const testAttempts = attempts.filter((a) => a.test_id === t.id);
              const best = testAttempts.reduce(
                (m, a) => Math.max(m, a.score),
                testAttempts.length ? 0 : NaN
              );
              return (
                <div
                  key={t.id}
                  data-testid={`test-item-${t.id}`}
                  className="flex items-center justify-between gap-4 p-4 border-b last:border-b-0 border-[color:var(--border)]"
                >
                  <div>
                    <div className="font-serif-display text-lg">
                      Тест · {t.questions.length} вопросов
                    </div>
                    <div className="text-xs text-[color:var(--muted)] mt-0.5">
                      {new Date(t.created_at).toLocaleString("ru-RU")} ·{" "}
                      {testAttempts.length} попыт{plural(testAttempts.length)}
                      {testAttempts.length > 0 && ` · лучший ${best}%`}
                    </div>
                  </div>
                  <Link
                    to={`/lecture/${id}/test/${t.id}`}
                    data-testid={`take-test-${t.id}`}
                    className="inline-flex items-center gap-2 px-3 py-2 border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm bg-[color:var(--paper)]"
                  >
                    Пройти
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Print-only view: конспект + вопросы + ответы */}
      <div className="print-only" data-testid="print-view">
        <h1 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "26pt", margin: "0 0 8pt" }}>
          {lec.title}
        </h1>
        <div style={{ fontSize: "9pt", color: "#666", marginBottom: "16pt" }}>
          {new Date(lec.created_at).toLocaleString("ru-RU")}
        </div>
        {lec.summary && (
          <>
            <h2 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "18pt", marginTop: "12pt" }}>
              Конспект
            </h2>
            <Markdown text={lec.summary} />
            {lec.key_points?.length > 0 && (
              <>
                <h3 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "13pt", marginTop: "10pt" }}>
                  Ключевые тезисы
                </h3>
                <ul>
                  {lec.key_points.map((k, i) => <li key={i}>{k}</li>)}
                </ul>
              </>
            )}
          </>
        )}
        {tests.length > 0 && (
          <>
            <div style={{ pageBreakBefore: "always" }} />
            <h2 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "18pt", marginTop: "12pt" }}>
              Тест ({tests[0].questions.length} вопросов)
            </h2>
            <ol style={{ paddingLeft: "1.2em" }}>
              {tests[0].questions.map((q) => (
                <li key={q.id} style={{ marginBottom: "10pt" }}>
                  <div style={{ fontWeight: 600 }}>{q.prompt}</div>
                  {q.type === "mcq" && (
                    <ul style={{ listStyle: "none", padding: 0, margin: "4pt 0" }}>
                      {q.options.map((o) => <li key={o}>{o}</li>)}
                    </ul>
                  )}
                </li>
              ))}
            </ol>
            <div style={{ pageBreakBefore: "always" }} />
            <h2 style={{ fontFamily: "Cormorant Garamond, serif", fontSize: "18pt" }}>
              Ответы
            </h2>
            <ol style={{ paddingLeft: "1.2em" }}>
              {tests[0].questions.map((q) => (
                <li key={q.id} style={{ marginBottom: "6pt" }}>
                  <strong>
                    {q.type === "tf"
                      ? q.answer === "True" ? "Правда" : "Ложь"
                      : q.answer}
                  </strong>
                  {q.explanation ? ` — ${q.explanation}` : ""}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}

function sourceLabel(s) {
  return s === "mic" ? "микрофон" : s === "paste" ? "вставка" : "загрузка";
}

function plural(n) {
  const m = n % 10, k = n % 100;
  if (m === 1 && k !== 11) return "ка";
  if ([2, 3, 4].includes(m) && ![12, 13, 14].includes(k)) return "ки";
  return "ок";
}
