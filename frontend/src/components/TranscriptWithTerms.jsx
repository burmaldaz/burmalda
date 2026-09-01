import { useMemo, useState } from "react";

/** Highlight glossary terms inside a transcript string. Case-insensitive,
 *  whole-word match. Clicking a highlighted term reveals its definition popover.
 */
export default function TranscriptWithTerms({ text = "", terms = [] }) {
  const [openIdx, setOpenIdx] = useState(null);

  const parts = useMemo(() => {
    if (!terms.length || !text) return [{ text }];
    // Build regex once with longest terms first so they win the match.
    const sorted = [...terms].sort((a, b) => b.term.length - a.term.length);
    const escaped = sorted
      .map((t) => t.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .filter(Boolean);
    if (!escaped.length) return [{ text }];
    const re = new RegExp(`\\b(${escaped.join("|")})\\b`, "gi");
    const out = [];
    let last = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) out.push({ text: text.slice(last, m.index) });
      const hit = sorted.find((t) => t.term.toLowerCase() === m[0].toLowerCase());
      out.push({ text: m[0], term: hit });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push({ text: text.slice(last) });
    return out;
  }, [text, terms]);

  return (
    <div
      data-testid="transcript-view"
      className="whitespace-pre-wrap leading-relaxed text-[color:var(--ink-soft)] max-h-[70vh] overflow-auto"
      style={{ fontSize: "1.05rem" }}
    >
      {parts.map((p, i) =>
        p.term ? (
          <span key={i} className="relative inline">
            <span
              className="term-hl"
              data-testid={`term-hl-${p.term.term.toLowerCase()}`}
              onClick={() => setOpenIdx(openIdx === i ? null : i)}
              title={p.term.translation}
            >
              {p.text}
            </span>
            {openIdx === i && (
              <span
                data-testid="term-popover"
                className="absolute left-0 top-full z-30 mt-1 w-72 p-3 bg-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm text-[color:var(--ink)] text-sm not-italic"
                onClick={() => setOpenIdx(null)}
              >
                <div className="font-serif-display text-lg leading-tight">
                  {p.term.term}
                </div>
                <div className="font-mono-label mt-1">
                  {p.term.translation}
                </div>
                {p.term.definition && (
                  <div className="mt-2 text-[color:var(--ink-soft)] leading-snug">
                    {p.term.definition}
                  </div>
                )}
              </span>
            )}
          </span>
        ) : (
          <span key={i}>{p.text}</span>
        )
      )}
      {!text && "Транскрипта пока нет."}
    </div>
  );
}
