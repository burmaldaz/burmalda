/** Very small markdown-ish renderer for AI notes.
 *  Supports: ## h2, ### h3, **bold**, - bullets, blank-line paragraphs.
 *  Kept intentionally simple; sanitizes by escaping HTML then re-adding tags.
 */
function esc(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Strip LaTeX delimiters that some LLMs still emit despite instructions.
function stripLatex(s) {
  return s
    .replace(/\\\[|\\\]/g, "")
    .replace(/\\\(|\\\)/g, "")
    .replace(/\$\$/g, "")
    .replace(/\\text\{([^}]*)\}/g, "$1")
    .replace(/\\frac\{([^}]*)\}\{([^}]*)\}/g, "($1)/($2)")
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/\\rightarrow|\\to/g, "→")
    .replace(/\\Delta/g, "Δ")
    .replace(/\\/g, "");
}

function inline(s) {
  return esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

export default function Markdown({ text = "", className = "" }) {
  if (!text) return null;
  const lines = stripLatex(text).replace(/\r/g, "").split("\n");
  const out = [];
  let listBuf = [];

  const flushList = () => {
    if (listBuf.length) {
      out.push(
        `<ul>${listBuf.map((li) => `<li>${inline(li)}</li>`).join("")}</ul>`,
      );
      listBuf = [];
    }
  };

  let paraBuf = [];
  const flushPara = () => {
    if (paraBuf.length) {
      out.push(`<p>${inline(paraBuf.join(" "))}</p>`);
      paraBuf = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^##\s+/.test(line)) {
      flushList(); flushPara();
      out.push(`<h2>${inline(line.replace(/^##\s+/, ""))}</h2>`);
    } else if (/^###\s+/.test(line)) {
      flushList(); flushPara();
      out.push(`<h3>${inline(line.replace(/^###\s+/, ""))}</h3>`);
    } else if (/^[-*]\s+/.test(line)) {
      flushPara();
      listBuf.push(line.replace(/^[-*]\s+/, ""));
    } else if (line.trim() === "") {
      flushList(); flushPara();
    } else {
      paraBuf.push(line);
    }
  }
  flushList();
  flushPara();

  return (
    <div
      className={`prose-notes ${className}`}
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: out.join("") }}
    />
  );
}
