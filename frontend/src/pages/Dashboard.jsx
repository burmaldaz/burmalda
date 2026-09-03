import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Mic, Library, ScrollText, Trophy, ArrowUpRight, Flame, Snowflake } from "lucide-react";
import { toast } from "sonner";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lectures, setLectures] = useState([]);
  const [freezing, setFreezing] = useState(false);

  const load = () => {
    api.stats().then(setStats).catch(() => {});
    api.listLectures().then(setLectures).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const freeze = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!stats?.can_freeze) return;
    setFreezing(true);
    try {
      await api.freezeStreak();
      toast.success("Серия заморожена на 2 дня.");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Не получилось.");
    } finally {
      setFreezing(false);
    }
  };

  const tiles = [
    { key: "lectures", label: "Лекций", icon: ScrollText, value: stats?.lectures ?? "—" },
    { key: "tests", label: "Тестов создано", icon: Library, value: stats?.tests ?? "—" },
    { key: "attempts", label: "Попыток", icon: Mic, value: stats?.attempts ?? "—" },
    { key: "avg_score", label: "Средний балл", icon: Trophy, value: stats ? `${stats.avg_score}%` : "—" },
  ];

  return (
    <div className="p-6 md:p-10 max-w-6xl" data-testid="dashboard-page">
      <div className="flex items-start justify-between gap-6 mb-10">
        <div>
          <div className="font-mono-label mb-3">— Помощник в учёбе</div>
          <h1 className="font-serif-display text-4xl sm:text-5xl lg:text-6xl leading-[1.05]">
            Превращаем устные лекции<br /> в конспекты, к которым возвращаются.
          </h1>
          <p className="mt-4 max-w-xl text-[color:var(--ink-soft)] text-base leading-relaxed">
            Записывайте лекции на английском вживую с микрофона или
            загружайте готовый транскрипт. Мы сохраним исходный текст,
            подготовим структурированный конспект и проверим знания
            смешанным тестом: множественный выбор, правда/ложь и короткие
            ответы.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-8">
        <Link
          to="/record"
          data-testid="cta-record"
          className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset hover-lift font-medium"
        >
          <Mic className="w-4 h-4" strokeWidth={2} />
          Начать запись
        </Link>
        <Link
          to="/library"
          data-testid="cta-library"
          className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--paper)] text-[color:var(--ink)] border border-[color:var(--ink)] shadow-offset hover-lift font-medium"
        >
          <Library className="w-4 h-4" strokeWidth={2} />
          Открыть библиотеку
        </Link>
      </div>

      {/* Streak card */}
      <Link
        to="/review"
        data-testid="streak-card"
        className="group block mb-10 border border-[color:var(--ink)] bg-[color:var(--paper)] shadow-offset hover-lift"
      >
        <div className="flex flex-col md:flex-row items-stretch">
          <div className={`flex items-center justify-center p-6 md:p-8 md:w-56 border-b md:border-b-0 md:border-r border-[color:var(--ink)] ${
              stats?.streak > 0 ? "bg-[color:var(--terracotta)]" : "bg-[color:var(--bg-2)]"
            }`}>
            <div className="relative">
              <Flame
                className={`w-16 h-16 ${
                  stats?.streak > 0 ? "text-white" : "text-[color:var(--muted)]"
                } ${stats?.reviewed_today ? "flame-glow" : ""}`}
                strokeWidth={1.5}
                fill={stats?.streak > 0 ? "currentColor" : "none"}
                data-testid="streak-flame"
              />
              {stats?.streak > 0 && (
                <div
                  className="absolute -bottom-2 -right-3 bg-[color:var(--ink)] text-[color:var(--paper)] px-2 py-0.5 text-sm font-mono-label border border-[color:var(--paper)]"
                  data-testid="streak-badge"
                >
                  {stats.streak}
                </div>
              )}
            </div>
          </div>
          <div className="flex-1 p-6 md:p-8 flex flex-col justify-center">
            <div className="font-mono-label mb-2">— Серия повторений</div>
            <div className="font-serif-display text-3xl md:text-4xl leading-tight">
              {stats == null
                ? "…"
                : stats.streak === 0
                ? "Начнём новую цепочку?"
                : `${stats.streak} ${daysWord(stats.streak)} подряд`}
            </div>
            <div className="text-[color:var(--ink-soft)] mt-2">
              {stats?.reviewed_today
                ? "Сегодня уже занимались — серия не сгорит."
                : stats?.streak > 0
                ? "Ещё не занимались сегодня — не потеряйте серию."
                : "Одна карточка в день — и цепочка растёт."}
            </div>
            <div className="mt-4 flex flex-wrap gap-2 items-center">
              <button
                onClick={freeze}
                disabled={!stats?.can_freeze || freezing}
                data-testid="freeze-streak-btn"
                className={`inline-flex items-center gap-2 px-3 py-2 border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm ${
                  stats?.can_freeze
                    ? "bg-[color:var(--paper)] text-[color:var(--ink)]"
                    : "bg-[color:var(--bg-2)] text-[color:var(--ink)] opacity-90 cursor-not-allowed"
                }`}
              >
                <Snowflake className="w-4 h-4" strokeWidth={1.5} />
                {stats?.can_freeze
                  ? "Заморозить на 2 дня"
                  : `Можно через ${stats?.next_freeze_in_days ?? "—"} дн.`}
              </button>
              {stats?.freeze_dates?.length > 0 && (
                <span className="font-mono-label" data-testid="freeze-history">
                  Последняя · {stats.freeze_dates[0]}
                </span>
              )}
            </div>
          </div>
        </div>
      </Link>

      <div className="grid grid-cols-2 md:grid-cols-4 border border-[color:var(--border)] bg-[color:var(--paper)] mb-10">
        {tiles.map(({ key, label, icon: Icon, value }, i) => (
          <div
            key={key}
            data-testid={`stat-${key}`}
            className={`p-6 ${i < 3 ? "md:border-r border-[color:var(--border)]" : ""} ${i < 2 ? "border-b md:border-b-0 border-[color:var(--border)]" : ""}`}
          >
            <div className="flex items-center justify-between mb-3">
              <Icon className="w-4 h-4 text-[color:var(--muted)]" strokeWidth={1.5} />
              <span className="font-mono-label">{label}</span>
            </div>
            <div className="font-serif-display text-4xl">{value}</div>
          </div>
        ))}
      </div>

      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-serif-display text-2xl">Недавние лекции</h2>
        <Link to="/library" className="text-sm underline decoration-dotted text-[color:var(--ink-soft)] hover:text-[color:var(--ink)]" data-testid="link-all-lectures">
          Все лекции
        </Link>
      </div>

      <div className="border border-[color:var(--border)] bg-[color:var(--paper)]">
        {lectures.length === 0 && (
          <div className="p-10 text-center" data-testid="empty-lectures">
            <div className="font-mono-label mb-3">Архив пуст</div>
            <p className="text-[color:var(--ink-soft)] max-w-md mx-auto mb-5">
              Пока ни одной сохранённой лекции. Начните с записи с микрофона —
              транскрипт появится здесь за секунды.
            </p>
            <Link
              to="/record"
              data-testid="empty-cta"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift"
            >
              <Mic className="w-4 h-4" strokeWidth={2} /> Записать сейчас
            </Link>
          </div>
        )}
        {lectures.slice(0, 6).map((lec) => (
          <Link
            key={lec.id}
            to={`/lecture/${lec.id}`}
            data-testid={`lecture-row-${lec.id}`}
            className="flex items-center justify-between gap-4 p-5 border-b last:border-b-0 border-[color:var(--border)] hover:bg-[color:var(--bg-2)] transition-colors"
          >
            <div className="min-w-0">
              <div className="font-serif-display text-xl truncate">{lec.title}</div>
              <div className="flex gap-3 mt-1 text-xs text-[color:var(--muted)]">
                <span className="font-mono-label">{sourceLabel(lec.source_type)}</span>
                <span>{new Date(lec.created_at).toLocaleString("ru-RU")}</span>
                <span>{lec.summary ? "Конспект готов" : "Ждёт конспекта"}</span>
              </div>
            </div>
            <ArrowUpRight className="w-4 h-4 text-[color:var(--muted)]" strokeWidth={1.5} />
          </Link>
        ))}
      </div>
    </div>
  );
}

function sourceLabel(s) {
  return s === "mic" ? "микрофон" : s === "paste" ? "вставка" : "загрузка";
}

function daysWord(n) {
  const m = n % 10, k = n % 100;
  if (m === 1 && k !== 11) return "день";
  if ([2, 3, 4].includes(m) && ![12, 13, 14].includes(k)) return "дня";
  return "дней";
}
