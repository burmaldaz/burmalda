import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import Dashboard from "@/pages/Dashboard";
import RecordPage from "@/pages/RecordPage";
import LibraryPage from "@/pages/LibraryPage";
import LecturePage from "@/pages/LecturePage";
import TestPage from "@/pages/TestPage";
import ReviewPage from "@/pages/ReviewPage";
import DigestPage from "@/pages/DigestPage";
import MobileRecordPage from "@/pages/MobileRecordPage";
import AuthPage from "@/pages/AuthPage";
import useTheme from "@/hooks/useTheme";
import { AuthProvider } from "@/hooks/AuthContext";

export default function App() {
  useTheme();
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--paper)",
              border: "1px solid var(--ink)",
              borderRadius: "2px",
              fontFamily: "Manrope, sans-serif",
              color: "var(--ink)",
              boxShadow: "3px 3px 0 0 var(--ink)",
            },
          }}
        />
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route path="/m/:id" element={<MobileRecordPage />} />
          <Route element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
            <Route index element={<Dashboard />} />
            <Route path="/record" element={<RecordPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/lecture/:id" element={<LecturePage />} />
            <Route path="/lecture/:id/test/:testId" element={<TestPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/digest" element={<DigestPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
