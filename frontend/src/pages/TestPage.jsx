import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { ArrowLeft, CheckCircle2, XCircle, RotateCcw, Trophy } from "lucide-react";

export default function TestPage() {
  const { id, testId } = useParams();
  const nav = useNavigate();
  const [test, setTest] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.getTest(testId).then(setTest).catch(() => {
      toast.error("Тест не найден");
      nav(`/lecture/${id}`);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testId]);

  const setAns = (qid, v) => setAnswers((a) => ({ ...a, [qid]: v }));

  const progress = useMemo(() => {
    if (!test) return 0;
    const answered = test.questions.filter((q) => (answers[q.id] ?? "").toString().trim() !== "").length;
    return Math.round((answered / test.questions.length) * 100);
  }, [test, answers]);

  const submit = async () => {
    if (!test) return;
    if (progress < 100) {
      const ok = confirm("Есть незаполненные вопросы. Всё равно отправить?");
      if (!ok) return;
    }
    setSubmitting(true);
    try {
      const arr = test.questions.map((q) => ({
        question_id: q.id,
        response: answers[q.id] ?? "",
      }));
      const r = await api.gradeTest(test.id, arr);
      setResult(r);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      toast.error("Не удалось проверить ответы.");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => { setResult(null); setAnswers({}); };

  if (!test) return <div className="p-10 font-mono-label">Загрузка теста…</div>;

  return (
    <div className="p-6 md:p-10 max-w-4xl" data-testid="test-page">
      <Link to={`/lecture/${id}`} className="inline-flex items-center gap-1 text-sm text-[color:var(--muted)] hover:text-[color:var(--ink)] mb-4">
        <ArrowLeft className="w-4 h-4" strokeWidth={1.5} /> К лекции
      </Link>

      {result ? (
        <ResultView result={result} test={test} onRetake={reset} />
      ) : (
        <>
          <div className="mb-6">
            <div className="font-mono-label mb-2">— Проверка знаний</div>
            <h1 className="font-serif-display text-4xl sm:text-5xl leading-tight">
              {test.questions.length} вопросов.
            </h1>
            <div className="mt-4 flex items-center gap-4">
              <div className="flex-1 h-1 bg-[color:var(--bg-2)]">
                <div
                  className="h-1 bg-[color:var(--terracotta)] transition-all"
                  style={{ width: `${progress}%` }}
                  data-testid="progress-bar"
                />
              </div>
              <div className="font-mono-label">{progress}%</div>
            </div>
          </div>

          <div className="space-y-5">
            {test.questions.map((q, idx) => (
              <QuestionCard
                key={q.id}
                idx={idx}
                q={q}
                value={answers[q.id] ?? ""}
                onChange={(v) => setAns(q.id, v)}
              />
            ))}
          </div>

          <div className="mt-8 flex justify-end">
            <button
              data-testid="submit-test-btn"
              onClick={submit}
              disabled={submitting}
              className="inline-flex items-center gap-2 px-6 py-3 bg-[color:var(--sage)] text-white border border-[color:var(--ink)] shadow-offset hover-lift disabled:opacity-60"
            >
              {submitting ? "Проверяем…" : "Отправить ответы"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

const typeLabel = (t) =>
  t === "mcq" ? "Множественный выбор"
  : t === "tf" ? "Правда / Ложь"
  : "Короткий ответ";

function QuestionCard({ idx, q, value, onChange }) {
  return (
    <div
      data-testid={`question-${q.id}`}
      className="border border-[color:var(--border)] bg-[color:var(--paper)] p-6"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono-label">
          В{idx + 1} · {typeLabel(q.type)}
        </div>
      </div>
      <div className="font-serif-display text-2xl mb-4 leading-snug">{q.prompt}</div>

      {q.type === "mcq" && (
        <div className="space-y-2">
          {q.options?.map((opt) => {
            const letter = opt.trim().charAt(0);
            const active = value === letter;
            return (
              <button
                type="button"
                key={opt}
                data-testid={`option-${q.id}-${letter}`}
                onClick={() => onChange(letter)}
                className={`w-full text-left px-4 py-3 border transition-all ${
                  active
                    ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]"
                    : "border-[color:var(--border)] hover:border-[color:var(--ink)] bg-[color:var(--paper)]"
                }`}
              >
                {opt}
              </button>
            );
          })}
        </div>
      )}

      {q.type === "tf" && (
        <div className="flex gap-3">
          {[
            { v: "True", label: "Правда" },
            { v: "False", label: "Ложь" },
          ].map(({ v, label }) => (
            <button
              type="button"
              key={v}
              data-testid={`tf-${q.id}-${v}`}
              onClick={() => onChange(v)}
              className={`flex-1 px-4 py-3 border ${
                value === v
                  ? "border-[color:var(--ink)] bg-[color:var(--ink)] text-[color:var(--paper)]"
                  : "border-[color:var(--border)] hover:border-[color:var(--ink)] bg-[color:var(--paper)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {q.type === "short" && (
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={`short-${q.id}`}
          placeholder="Введите ответ…"
          className="w-full px-4 py-3 bg-[color:var(--bg)] border border-[color:var(--border)] focus:border-[color:var(--ink)] focus:outline-none text-lg"
        />
      )}
    </div>
  );
}

function ResultView({ result, test, onRetake }) {
  const map = Object.fromEntries(test.questions.map((q) => [q.id, q]));
  return (
    <div data-testid="result-view">
      <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-8 shadow-offset flex flex-col md:flex-row items-center justify-between gap-6 mb-8">
        <div>
          <div className="font-mono-label mb-2">— Ваш результат</div>
          <div className="font-serif-display text-6xl leading-none" data-testid="score-value">
            {result.score}%
          </div>
          <div className="mt-2 text-[color:var(--ink-soft)]">
            {result.correct} из {result.total} — верно
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="w-24 h-24 border-2 border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)]">
            <Trophy className="w-10 h-10 text-white" strokeWidth={1.5} />
          </div>
          <button
            onClick={onRetake}
            data-testid="retake-btn"
            className="inline-flex items-center gap-2 px-4 py-2 border border-[color:var(--ink)] shadow-offset-sm hover-lift bg-[color:var(--paper)]"
          >
            <RotateCcw className="w-4 h-4" strokeWidth={1.5} /> Пройти ещё раз
          </button>
        </div>
      </div>

      <div className="space-y-4">
        {result.graded.map((g, idx) => {
          const q = map[g.question_id];
          const correctLabel =
            q?.type === "tf"
              ? g.correct_answer === "True" ? "Правда" : "Ложь"
              : g.correct_answer;
          const respLabel =
            q?.type === "tf" && g.response
              ? g.response === "True" ? "Правда" : "Ложь"
              : g.response;
          return (
            <div
              key={g.question_id}
              data-testid={`review-${g.question_id}`}
              className={`border p-6 bg-[color:var(--paper)] ${
                g.is_correct
                  ? "border-[color:var(--sage)]"
                  : "border-[color:var(--terracotta)]"
              }`}
            >
              <div className="flex items-start gap-3">
                {g.is_correct ? (
                  <CheckCircle2 className="w-5 h-5 mt-1 text-[color:var(--sage-deep)]" strokeWidth={1.75} />
                ) : (
                  <XCircle className="w-5 h-5 mt-1 text-[color:var(--terracotta-deep)]" strokeWidth={1.75} />
                )}
                <div className="flex-1">
                  <div className="font-mono-label mb-1">В{idx + 1}</div>
                  <div className="font-serif-display text-xl mb-3">{q?.prompt}</div>
                  <div className="text-sm text-[color:var(--ink-soft)]">
                    <div>
                      <span className="font-mono-label mr-2">Ваш ответ</span>
                      {respLabel || <em className="text-[color:var(--muted)]">— пусто —</em>}
                    </div>
                    <div className="mt-1">
                      <span className="font-mono-label mr-2">Правильный</span>
                      {correctLabel}
                    </div>
                    {g.explanation && (
                      <div className="mt-2 pt-2 border-t border-[color:var(--border)] text-[color:var(--ink-soft)]">
                        {g.explanation}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
