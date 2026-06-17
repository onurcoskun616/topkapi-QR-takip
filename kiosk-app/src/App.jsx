import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { fetchQrToken, fetchRecentScans } from "./api";
import BirthdayOverlay from "./BirthdayOverlay";
import ScanResult from "./ScanResult";

// The kiosk learns which campus it belongs to from the tablet URL, e.g.
// https://kiosk.okulunuz.com/?campus=3  — needed so the tablet only confirms
// (and celebrates) scans for its own campus. Falls back to a build-time env var.
function readCampusId() {
  const fromQuery = new URLSearchParams(window.location.search).get("campus");
  return fromQuery || import.meta.env.VITE_CAMPUS_ID || null;
}

// How long each on-screen confirmation stays up, and how often we poll for new
// scans. The poll is brisk so a green check appears moments after scanning.
const SCAN_DISPLAY_MS = 2600;
const BIRTHDAY_DISPLAY_MS = 9000;
const SCAN_POLL_MS = 1500;

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

  // Scan confirmations / birthday celebrations polled for this kiosk's campus.
  const campusIdRef = useRef(readCampusId());
  const [current, setCurrent] = useState(null); // { kind, name, type } | null
  const currentRef = useRef(null);
  const queueRef = useRef([]);
  const seenLogIdsRef = useRef(new Set());

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

  // Show the next queued confirmation if nothing is currently on screen.
  const pump = useCallback(() => {
    if (currentRef.current) return;
    const next = queueRef.current.shift();
    if (!next) return;
    currentRef.current = next;
    setCurrent(next);
  }, []);

  const dismiss = useCallback(() => {
    currentRef.current = null;
    setCurrent(null);
    setTimeout(pump, 0); // let state settle, then show the next one
  }, [pump]);

  // Poll for this campus's recent successful scans and queue an on-screen
  // confirmation for each new one (de-duped by log id so each shows once).
  useEffect(() => {
    const campusId = campusIdRef.current;
    if (!campusId) return; // no campus configured → tablet confirmations off

    let cancelled = false;
    const controller = new AbortController();

    const poll = async () => {
      try {
        const data = await fetchRecentScans(campusId, controller.signal);
        if (cancelled) return;
        for (const s of data.scans || []) {
          if (seenLogIdsRef.current.has(s.log_id)) continue;
          seenLogIdsRef.current.add(s.log_id);
          queueRef.current.push({
            kind: s.birthday ? "birthday" : "scan",
            name: s.full_name,
            type: s.type,
          });
        }
        pump();
      } catch {
        /* transient; next tick retries */
      }
    };

    poll();
    const interval = setInterval(poll, SCAN_POLL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, [pump]);

  // Auto-dismiss the current confirmation after its display time.
  useEffect(() => {
    if (!current) return;
    const ms = current.kind === "birthday" ? BIRTHDAY_DISPLAY_MS : SCAN_DISPLAY_MS;
    const timer = setTimeout(dismiss, ms);
    return () => clearTimeout(timer);
  }, [current, dismiss]);

  const progress = Math.min(100, Math.max(0, (remaining / ttl) * 100));
  const isStale = remaining <= 0 || !token;

  return (
    <div className="kiosk">
      {current?.kind === "birthday" && (
        <BirthdayOverlay name={current.name} onDone={dismiss} />
      )}
      {current?.kind === "scan" && (
        <ScanResult name={current.name} type={current.type} onDone={dismiss} />
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
      ) : !campusIdRef.current ? (
        <p className="status status--error">
          ⚠ Kampüs tanımlı değil — onay bildirimleri için adrese ?campus=&lt;id&gt; ekleyin
        </p>
      ) : (
        <p className="status">Sunucu saati ile senkronize</p>
      )}
    </div>
  );
}
