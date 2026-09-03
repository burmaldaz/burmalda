import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Mic, Square, Wifi, Check } from "lucide-react";
import useSpeechRecognition from "@/hooks/useSpeechRecognition";
import { api } from "@/lib/api";

/** Phone-optimized recording page opened by scanning the QR on the desktop.
 *  Uses the short-lived record token from the URL to POST transcript chunks.
 */
export default function MobileRecordPage() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t");
  const [lec, setLec] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [pushed, setPushed] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const { supported, isRecording, interim, finalText, start, stop, error } =
    useSpeechRecognition();
  const lastPushedLen = useRef(0);
  const startedAt = useRef(null);
  const errorToastedRef = useRef(false);

  useEffect(() => {
    if (!token) { setNotFound(true); return; }
    api.mobileGetLecture(id, token).then(setLec).catch(() => setNotFound(true));
  }, [id, token]);

  useEffect(() => {
    if (!token) return;
    const iv = setInterval(async () => {
      if (finalText.length <= lastPushedLen.current) return;
      const chunk = finalText.slice(lastPushedLen.current).trim();
      if (!chunk) return;
      try {
        await api.updateTranscript(id, {
          transcript: chunk,
          append: true,
          duration_sec: startedAt.current
            ? Math.floor((Date.now() - startedAt.current) / 1000)
            : undefined,
        }, token);
        lastPushedLen.current = finalText.length;
        setPushed((p) => p + 1);
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("push failed", e);
      }
    }, 4000);
    return () => clearInterval(iv);
  }, [finalText, id, token]);

  useEffect(() => {
    if (!isRecording) return;
    const iv = setInterval(() => {
      setElapsed(
        startedAt.current ? Math.floor((Date.now() - startedAt.current) / 1000) : 0
      );
    }, 500);
    return () => clearInterval(iv);
  }, [isRecording]);

  useEffect(() => {
    if ((error === "not-allowed" || error === "service-not-allowed") && !errorToastedRef.current) {
      errorToastedRef.current = true;
      toast.error("Разрешите микрофон в браузере.");
    }
  }, [error]);

  if (notFound) {
    return (
      <div className="paper-grain min-h-screen relative" data-testid="mobile-record">
        <div className="relative z-10 p-6 max-w-md mx-auto text-center">
          <div className="font-mono-label mb-3">— Ссылка недействительна</div>
          <h1 className="font-serif-display text-3xl mb-3">Откройте QR заново</h1>
          <p className="text-[color:var(--ink-soft)]">
            Токен записи истёк или неверен. Попросите открыть QR ещё раз на компьютере.
          </p>
        </div>
      </div>
    );
  }

  const onStart = () => {
    if (!supported) return toast.error("Браузер не поддерживает распознавание речи.");
    startedAt.current = Date.now();
    setElapsed(0);
    start();
  };

  const fmt = (s) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  return (
    <div className="paper-grain min-h-screen relative" data-testid="mobile-record">
      <div className="relative z-10 p-5 max-w-md mx-auto">
        <div className="flex items-center gap-2 mb-4">
          <div className="w-7 h-7 border border-[color:var(--ink)] flex items-center justify-center bg-[color:var(--terracotta)] text-white text-[10px]">u</div>
          <div className="font-serif-display text-lg leading-none">upsidestudy · телефон</div>
        </div>
        <div className="font-mono-label mb-1">— Запись лекции</div>
        <h1 className="font-serif-display text-3xl leading-tight mb-6" data-testid="mobile-title">
          {lec?.title || "Загрузка…"}
        </h1>

        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-5 shadow-offset mb-4">
          <div className="flex items-center gap-3 mb-4">
            {isRecording && <span className="rec-dot" />}
            <div className="font-mono-label" data-testid="mobile-timer">{fmt(elapsed)}</div>
            <div className="ml-auto flex items-center gap-1 text-[color:var(--muted)] text-xs">
              <Wifi className="w-3.5 h-3.5" strokeWidth={1.5} />
              <span data-testid="mobile-pushed">{pushed} чанков</span>
            </div>
          </div>
          {!isRecording ? (
            <button onClick={onStart} data-testid="mobile-start"
              className="w-full inline-flex items-center justify-center gap-2 px-5 py-4 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift text-lg">
              <Mic className="w-5 h-5" strokeWidth={2} /> Начать запись
            </button>
          ) : (
            <button onClick={stop} data-testid="mobile-stop"
              className="w-full inline-flex items-center justify-center gap-2 px-5 py-4 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift text-lg">
              <Square className="w-5 h-5" strokeWidth={2} /> Остановить
            </button>
          )}
        </div>

        <div className="border border-[color:var(--border)] bg-[color:var(--paper)] p-4 min-h-[200px] max-h-[50vh] overflow-auto text-[color:var(--ink)] leading-relaxed text-base whitespace-pre-wrap" data-testid="mobile-transcript">
          {finalText}
          {interim && <span className="text-[color:var(--muted)] italic"> {interim}</span>}
          {!finalText && !interim && (
            <span className="text-[color:var(--muted)]">
              Транскрипт будет появляться здесь и подгружаться на компьютер каждые 4 секунды.
            </span>
          )}
        </div>

        <div className="mt-4 flex items-center gap-2 text-xs text-[color:var(--muted)]">
          <Check className="w-3.5 h-3.5 text-[color:var(--sage-deep)]" strokeWidth={2} />
          Компьютер получает текст автоматически — можно закрыть страницу после остановки.
        </div>
      </div>
    </div>
  );
}
