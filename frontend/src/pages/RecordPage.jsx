import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Mic, Square, Upload, FileText, Trash2, AudioLines, Loader2, QrCode, Smartphone } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import useSpeechRecognition from "@/hooks/useSpeechRecognition";
import { api } from "@/lib/api";

export default function RecordPage() {
  const [mode, setMode] = useState("mic"); // mic | paste | upload | audio | phone
  const [title, setTitle] = useState("");
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [startedAt, setStartedAt] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [phoneLecId, setPhoneLecId] = useState(null);
  const [phoneToken, setPhoneToken] = useState(null);
  const [phoneTranscript, setPhoneTranscript] = useState("");
  const [phoneCreating, setPhoneCreating] = useState(false);
  const nav = useNavigate();

  const {
    supported, isRecording, interim, finalText,
    start, stop, reset, setFinalText, error,
  } = useSpeechRecognition();

  useEffect(() => {
    if (!isRecording) return;
    const iv = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 500);
    return () => clearInterval(iv);
  }, [isRecording, startedAt]);

  useEffect(() => {
    if (error === "not-allowed" || error === "service-not-allowed") {
      toast.error("Браузер запретил доступ к микрофону.");
    }
  }, [error]);

  const onStart = () => {
    if (!supported) {
      toast.error("Ваш браузер не поддерживает Web Speech API. Используйте Chrome или Edge.");
      return;
    }
    setStartedAt(Date.now());
    setElapsed(0);
    start();
  };

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (!f.name.match(/\.(txt|md)$/i)) {
      toast.error("Пока принимаются только файлы .txt или .md. Аудио→текст работает через микрофон в браузере.");
      return;
    }
    const text = await f.text();
    setFinalText(text);
    if (!title) setTitle(f.name.replace(/\.(txt|md)$/i, ""));
    toast.success("Транскрипт загружен.");
  };

  const onAudioFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 25 * 1024 * 1024) {
      toast.error("Файл больше 25 МБ. Разделите его на части.");
      return;
    }
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
    setTranscribing(true);
    setUploadPct(0);
    try {
      const res = await api.transcribeAudio(f, (evt) => {
        if (evt.total) setUploadPct(Math.round((evt.loaded / evt.total) * 100));
      });
      setFinalText(res.text || "");
      toast.success("Расшифровка готова.");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Не удалось расшифровать аудио.");
    } finally {
      setTranscribing(false);
    }
  };

  const startPhoneSession = async () => {
    if (!title.trim()) return toast.error("Сначала укажите название лекции.");
    setPhoneCreating(true);
    try {
      const lec = await api.createLecture({
        title: title.trim(),
        source_type: "mic",
        transcript: "",
      });
      const tokenResp = await api.createRecordToken(lec.id);
      setPhoneLecId(lec.id);
      setPhoneToken(tokenResp.token);
      setPhoneTranscript("");
      toast.success("Отсканируйте QR — телефон подключён к этой лекции.");
    } catch (e) {
      toast.error("Не удалось создать лекцию.");
    } finally {
      setPhoneCreating(false);
    }
  };

  // Poll the lecture while phone session is active.
  useEffect(() => {
    if (!phoneLecId) return;
    const iv = setInterval(async () => {
      try {
        const l = await api.getLecture(phoneLecId);
        setPhoneTranscript(l.transcript || "");
      } catch (_) {}
    }, 3000);
    return () => clearInterval(iv);
  }, [phoneLecId]);

  const saveLecture = async () => {
    const transcriptText =
      mode === "paste" ? pasted.trim() : (finalText + " " + interim).trim();
    if (!title.trim()) {
      toast.error("Укажите название лекции.");
      return;
    }
    if (!transcriptText) {
      toast.error("Пока нечего сохранять — транскрипт пустой.");
      return;
    }
    setBusy(true);
    try {
      const lec = await api.createLecture({
        title: title.trim(),
        source_type: mode === "audio" ? "upload" : mode,
        transcript: transcriptText,
      });
      if (elapsed) {
        await api.updateTranscript(lec.id, {
          transcript: transcriptText,
          duration_sec: elapsed,
        });
      }
      toast.success("Лекция сохранена.");
      nav(`/lecture/${lec.id}`);
    } catch (e) {
      toast.error("Не удалось сохранить лекцию.");
    } finally {
      setBusy(false);
    }
  };

  const fmtTime = (s) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

  const wordCount =
    mode === "paste"
      ? pasted.trim().split(/\s+/).filter(Boolean).length
      : (finalText + " " + interim).trim().split(/\s+/).filter(Boolean).length;

  return (
    <div className="p-6 md:p-10 max-w-5xl" data-testid="record-page">
      <div className="font-mono-label mb-3">— Новая лекция</div>
      <h1 className="font-serif-display text-4xl sm:text-5xl mb-2">
        Зафиксируйте всё, что говорит преподаватель.
      </h1>
      <p className="text-[color:var(--ink-soft)] max-w-2xl mb-8">
        Записывайте живьём с микрофона, вставляйте готовый текст или
        загружайте файл. Всё хранится в исходном виде — конспект появляется
        только по вашей команде.
      </p>

      <div className="flex flex-wrap gap-2 mb-6">
        {[
          { k: "mic", label: "Микрофон", icon: Mic },
          { k: "phone", label: "Телефон (QR)", icon: Smartphone },
          { k: "paste", label: "Вставить текст", icon: FileText },
          { k: "upload", label: "Загрузить .txt", icon: Upload },
          { k: "audio", label: "Аудио → текст", icon: AudioLines },
        ].map(({ k, label, icon: Icon }) => (
          <button
            key={k}
            data-testid={`mode-${k}`}
            onClick={() => setMode(k)}
            className={`inline-flex items-center gap-2 px-4 py-2 border text-sm transition-all ${
              mode === k
                ? "bg-[color:var(--ink)] text-[color:var(--paper)] border-[color:var(--ink)]"
                : "bg-[color:var(--paper)] border-[color:var(--border)] hover:border-[color:var(--ink)]"
            }`}
          >
            <Icon className="w-4 h-4" strokeWidth={1.5} /> {label}
          </button>
        ))}
      </div>

      <label className="block mb-2 font-mono-label">Название лекции</label>
      <input
        data-testid="lecture-title-input"
        className="w-full max-w-2xl px-4 py-3 bg-[color:var(--paper)] border border-[color:var(--ink)] focus:outline-none focus:shadow-offset-sm mb-6 font-serif-display text-xl"
        placeholder="например, Микроэкономика 401 — Поведение потребителя"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />

      {mode === "mic" && (
        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 shadow-offset">
          <div className="flex flex-wrap items-center gap-4 mb-4">
            {!isRecording ? (
              <button
                data-testid="mic-start-btn"
                onClick={onStart}
                className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift"
              >
                <Mic className="w-4 h-4" strokeWidth={2} /> Старт
              </button>
            ) : (
              <button
                data-testid="mic-stop-btn"
                onClick={stop}
                className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift"
              >
                <Square className="w-4 h-4" strokeWidth={2} /> Стоп
              </button>
            )}
            <button
              data-testid="mic-reset-btn"
              onClick={() => { reset(); setElapsed(0); setStartedAt(null); }}
              className="inline-flex items-center gap-2 px-4 py-2 border border-[color:var(--border)] hover:border-[color:var(--ink)] text-sm"
            >
              <Trash2 className="w-4 h-4" strokeWidth={1.5} /> Очистить
            </button>

            <div className="flex items-center gap-3 ml-auto">
              {isRecording && <span className="rec-dot" />}
              <span className="font-mono-label" data-testid="mic-timer">
                {fmtTime(elapsed)}
              </span>
              <span className="font-mono-label">{wordCount} слов</span>
            </div>
          </div>

          {!supported && (
            <div className="p-3 mb-4 border border-[color:var(--terracotta)] text-[color:var(--terracotta-deep)] text-sm">
              Web Speech API недоступно в этом браузере. Откройте в Chrome
              или Edge — либо воспользуйтесь режимом «Вставить текст» или
              «Загрузить .txt».
            </div>
          )}

          <div
            data-testid="live-transcript"
            className="min-h-[220px] p-4 border border-[color:var(--border)] bg-[color:var(--bg)] text-[color:var(--ink)] leading-relaxed text-lg whitespace-pre-wrap"
          >
            {finalText}
            {interim && (
              <span className="text-[color:var(--muted)] italic"> {interim}</span>
            )}
            {!finalText && !interim && (
              <span className="text-[color:var(--muted)]">
                Живая расшифровка речи появится здесь по мере того, как вы говорите…
              </span>
            )}
          </div>
        </div>
      )}

      {mode === "paste" && (
        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 shadow-offset">
          <textarea
            data-testid="paste-textarea"
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            placeholder="Вставьте сюда сырой текст лекции…"
            className="w-full min-h-[280px] p-4 bg-[color:var(--bg)] border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--ink)] text-lg leading-relaxed"
          />
          <div className="mt-3 font-mono-label">{wordCount} слов</div>
        </div>
      )}

      {mode === "upload" && (
        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-8 shadow-offset text-center">
          <Upload className="w-8 h-8 mx-auto mb-3 text-[color:var(--muted)]" strokeWidth={1.5} />
          <p className="mb-4 text-[color:var(--ink-soft)]">
            Выберите файл с транскриптом (<code>.txt</code> или <code>.md</code>).
          </p>
          <input
            type="file"
            accept=".txt,.md,text/plain"
            onChange={onFile}
            data-testid="file-input"
            className="block mx-auto"
          />
          {finalText && (
            <div className="mt-6 text-left">
              <div className="font-mono-label mb-2">Предпросмотр</div>
              <div className="p-4 bg-[color:var(--bg)] border border-[color:var(--border)] max-h-[300px] overflow-auto text-[color:var(--ink-soft)] leading-relaxed whitespace-pre-wrap">
                {finalText.slice(0, 1200)}
                {finalText.length > 1200 && "…"}
              </div>
              <div className="mt-2 font-mono-label">{wordCount} слов</div>
            </div>
          )}
        </div>
      )}

      {mode === "audio" && (
        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-8 shadow-offset">
          <div className="text-center mb-4">
            <AudioLines className="w-8 h-8 mx-auto mb-3 text-[color:var(--muted)]" strokeWidth={1.5} />
            <p className="text-[color:var(--ink-soft)] max-w-lg mx-auto">
              Загрузите аудиозапись лекции — распознаём через Whisper и
              подставляем текст ниже. Поддерживаются <code>mp3, mp4, m4a,
              wav, webm</code>. Лимит 25 МБ.
            </p>
          </div>
          <div className="flex justify-center">
            <input
              type="file"
              accept="audio/*,video/mp4,.mp3,.mp4,.m4a,.wav,.webm,.mpga,.mpeg"
              onChange={onAudioFile}
              disabled={transcribing}
              data-testid="audio-file-input"
              className="block"
            />
          </div>
          {transcribing && (
            <div className="mt-6 flex items-center justify-center gap-3 text-[color:var(--ink-soft)]">
              <Loader2 className="w-5 h-5 animate-spin" strokeWidth={1.5} />
              <span data-testid="audio-transcribing">
                {uploadPct < 100
                  ? `Загрузка ${uploadPct}%…`
                  : "Расшифровка Whisper…"}
              </span>
            </div>
          )}
          {finalText && (
            <div className="mt-6">
              <div className="font-mono-label mb-2">Распознанный текст</div>
              <div
                data-testid="audio-transcript-preview"
                className="p-4 bg-[color:var(--bg)] border border-[color:var(--border)] max-h-[300px] overflow-auto text-[color:var(--ink-soft)] leading-relaxed whitespace-pre-wrap"
              >
                {finalText}
              </div>
              <div className="mt-2 font-mono-label">{wordCount} слов</div>
            </div>
          )}
        </div>
      )}

      {mode === "phone" && (
        <div className="border border-[color:var(--ink)] bg-[color:var(--paper)] p-6 md:p-8 shadow-offset">
          {!phoneLecId ? (
            <div className="text-center">
              <QrCode className="w-8 h-8 mx-auto mb-3 text-[color:var(--muted)]" strokeWidth={1.5} />
              <p className="text-[color:var(--ink-soft)] max-w-lg mx-auto mb-5">
                Создаём лекцию, показываем QR-код — открываете его камерой
                телефона, включаете микрофон, кладёте телефон на парту.
                Расшифровка приезжает сюда каждые ~4 секунды.
              </p>
              <button
                onClick={startPhoneSession}
                disabled={phoneCreating}
                data-testid="phone-start-btn"
                className="inline-flex items-center gap-2 px-5 py-3 bg-[color:var(--terracotta)] text-white border border-[color:var(--ink)] shadow-offset-sm hover-lift disabled:opacity-60"
              >
                {phoneCreating ? <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} /> : <QrCode className="w-4 h-4" strokeWidth={2} />}
                Показать QR
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="flex flex-col items-center justify-center">
                <div className="p-4 bg-white border border-[color:var(--ink)] shadow-offset-sm" data-testid="phone-qr">
                  <QRCodeSVG
                    value={`${window.location.origin}/m/${phoneLecId}?t=${phoneToken}`}
                    size={220}
                    level="M"
                    bgColor="#ffffff"
                    fgColor="#1c201f"
                  />
                </div>
                <div className="font-mono-label mt-3">Отсканируйте камерой</div>
                <a
                  href={`${window.location.origin}/m/${phoneLecId}?t=${phoneToken}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="phone-link"
                  className="mt-1 text-xs text-[color:var(--ink-soft)] underline decoration-dotted break-all max-w-full text-center"
                >
                  {`${window.location.origin}/m/${phoneLecId}`}
                </a>
              </div>
              <div>
                <div className="font-mono-label mb-2">Транскрипт с телефона (обновляется)</div>
                <div
                  data-testid="phone-transcript"
                  className="min-h-[220px] max-h-[400px] overflow-auto p-4 border border-[color:var(--border)] bg-[color:var(--bg)] leading-relaxed whitespace-pre-wrap"
                >
                  {phoneTranscript || (
                    <span className="text-[color:var(--muted)]">
                      Ждём, пока телефон начнёт слать текст…
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <div className="font-mono-label">
                    {phoneTranscript.split(/\s+/).filter(Boolean).length} слов
                  </div>
                  <button
                    onClick={() => nav(`/lecture/${phoneLecId}`)}
                    data-testid="phone-open-lecture"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-[color:var(--ink)] text-[color:var(--paper)] border border-[color:var(--ink)] shadow-offset-sm hover-lift text-sm"
                  >
                    Открыть лекцию →
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {mode !== "phone" && (
        <div className="mt-8 flex justify-end">
          <button
            onClick={saveLecture}
            disabled={busy}
            data-testid="save-lecture-btn"
            className="inline-flex items-center gap-2 px-6 py-3 bg-[color:var(--sage)] text-white border border-[color:var(--ink)] shadow-offset hover-lift disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {busy ? "Сохраняем…" : "Сохранить и открыть"}
          </button>
        </div>
      )}
    </div>
  );
}
