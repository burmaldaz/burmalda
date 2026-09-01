import { useEffect, useState, useCallback } from "react";

/** Simple theme hook: 'light' | 'dark', persisted in localStorage. */
export default function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "light";
    return localStorage.getItem("palimpsest-theme") || "light";
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("palimpsest-theme", theme); } catch (_) {}
  }, [theme]);
  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  return { theme, setTheme, toggle };
}
