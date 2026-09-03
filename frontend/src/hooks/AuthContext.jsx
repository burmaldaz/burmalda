import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // null = checking, false = anonymous, object = logged in
  const [user, setUser] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
      return me;
    } catch (_) {
      setUser(false);
      return null;
    }
  }, []);

  useEffect(() => {
    // Skip /me check while returning from Emergent Auth — the callback
    // handler will process the session_id and set our cookies first.
    if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
      return;
    }
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    const r = await api.login({ email, password });
    setUser(r.user);
    return r.user;
  };

  const register = async (email, password, name) => {
    const r = await api.register({ email, password, name });
    setUser(r.user);
    return r.user;
  };

  const logout = async () => {
    try { await api.logout(); } catch (_) {}
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
