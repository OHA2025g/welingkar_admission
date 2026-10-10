import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { http } from "@/lib/api";

const AuthCtx = createContext(null);
const ACTIVITY = ["mousemove", "keydown", "click", "scroll", "touchstart"];

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [ended, setEnded] = useState(null);
  const lastActivity = useRef(Date.now());

  const refresh = useCallback(async () => {
    try {
      const { data } = await http.get("/auth/me");
      setUser(data);
      return data;
    } catch {
      setUser(false);
      return false;
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const onEnd = (e) => { setUser(false); setEnded(e.detail?.message || "Your session has ended."); };
    window.addEventListener("ws:session-ended", onEnd);
    return () => window.removeEventListener("ws:session-ended", onEnd);
  }, []);

  useEffect(() => {
    if (!user) return;
    const mark = () => { lastActivity.current = Date.now(); };
    ACTIVITY.forEach((ev) => window.addEventListener(ev, mark, { passive: true }));
    const beat = setInterval(() => {
      if (Date.now() - lastActivity.current < 60000) http.post("/auth/heartbeat").catch(() => {});
    }, 60000);
    return () => { ACTIVITY.forEach((ev) => window.removeEventListener(ev, mark)); clearInterval(beat); };
  }, [user]);

  const signIn = (data) => { lastActivity.current = Date.now(); setEnded(null); setUser(data.user); return data.user; };

  const logout = useCallback(async (reason) => {
    try { await http.post("/auth/logout"); } catch { /* session may already be gone */ }
    setUser(false);
    if (reason) setEnded(reason);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, setUser, refresh, signIn, logout, ended, setEnded, lastActivity }}>
      {children}
    </AuthCtx.Provider>
  );
};

export const useAuth = () => useContext(AuthCtx);
export const can = (user, perm) => (Array.isArray(perm) ? perm : [perm]).some((p) => !!user?.permissions?.includes(p));
