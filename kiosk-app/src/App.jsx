import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { fetchQrToken, fetchCelebrations } from "./api";
import BirthdayOverlay from "./BirthdayOverlay";

// The kiosk learns which campus it belongs to from the tablet URL, e.g.
// https://kiosk.okulunuz.com/?campus=3  — needed so a birthday at one campus
// only celebrates on that campus's tablets. Falls back to a build-time env var.
function readCampusId() {
  const fromQuery = new URLSearchParams(window.location.search).get("campus");
  return fromQuery || import.meta.env.VITE_CAMPUS_ID || null;
}

// How long each birthday greeting stays on screen, and how often we poll.
const CELEBRATION_DISPLAY_MS = 9000;
const CELEBRATION_POLL_MS = 5000;

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

  // Birthday celebrations polled from the backend for this kiosk's campus.
  const campusIdRef = useRef(readCampusId());
  const [celebration, setCelebration] = useState(null); // { full_name } | null
  const seenLogIdsRef = useRef(new Set());
  const celebrationTimerRef = useRef(null);

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

  // Poll for birthday first-IN scans on this campus and queue a greeting for
  // any we haven't shown yet. De-dupe by log id so each person shows once.
  useEffect(() => {
    const campusId = campusIdRef.current;
    if (!campusId) return; // no campus configured → birthday feature off

    let cancelled = false;
    const controller = new AbortController();

    const poll = async () => {
      try {
        const data = await fetchCelebrations(campusId, controller.signal);
        if (cancelled) return;
        for (const c of data.celebrations || []) {
          if (seenLogIdsRef.current.has(c.log_id)) continue;
          seenLogIdsRef.current.add(c.log_id);
          // Show now if nothing is on screen; otherwise the next poll picks it
          // up once the current greeting clears.
          setCelebration((current) => current || { full_name: c.full_name });
        }
      } catch {
        /* transient; next tick retries */
      }
    };

    poll();
    const interval = setInterval(poll, CELEBRATION_POLL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  // Auto-dismiss the current greeting after a few seconds.
  useEffect(() => {
    if (!celebration) return;
    celebrationTimerRef.current = setTimeout(
      () => setCelebration(null),
      CELEBRATION_DISPLAY_MS
    );
    return () => clearTimeout(celebrationTimerRef.current);
  }, [celebration]);

  const progress = Math.min(100, Math.max(0, (remaining / ttl) * 100));
  const isStale = remaining <= 0 || !token;

  return (
    <div className="kiosk">
      {celebration && (
        <BirthdayOverlay
          name={celebration.full_name}
          onDone={() => setCelebration(null)}
        />
      )}
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
