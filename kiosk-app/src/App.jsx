import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { fetchQrToken } from "./api";

/**
 * Full-screen kiosk:
 *   - Pulls a fresh, signed QR token from the backend.
 *   - Renders it as a large QR code.
 *   - Counts down using the SERVER-provided ttl/expiry and auto-refreshes,
 *     so the displayed code always reflects the backend's 15s rule.
 */
export default function App() {
  const [token, setToken] = useState(null);
  const [expiresAt, setExpiresAt] = useState(null);
  const [ttl, setTtl] = useState(15);
  const [remaining, setRemaining] = useState(15);
  const [error, setError] = useState(null);

  // Offset between the kiosk clock and the server clock (ms). We trust the
  // server: remaining time is computed against server-synced "now".
  const serverOffsetRef = useRef(0);
  const abortRef = useRef(null);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await fetchQrToken(controller.signal);
      const serverNow = new Date(data.server_time).getTime();
      serverOffsetRef.current = serverNow - Date.now();
      setToken(data.token);
      setExpiresAt(new Date(data.expires_at).getTime());
      setTtl(data.ttl_seconds);
      setError(null);
    } catch (err) {
      if (err.name !== "AbortError") {
        setError(err.message || "Sunucuya ulaşılamıyor");
      }
    }
  }, []);

  // Initial load.
  useEffect(() => {
    refresh();
    return () => abortRef.current?.abort();
  }, [refresh]);

  // If we have no valid token (e.g. backend was down at startup), keep retrying.
  useEffect(() => {
    if (error && !expiresAt) {
      const retry = setTimeout(refresh, 3000);
      return () => clearTimeout(retry);
    }
  }, [error, expiresAt, refresh]);

  // Tick every 250ms: update the countdown and trigger a refresh at expiry.
  useEffect(() => {
    if (!expiresAt) return;
    const interval = setInterval(() => {
      const serverNow = Date.now() + serverOffsetRef.current;
      const secsLeft = Math.max(0, (expiresAt - serverNow) / 1000);
      setRemaining(secsLeft);
      if (secsLeft <= 0) {
        refresh();
      }
    }, 250);
    return () => clearInterval(interval);
  }, [expiresAt, refresh]);

  const progress = Math.min(100, Math.max(0, (remaining / ttl) * 100));
  const isStale = remaining <= 0 || !token;

  return (
    <div className="kiosk">
      <h1 className="kiosk__title">Topkapı Okulları</h1>
      <p className="kiosk__subtitle">
        Giriş / Çıkış için telefonunuzla QR kodu okutun
      </p>

      <div className={`qr-card ${isStale ? "qr-card--stale" : ""}`}>
        {token ? (
          <QRCodeSVG
            value={token}
            size={Math.min(window.innerWidth, window.innerHeight) * 0.45}
            level="M"
            includeMargin={false}
          />
        ) : (
          <div style={{ width: 240, height: 240 }} />
        )}
      </div>

      <div className="countdown">
        <div
          className="countdown__ring"
          style={{ "--progress": progress }}
        >
          <div className="countdown__ring-inner">{Math.ceil(remaining)}</div>
        </div>
        <span className="countdown__label">
          Kod {ttl} saniyede bir yenilenir
        </span>
      </div>

      {error ? (
        <p className="status status--error">⚠ {error} — yeniden deneniyor…</p>
      ) : (
        <p className="status">Sunucu saati ile senkronize</p>
      )}
    </div>
  );
}
