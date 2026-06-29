import { useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import {
  fetchQrToken,
  fetchQrTokenStatus,
  fetchRecentScans,
  fetchAnnouncements,
} from "./api";
import BirthdayOverlay from "./BirthdayOverlay";
import ScanResult from "./ScanResult";
import Announcement from "./Announcement";
import logo from "./assets/logo.png";

// The kiosk learns which campus it belongs to from the tablet URL, e.g.
// https://kiosk.okulunuz.com/?campus=3  — needed so the tablet only confirms
// (and celebrates) scans for its own campus. Falls back to a build-time env var.
function readCampusId() {
  const fromQuery = new URLSearchParams(window.location.search).get("campus");
  return fromQuery || import.meta.env.VITE_CAMPUS_ID || null;
}

const KIOSK_ID_KEY = "topkapi_kiosk_id";

// A campus can run several tablets at once. Each needs its own stable id so a
// scan confirmed on one tablet's QR code is never shown on another — generated
// once and kept in localStorage, so it survives reloads but is unique per
// physical device (clearing site data starts a fresh identity, which is fine:
// it only affects which tablet shows the next confirmation, never attendance).
function readKioskId() {
  let id = localStorage.getItem(KIOSK_ID_KEY);
  if (!id) {
    id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    localStorage.setItem(KIOSK_ID_KEY, id);
  }
  return id;
}

// How long each on-screen confirmation stays up, and how often we poll for new
// scans. The poll is brisk so a green check appears within a fraction of a
// second of scanning. The phone always shows its own instant result too.
const SCAN_DISPLAY_MS = 1800;
const BIRTHDAY_DISPLAY_MS = 9000;
const SCAN_POLL_MS = 700;
// Cap pending confirmations so a morning rush keeps the tablet on recent scans
// instead of lagging seconds behind (birthdays are never dropped).
const MAX_PENDING = 4;
// How often we ask "has my currently-displayed code been scanned yet?" so a
// kiosk can roll over to a fresh code right away instead of leaving a dead
// one on screen for the rest of its 15s window — useful with several kiosks
// at one campus, where the next person may well be standing at this exact
// tablet moments after someone else's scan. Kept brisk so the new code shows
// almost immediately after a scan (the next person never faces a dead code).
const TOKEN_STATUS_POLL_MS = 400;
// How often we refresh the list of notices to show, and — when more than one is
// active — how long each stays on screen before rotating to the next.
const ANNOUNCE_POLL_MS = 20000;
const ANNOUNCE_ROTATE_MS = 12000;
// Safety net for video notices: normally we advance on the video's own
// "ended" event so a clip always plays to completion, but if playback stalls
// (bad network, decode error) this guarantees the kiosk doesn't get stuck.
const VIDEO_FALLBACK_ROTATE_MS = 60000;

/**
 * Full-screen kiosk:
 *   - Pulls a fresh, signed QR token from the backend.
 *   - Renders it as a large QR code.
 *   - Counts down using the SERVER-provided ttl/expiry and auto-refreshes,
 *     so the displayed code always reflects the backend's 15s rule.
 */
export default function App() {
  const [token, setToken] = useState(null);
  const [jti, setJti] = useState(null);
  const [expiresAt, setExpiresAt] = useState(null);
  const [ttl, setTtl] = useState(15);
  const [remaining, setRemaining] = useState(15);
  const [error, setError] = useState(null);
  const [clockText, setClockText] = useState("");

  // Offset between the kiosk clock and the server clock (ms). We trust the
  // server: remaining time is computed against server-synced "now".
  const serverOffsetRef = useRef(0);
  const abortRef = useRef(null);

  // Scan confirmations / birthday celebrations polled for this kiosk's campus.
  const campusIdRef = useRef(readCampusId());
  const kioskIdRef = useRef(readKioskId());
  const [current, setCurrent] = useState(null); // { kind, name, type } | null
  const currentRef = useRef(null);
  const queueRef = useRef([]);
  const seenLogIdsRef = useRef(new Set());

  // Full-screen notices (admin "Duyurular"); rotated if more than one is active.
  const [announcements, setAnnouncements] = useState([]);
  const [annIndex, setAnnIndex] = useState(0);

  // Browsers force auto-playing video to be muted until the page gets a real
  // user gesture. Nobody taps this kiosk (staff scan with their phones), so we
  // surface a one-time "enable sound" button: a single tap unlocks audio for
  // the whole session, and every announcement video then plays with sound.
  const [soundOn, setSoundOn] = useState(false);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const data = await fetchQrToken(campusIdRef.current, kioskIdRef.current, controller.signal);
      const serverNow = new Date(data.server_time).getTime();
      serverOffsetRef.current = serverNow - Date.now();
      setToken(data.token);
      setJti(data.jti);
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

  // Watch the currently-displayed code: the moment it's scanned, roll over to
  // a fresh one immediately rather than waiting out the rest of its 15s slot.
  useEffect(() => {
    if (!jti) return;
    let cancelled = false;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const data = await fetchQrTokenStatus(jti, controller.signal);
        if (!cancelled && data.used) refresh();
      } catch {
        /* transient; next tick retries */
      }
    };
    const interval = setInterval(poll, TOKEN_STATUS_POLL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, [jti, refresh]);

  // Live wall-clock display (HH:MM:SS), corrected by the same server offset
  // used for the countdown, so staff can read the exact time of their scan
  // regardless of the tablet's own clock accuracy. Runs independently of the
  // QR refresh cycle so it keeps ticking even during an error/retry state.
  useEffect(() => {
    const tick = () => {
      const serverNow = new Date(Date.now() + serverOffsetRef.current);
      setClockText(
        serverNow.toLocaleTimeString("tr-TR", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
      );
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

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
        const data = await fetchRecentScans(campusId, kioskIdRef.current, controller.signal);
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
        // During a rush, drop the oldest plain confirmations (keep birthdays)
        // so the tablet stays on recent scans rather than lagging behind.
        if (queueRef.current.length > MAX_PENDING) {
          let over = queueRef.current.length - MAX_PENDING;
          queueRef.current = queueRef.current.filter((e) => {
            if (over > 0 && e.kind === "scan") {
              over -= 1;
              return false;
            }
            return true;
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

  // Poll the notices this campus's kiosk should display right now.
  useEffect(() => {
    const campusId = campusIdRef.current;
    if (!campusId) return; // no campus configured → no notices

    let cancelled = false;
    const controller = new AbortController();
    const poll = async () => {
      try {
        const data = await fetchAnnouncements(campusId, controller.signal);
        if (!cancelled) setAnnouncements(data.announcements || []);
      } catch {
        /* transient; next tick retries */
      }
    };
    poll();
    const interval = setInterval(poll, ANNOUNCE_POLL_MS);
    return () => {
      cancelled = true;
      controller.abort();
      clearInterval(interval);
    };
  }, []);

  // The notice currently on screen (rotated by the effect below), if any.
  const announcement = announcements.length
    ? announcements[annIndex % announcements.length]
    : null;

  // Advance to the next notice, looping back to the first.
  const advanceAnnouncement = useCallback(() => {
    setAnnIndex((i) => (announcements.length ? (i + 1) % announcements.length : 0));
  }, [announcements.length]);

  // Rotate through multiple active notices; reset to the first when the set
  // shrinks so the index never points past the end. Image/text notices
  // rotate on a fixed timer; a video notice instead advances when it
  // actually finishes playing (the <video> onEnded handler passed down to
  // Announcement), so a longer clip is never cut off mid-play — this timer
  // then only acts as a fallback for that case. Depending on the video URL
  // (not the announcements array itself) keeps a periodic re-fetch with the
  // same content from resetting the timer mid-play.
  useEffect(() => {
    if (announcements.length <= 1) {
      setAnnIndex(0);
      return;
    }
    const delay = announcement?.video_url ? VIDEO_FALLBACK_ROTATE_MS : ANNOUNCE_ROTATE_MS;
    const timer = setTimeout(advanceAnnouncement, delay);
    return () => clearTimeout(timer);
  }, [announcements.length, annIndex, announcement?.video_url, advanceAnnouncement]);

  const progress = Math.min(100, Math.max(0, (remaining / ttl) * 100));
  const isStale = remaining <= 0 || !token;

  // Tablets get mounted in either orientation. Portrait has height to spare,
  // so the QR leans on width; landscape is short, so it leans on height —
  // otherwise the code (and everything below it) overflows a wide-but-short
  // screen. Recomputed every render, which happens at least every 250ms via
  // the countdown tick, so it tracks a live orientation change too.
  const isLandscape = window.innerWidth > window.innerHeight;
  const qrSize = isLandscape
    ? Math.min(window.innerWidth * 0.22, window.innerHeight * 0.55)
    : Math.min(window.innerWidth * 0.46, window.innerHeight * 0.36);

  // Whether any active notice carries a video — only then is a sound toggle
  // meaningful (images and text have nothing to play).
  const hasVideo = announcements.some((a) => a.video_url);

  // Scan confirmations / birthday celebrations overlay every layout. The sound
  // toggle rides along here so it shows in both the QR and announcement views.
  const overlays = (
    <>
      {hasVideo && !soundOn && (
        <button className="sound-toggle" onClick={() => setSoundOn(true)}>
          🔊 Sesi Aç
        </button>
      )}
      {current?.kind === "birthday" && (
        <BirthdayOverlay name={current.name} onDone={dismiss} />
      )}
      {current?.kind === "scan" && (
        <ScanResult name={current.name} type={current.type} onDone={dismiss} />
      )}
    </>
  );

  // Announcement mode: the notice fills the screen and the QR shrinks to a
  // compact card in the bottom-right corner — no clock, no countdown clutter.
  if (announcement) {
    const cornerQr = Math.max(
      180,
      Math.min(340, Math.min(window.innerWidth, window.innerHeight) * 0.32)
    );
    return (
      <div className="kiosk kiosk--announce">
        {overlays}
        <Announcement
          data={announcement}
          soundOn={soundOn}
          loop={announcements.length <= 1}
          onVideoEnded={advanceAnnouncement}
        />
        <div className={`qr-corner ${isStale ? "qr-corner--stale" : ""}`}>
          <div className="qr-corner__code">
            {token ? (
              <QRCodeSVG value={token} size={cornerQr} level="M" includeMargin={false} />
            ) : (
              <div style={{ width: cornerQr, height: cornerQr }} />
            )}
          </div>
          <span className="qr-corner__label">Giriş / Çıkış için okutun</span>
        </div>
      </div>
    );
  }

  return (
    <div className="kiosk">
      {overlays}
      <div className="kiosk__intro">
        <img className="kiosk__logo" src={logo} alt="Topkapı Okulları" />
        <h1 className="kiosk__title">Topkapı Okulları</h1>
        <p className="kiosk__subtitle">
          Giriş / Çıkış için telefonunuzla QR kodu okutun
        </p>
      </div>

      <div className={`qr-card ${isStale ? "qr-card--stale" : ""}`}>
        {token ? (
          <QRCodeSVG value={token} size={qrSize} level="M" includeMargin={false} />
        ) : (
          <div style={{ width: 240, height: 240 }} />
        )}
      </div>

      <div className="kiosk__footer">
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
        <p className="kiosk__clock">{clockText}</p>
      </div>
    </div>
  );
}
