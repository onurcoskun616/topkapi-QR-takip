import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getDeviceFingerprint } from "./fingerprint";

const REFRESH_KEY = "topkapi_admin_refresh";
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null); // short-lived access token
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const refreshTimer = useRef(null);
  const fingerprint = getDeviceFingerprint();

  const scheduleRefresh = (expiresInSec) => {
    clearTimeout(refreshTimer.current);
    // Refresh a minute before expiry so the access token never lapses.
    const ms = Math.max((expiresInSec - 60) * 1000, 15000);
    refreshTimer.current = setTimeout(doRefresh, ms);
  };

  async function doRefresh() {
    const refreshToken = localStorage.getItem(REFRESH_KEY);
    if (!refreshToken) return false;
    try {
      const data = await api.refresh(refreshToken, fingerprint);
      setToken(data.access_token);
      setUser(data.user);
      scheduleRefresh(data.access_expires_in);
      return true;
    } catch {
      localStorage.removeItem(REFRESH_KEY);
      setToken(null);
      setUser(null);
      return false;
    }
  }

  useEffect(() => {
    (async () => {
      await doRefresh();
      setLoading(false);
    })();
    return () => clearTimeout(refreshTimer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (email, password) => {
    const data = await api.login(email.trim().toLowerCase(), password, fingerprint);
    if (!["campus_director", "hq"].includes(data.user.role)) {
      throw new Error("Bu panele yalnızca müdür ve genel merkez giriş yapabilir.");
    }
    localStorage.setItem(REFRESH_KEY, data.refresh_token);
    setToken(data.access_token);
    setUser(data.user);
    scheduleRefresh(data.access_expires_in);
  };

  const logout = () => {
    clearTimeout(refreshTimer.current);
    localStorage.removeItem(REFRESH_KEY);
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ token, user, loading, login, logout, isAuthed: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
