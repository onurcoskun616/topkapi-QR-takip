import { createContext, useContext, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getDeviceFingerprint } from "./fingerprint";

// The long-lived (1 year) refresh token lives in localStorage.
const REFRESH_KEY = "topkapi_refresh_token";

const AuthContext = createContext(null);

// Map a user record to a coarse phase the UI routes on.
const phaseFor = (user) =>
  !user ? "anon" : user.status === "active" ? "authed" : "pending";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [phase, setPhase] = useState("loading"); // loading | anon | pending | authed
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
      setPhase(phaseFor(data.user));
      return true;
    } catch {
      // Refresh failed (expired, revoked, or this device was reset by a director).
      accessRef.current = null;
      clearRefresh();
      setUser(null);
      setPhase("anon");
      return false;
    }
  };

  // On launch: try to resume the session silently so an approved teacher lands
  // straight on the camera without re-registering.
  useEffect(() => {
    (async () => {
      const ok = await silentRefresh();
      if (!ok) setPhase("anon");
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Register (or re-claim an existing phone on a new device after a reset).
  const register = async (payload) => {
    const data = await api.register({
      ...payload,
      device_fingerprint: fingerprint,
    });
    accessRef.current = data.access_token;
    persistRefresh(data.refresh_token);
    setUser(data.user);
    setPhase(phaseFor(data.user));
    return data.user;
  };

  // Re-check approval status (the pending screen polls this).
  const recheck = async () => {
    if (!accessRef.current) return silentRefresh();
    try {
      const fresh = await api.me(accessRef.current);
      setUser(fresh);
      setPhase(phaseFor(fresh));
      return true;
    } catch (err) {
      if (err.status === 401) return silentRefresh();
      return false;
    }
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
    setPhase("anon");
  };

  /**
   * Authenticated scan with automatic one-shot silent refresh: if the access
   * token expired mid-day, refresh once and retry before giving up.
   */
  const scan = async (qrToken, location) => {
    try {
      return await api.scan(accessRef.current, qrToken, location);
    } catch (err) {
      if (err.status === 401 && (await silentRefresh())) {
        return await api.scan(accessRef.current, qrToken, location);
      }
      throw err;
    }
  };

  // Generic one-shot-refresh wrapper for any authed call (mirrors `scan`), so a
  // token that expired mid-day is refreshed once before the call gives up.
  const withAuth = async (fn) => {
    try {
      return await fn(accessRef.current);
    } catch (err) {
      if (err.status === 401 && (await silentRefresh())) {
        return await fn(accessRef.current);
      }
      throw err;
    }
  };

  const myLeaves = () => withAuth((t) => api.myLeaves(t));
  const requestLeave = (payload) => withAuth((t) => api.requestLeave(t, payload));
  const myStatus = () => withAuth((t) => api.myStatus(t));

  return (
    <AuthContext.Provider
      value={{ user, phase, register, recheck, logout, scan, myLeaves, requestLeave, myStatus }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
