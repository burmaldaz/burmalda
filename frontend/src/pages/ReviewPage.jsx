import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { CheckCircle2, XCircle, Repeat, PartyPopper } from "lucide-react";

export default function ReviewPage() {
  const [items, setItems] = useState(null);
  const [idx, setIdx] = useState(0);
  const [value, setValue] = useState("");
  const [feedback, setFeedback] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const list = await api.reviewDue();
      setItems(list);
      setIdx(0);
      setValue("");
      setFeedback(null);
    } catch (e) {
      toast.error("Не удалось загрузить.");
    }
  };
  useEffect(() => { load(); }, []);

  if (items === null) return <div className="p-10 font-mono-label">Загрузка…</div>;

  if (items.length === 0) {
    return (
      <div className="p-6 md:p-10 max-w-3xl" data-testid="review-page">
        <div className="font-mono-label mb-3">— Повторение</div>
        <h1 className="font-serif-display text-4xl sm:text-5xl mb-3">Всё в порядке.</h1>
        <p className="text-[color:var(--ink-soft)] mb-8">
          На сегодня карточек к повторению нет. Как только вы ошибётесь в
          каком-нибудь вопросе теста, он появится здесь — через день,
          затем через неделю, и так далее.
        </p>
        <div className="border border-[color:var(--border)] bg-[color:var(--paper)] p-12 text-center">
          <PartyPopper className="w-10 h-10 mx-auto mb-3 text-[color:var(--sage-deep)]" strokeWidth={1.25} />
          <div className="font-serif-display text-2xl mb-1">Очередь пуста</div>
          <p className="text-[color:var(--ink-soft)]">
            <Link to="/library" className="underline decoration-dotted">Откройте библиотеку</Link>, чтобы пройти новый тест.
          </p>
        </div>
      </div>
    );
  }

  const current = items[idx];
  const q = current.question;

  const answer = async () => {
    if (!value && q.type !== "short") {
      toast.error("Выберите ответ.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.reviewAnswer(current.id, value);
      setFeedback(r);
    } catch (e) {
      toast.error("Не удалось проверить.");
    } finally {
      setBusy(false);
    }
  };

  const next = () => {
    if (idx + 1 < items.length) {
      setIdx(idx + 1);
      setValue("");
      setFeedback(null);
    } else {
      load(); // refetch — some items may have new due dates now
      toast.success("Круг повторения пройден!");
    }
  };

  const typeLabel =
    q.type === "mcq" ? "Множественный выбор"
    : q.type === "tf" ? "Правда / Ложь"
    : "Короткий ответ";

  return (
    <div className="p-6 md:p-10 max-w-3xl" data-testid="review-page">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <div className="font-mono-label mb-1">— Повторение · {typeLabel}</div>
          <h1 className="font-serif-display text-3xl sm:text-4xl leading-tight">
            Карточка {idx + 1} из {items.length}
          </h1>
        </div>
        <div className="flex items-center gap-2 text-[color:var(--muted)] text-sm">
          <Repeat className="w-4 h-4" strokeWidth={1.5} />
          <span>{current.misses}× пропусков · подряд {current.streak}</span>
        </div>
      </div>

      <div className="h-1 bg-[color:var(--bg-2)] mb-6">
        <div
          className="h-1 bg-[color:var(--terracotta)] transition-all"
          style={{ width: `${((idx + (feedback ? 1 : 0)) / items.length) * 100}%` }}
        />
      </div>

      <div
        data-testid={`review-card-${current.id}`}
        className="border border-[color:var(--border)] bg-[color:var(--paper)] p-6 md:p-8"
      >
        <div className="font-serif-display text-2xl mb-5 leading-snug">
          {q.prompt}
        </div>

        {q.type === "mcq" && (
          <div className="space-y-2">
            {q.options?.map((opt) => {
              const letter = opt.trim().charAt(0);
              const active = value === letter;
              return (
                <button
                  key={opt}
                  disabled={!!feedback}
                  onClick={() => setValue(letter)}
                  data-testid={`review-option-${letter}`}
                  className={`w-full text-left px-4 py-3 border ${
                    active
                      ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]"
                      : "border-[color:var(--border)] hover:border-[color:var(--ink)] bg-[color:var(--paper)]"
                  } ${feedback ? "opacity-70" : ""}`}
                >
                  {opt}
                </button>
              );
            })}
          </div>
        )}

        {q.type === "tf" && (
          <div className="flex gap-3">
            {[{ v: "True", l: "Правда" }, { v: "False", l: "Ложь" }].map(
              ({ v, l }) => (
                <button
                  key={v}
                  disabled={!!feedback}
                  onClick={() => setValue(v)}
                  data-testid={`review-tf-${v}`}
                  className={`flex-1 px-4 py-3 border ${
                    value === v
                      ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]"
                      : "border-[color:var(--border)] hover:border-[color:var(--ink)] bg-[color:var(--paper)]"
                  } ${feedback ? "opacity-70" : ""}`}
                >
                  {l}
                </button>
              )
            )}
          </div>
        )}

        {q.type === "short" && (
          <input
            type="text"
            value={value}
            disabled={!!feedback}
            onChange={(e) => setValue(e.target.value)}
            data-testid="review-short"
            placeholder="Введите ответ…"
            className="w-full px-4 py-3 bg-[color:var(--bg)] border border-[color:var(--border)] focus:border-[color:var(--ink)] focus:outline-none text-lg"
          />
        )}

        {feedback && (
          <div
            data-testid="review-feedback"
            className={`mt-6 p-4 border ${
              feedback.is_correct
                ? "border-[color:var(--sage)]"
                : "border-[color:var(--terracotta)]"
            }`}
          >
            <div className="flex items-start gap-2">
              {feedback.is_correct ? (
                <CheckCircle2 className="w-5 h-5 text-[color:var(--sage-deep)] mt-0.5" strokeWidth={1.75} />
              ) : (
                <XCircle className="w-5 h-5 text-[color:var(--terracotta-deep)] mt-0.5" strokeWidth={1.75} />
              )}
              <div className="text-sm text-[color:var(--ink-soft)] flex-1">
                <div className="mb-1">
                  <span className="font-mono-label mr-2">Правильный</span>
                  {q.type === "tf"
                    ? feedback.correct_answer === "True" ? "Правда" : "Ложь"
                    : feedback.correct_answer}
                </div>
                {feedback.explanation && (
                  <div className="mt-2 pt-2 border-t border-[color:var(--border)]">
                    {feedback.explanation}
                  </div>
                )}
                <div className="mt-2 font-mono-label">
                  Следующий показ через {feedback.next_due_days}{" "}
                  {feedback.next_due_days === 1 ? "день" : "дн."}
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="mt-6 flex justify-end">
          {feedback ? (
            <button
              onClick={next}
              data-testid="review-next-btn"
              className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift"
            >
              {idx + 1 < items.length ? "Следующая →" : "Завершить"}
            </button>
          ) : (
            <button
              onClick={answer}
              disabled={busy}
              data-testid="review-answer-btn"
              className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--sage)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-60"
            >
              {busy ? "Проверяем…" : "Проверить"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
