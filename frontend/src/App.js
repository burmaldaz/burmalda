import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import AppShell from "@/components/AppShell";
import Dashboard from "@/pages/Dashboard";
import RecordPage from "@/pages/RecordPage";
import LibraryPage from "@/pages/LibraryPage";
import LecturePage from "@/pages/LecturePage";
import TestPage from "@/pages/TestPage";
import ReviewPage from "@/pages/ReviewPage";

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#FCFBF9",
            border: "1px solid #1C201F",
            borderRadius: "2px",
            fontFamily: "Manrope, sans-serif",
            color: "#1C201F",
            boxShadow: "3px 3px 0 0 #1C201F",
          },
        }}
      />
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Dashboard />} />
          <Route path="/record" element={<RecordPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/lecture/:id" element={<LecturePage />} />
          <Route path="/lecture/:id/test/:testId" element={<TestPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
