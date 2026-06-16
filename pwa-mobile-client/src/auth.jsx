import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getDeviceFingerprint } from "./fingerprint";

// Per the spec the long-lived (1 year) refresh token lives in localStorage.
const REFRESH_KEY = "topkapi_refresh_token";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | anon | authed
  // Access token kept in memory only (short-lived; refreshed silently).
  const accessRef = useRef(null);

  const fingerprint = getDeviceFingerprint();

  const persistRefresh = (t) => localStorage.setItem(REFRESH_KEY, t);
  const clearRefresh = () => localStorage.removeItem(REFRESH_KEY);

  // ---- Silent refresh: swap refresh token + device id for a new access token.
  const silentRefresh = async () => {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    try {
      const data = await api.refresh(refreshToken, fingerprint);
      accessRef.current = data.access_token;
      setUser(data.user);
      return true;
    } catch {
      // Refresh failed (expired, revoked, or this device was kicked).
      accessRef.current = null;
      clearRefresh();
      setUser(null);
      return false;
    }
  };

  // On launch: try to resume the session silently so the teacher lands
  // straight on the camera without seeing a login screen.
  useEffect(() => {
    (async () => {
      const ok = await silentRefresh();
      setStatus(ok ? "authed" : "anon");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email, password) => {
    const data = await api.login(
      email.trim().toLowerCase(),
      password,
      fingerprint
    );
    accessRef.current = data.access_token;
    persistRefresh(data.refresh_token);
    setUser(data.user);
    setStatus("authed");
  };

  const logout = async () => {
    if (accessRef.current) {
      try {
        await api.logout(accessRef.current);
      } catch {
        /* best effort */
      }
    }
    accessRef.current = null;
    clearRefresh();
    setUser(null);
    setStatus("anon");
  };

  /**
   * Authenticated scan with automatic one-shot silent refresh: if the access
   * token expired mid-day, refresh once and retry before giving up.
   */
  const scan = async (qrToken) => {
    try {
      return await api.scan(accessRef.current, qrToken);
    } catch (err) {
      if (err.status === 401 && (await silentRefresh())) {
        return await api.scan(accessRef.current, qrToken);
      }
      if (err.status === 401) {
        setStatus("anon");
      }
      throw err;
    }
  };

  return (
    <AuthContext.Provider value={{ user, status, login, logout, scan }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
