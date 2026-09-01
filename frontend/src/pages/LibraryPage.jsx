import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Trash2, ArrowUpRight, Mic } from "lucide-react";

export default function LibraryPage() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = () => {
    setLoading(true);
    api.listLectures().then(setItems).finally(() => setLoading(false));
  };

  useEffect(() => { refresh(); }, []);

  const remove = async (id) => {
    if (!confirm("Удалить эту лекцию вместе с тестами?")) return;
    await api.deleteLecture(id);
    toast.success("Лекция удалена");
    refresh();
  };

  return (
    <div className="p-6 md:p-10 max-w-6xl" data-testid="library-page">
      <div className="flex items-end justify-between mb-8">
        <div>
          <div className="font-mono-label mb-3">— Архив</div>
          <h1 className="font-serif-display text-4xl sm:text-5xl">Библиотека</h1>
        </div>
        <Link
          to="/record"
          data-testid="library-new-btn"
          className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm"
        >
          <Mic className="w-4 h-4" strokeWidth={1.5} /> Новая лекция
        </Link>
      </div>

      {loading ? (
        <div className="font-mono-label">Загрузка…</div>
      ) : items.length === 0 ? (
        <div className="border border-[color:var(--border)] bg-[color:var(--paper)] p-12 text-center">
          <div className="font-mono-label mb-3">Пока пусто</div>
          <p className="text-[color:var(--ink-soft)] max-w-md mx-auto">
            Как только вы запишете или вставите первую лекцию, она появится
            здесь — вместе с конспектами и историей тестов.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {items.map((l) => (
            <div
              key={l.id}
              data-testid={`library-card-${l.id}`}
              className="border border-[color:var(--border)] bg-[color:var(--paper)] p-6 flex flex-col hover-lift"
            >
              <div className="flex items-start justify-between mb-3 gap-2">
                <div className="font-mono-label">{sourceLabel(l.source_type)}</div>
                <button
                  data-testid={`delete-${l.id}`}
                  onClick={() => remove(l.id)}
                  className="text-[color:var(--muted)] hover:text-[color:var(--terracotta)]"
                >
                  <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>
              <Link to={`/lecture/${l.id}`} className="flex-1">
                <div className="font-serif-display text-2xl leading-tight mb-2">
                  {l.title}
                </div>
                <div className="text-sm text-[color:var(--ink-soft)] line-clamp-3 leading-relaxed mb-3">
                  {l.transcript
                    ? l.transcript.slice(0, 180) +
                      (l.transcript.length > 180 ? "…" : "")
                    : "Транскрипта ещё нет."}
                </div>
              </Link>
              <div className="flex items-center justify-between mt-auto pt-3 border-t border-[color:var(--border)]">
                <div className="text-xs text-[color:var(--muted)]">
                  {new Date(l.created_at).toLocaleDateString("ru-RU")} ·{" "}
                  {l.summary ? "Конспект готов" : "Без конспекта"}
                </div>
                <Link
                  to={`/lecture/${l.id}`}
                  className="inline-flex items-center gap-1 text-sm text-[color:var(--ink)]"
                >
                  Открыть <ArrowUpRight className="w-4 h-4" strokeWidth={1.5} />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function sourceLabel(s) {
  return s === "mic" ? "микрофон" : s === "paste" ? "вставка" : "загрузка";
}
