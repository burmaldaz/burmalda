import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/AuthContext";

export default function ProtectedRoute({ children }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === null) {
    return (
      <div className="min-h-screen flex items-center justify-center text-[color:var(--muted)] font-mono-label">
        загрузка…
      </div>
    );
  }
  if (user === false) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return children;
}
