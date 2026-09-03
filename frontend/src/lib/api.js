import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

// Cookies-based auth: send credentials on every request.
axios.defaults.withCredentials = true;

const http = axios.create({ baseURL: API, withCredentials: true });

export const api = {
  // Auth
  register: (body) => http.post("/auth/register", body).then((r) => r.data),
  login: (body) => http.post("/auth/login", body).then((r) => r.data),
  logout: () => http.post("/auth/logout").then((r) => r.data),
  me: () => http.get("/auth/me").then((r) => r.data),
  forgotPassword: (email) =>
    http.post("/auth/forgot-password", { email }).then((r) => r.data),
  resetPassword: (token, password) =>
    http.post("/auth/reset-password", { token, password }).then((r) => r.data),
  emergentSession: (sessionId) =>
    http.post("/auth/emergent-session", { session_id: sessionId }).then((r) => r.data),

  // Lectures
  listLectures: () => http.get("/lectures").then((r) => r.data),
  getLecture: (id) => http.get(`/lectures/${id}`).then((r) => r.data),
  createLecture: (body) => http.post("/lectures", body).then((r) => r.data),
  deleteLecture: (id) => http.delete(`/lectures/${id}`).then((r) => r.data),
  updateTranscript: (id, body, token) => {
    const cfg = token ? { headers: { Authorization: `Bearer ${token}` } } : {};
    return http.patch(`/lectures/${id}/transcript`, body, cfg).then((r) => r.data);
  },
  generateSummary: (id) => http.post(`/lectures/${id}/summary`).then((r) => r.data),
  generateTest: (id) => http.post(`/lectures/${id}/test`).then((r) => r.data),
  listTests: (id) => http.get(`/lectures/${id}/tests`).then((r) => r.data),
  getTest: (id) => http.get(`/tests/${id}`).then((r) => r.data),
  gradeTest: (id, answers) => http.post(`/tests/${id}/grade`, { answers }).then((r) => r.data),
  listAttempts: (id) => http.get(`/lectures/${id}/attempts`).then((r) => r.data),

  // Aggregate / config
  stats: () => http.get("/stats").then((r) => r.data),
  config: () => http.get("/config").then((r) => r.data),

  // Audio
  transcribeAudio: (file, onProgress) => {
    const fd = new FormData();
    fd.append("file", file);
    return http.post("/transcribe-audio", fd, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 300000,
      onUploadProgress: onProgress,
    }).then((r) => r.data);
  },

  // Review / streak
  reviewDue: () => http.get("/review/due").then((r) => r.data),
  reviewStats: () => http.get("/review/stats").then((r) => r.data),
  reviewAnswer: (id, response) =>
    http.post(`/review/${id}/answer`, { response }).then((r) => r.data),
  freezeStreak: () => http.post("/streak/freeze").then((r) => r.data),

  // Glossary
  generateGlossary: (id) => http.post(`/lectures/${id}/glossary`).then((r) => r.data),
  glossaryAll: () => http.get("/glossary/all").then((r) => r.data),

  // Digest
  digestPreview: () => http.get("/digest/preview").then((r) => r.data),
  digestSend: () => http.post("/digest/send").then((r) => r.data),

  // Phone / QR
  createRecordToken: (id) =>
    http.post(`/lectures/${id}/record-token`).then((r) => r.data),
  mobileGetLecture: (id, token) =>
    http.get(`/lectures/${id}/mobile?t=${encodeURIComponent(token)}`).then((r) => r.data),
};

export function formatApiError(detail, fallback = "Что-то пошло не так.") {
  if (detail == null) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail
      .map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e)))
      .filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}
