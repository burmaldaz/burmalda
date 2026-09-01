import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

const http = axios.create({ baseURL: API });

export const api = {
  listLectures: () => http.get("/lectures").then((r) => r.data),
  getLecture: (id) => http.get(`/lectures/${id}`).then((r) => r.data),
  createLecture: (body) => http.post("/lectures", body).then((r) => r.data),
  deleteLecture: (id) => http.delete(`/lectures/${id}`).then((r) => r.data),
  updateTranscript: (id, body) =>
    http.patch(`/lectures/${id}/transcript`, body).then((r) => r.data),
  generateSummary: (id) =>
    http.post(`/lectures/${id}/summary`).then((r) => r.data),
  generateTest: (id) => http.post(`/lectures/${id}/test`).then((r) => r.data),
  listTests: (id) => http.get(`/lectures/${id}/tests`).then((r) => r.data),
  getTest: (id) => http.get(`/tests/${id}`).then((r) => r.data),
  gradeTest: (id, answers) =>
    http.post(`/tests/${id}/grade`, { answers }).then((r) => r.data),
  listAttempts: (id) =>
    http.get(`/lectures/${id}/attempts`).then((r) => r.data),
  stats: () => http.get("/stats").then((r) => r.data),
  config: () => http.get("/config").then((r) => r.data),
  transcribeAudio: (file, onProgress) => {
    const fd = new FormData();
    fd.append("file", file);
    return http
      .post("/transcribe-audio", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: 300000,
        onUploadProgress: onProgress,
      })
      .then((r) => r.data);
  },
  reviewDue: () => http.get("/review/due").then((r) => r.data),
  reviewStats: () => http.get("/review/stats").then((r) => r.data),
  reviewAnswer: (id, response) =>
    http.post(`/review/${id}/answer`, { response }).then((r) => r.data),
};
