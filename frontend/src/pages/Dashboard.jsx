import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Mic, Library, ScrollText, Trophy, ArrowUpRight } from "lucide-react";

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [lectures, setLectures] = useState([]);

  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
    api.listLectures().then(setLectures).catch(() => {});
  }, []);

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

      <div className="flex flex-wrap gap-3 mb-10">
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
