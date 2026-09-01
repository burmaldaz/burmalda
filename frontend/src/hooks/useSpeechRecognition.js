import { useEffect, useRef, useState, useCallback } from "react";

/**
 * Live speech-to-text using the browser's Web Speech API.
 * Works in Chromium-based browsers. Continuous mode with interim results.
 */
export default function useSpeechRecognition() {
  const recognitionRef = useRef(null);
  const [isRecording, setIsRecording] = useState(false);
  const [interim, setInterim] = useState("");
  const [finalText, setFinalText] = useState("");
  const [supported, setSupported] = useState(true);
  const [error, setError] = useState(null);
  const shouldRunRef = useRef(false);

  useEffect(() => {
    const SR =
      window.SpeechRecognition || window.webkitSpeechRecognition || null;
    if (!SR) {
      setSupported(false);
      return;
    }
    const rec = new SR();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";
    rec.onresult = (e) => {
      let interimStr = "";
      let finalStr = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalStr += t + " ";
        else interimStr += t;
      }
      if (finalStr) setFinalText((p) => (p + " " + finalStr).trim());
      setInterim(interimStr);
    };
    rec.onerror = (e) => {
      setError(e.error || "recognition-error");
      if (e.error === "no-speech" || e.error === "aborted") return;
      shouldRunRef.current = false;
      setIsRecording(false);
    };
    rec.onend = () => {
      // Auto-restart while user still wants to record (SR times out).
      if (shouldRunRef.current) {
        try { rec.start(); } catch (_) {}
      } else {
        setIsRecording(false);
      }
    };
    recognitionRef.current = rec;
    return () => {
      shouldRunRef.current = false;
      try { rec.stop(); } catch (_) {}
    };
  }, []);

  const start = useCallback(() => {
    setError(null);
    setInterim("");
    if (!recognitionRef.current) return;
    shouldRunRef.current = true;
    try {
      recognitionRef.current.start();
      setIsRecording(true);
    } catch (_) {
      // start() throws if already running; ignore
    }
  }, []);

  const stop = useCallback(() => {
    shouldRunRef.current = false;
    try { recognitionRef.current?.stop(); } catch (_) {}
    setIsRecording(false);
  }, []);

  const reset = useCallback(() => {
    setFinalText("");
    setInterim("");
  }, []);

  return { supported, isRecording, interim, finalText, error, start, stop, reset, setFinalText };
}
