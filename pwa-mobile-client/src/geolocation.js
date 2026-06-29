// Phone location for campus geofencing. We start watching as soon as the app
// opens (so the browser asks for permission up front and a fresh fix is ready
// by the time the user scans), keep the latest reading in memory, and expose a
// helper that returns the freshest fix available at scan time.

let latest = null; // { latitude, longitude, accuracy, ts } | null
let permission = "unknown"; // "unknown" | "granted" | "denied" | "unavailable"
let watchId = null;
const listeners = new Set();

function emit() {
  listeners.forEach((fn) => fn());
}

/** Begin watching the device location (idempotent). Call once on app start. */
export function startWatching() {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    permission = "unavailable";
    emit();
    return;
  }
  if (watchId !== null) return;
  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      latest = {
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        ts: Date.now(),
      };
      permission = "granted";
      emit();
    },
    (err) => {
      // 1 = PERMISSION_DENIED; others are position-unavailable/timeout. Either
      // way, live tracking just failed — drop any cached fix so a scan right
      // after location is switched off can't ride on an old reading.
      latest = null;
      permission = err.code === 1 ? "denied" : "unavailable";
      emit();
    },
    // Coarse (network/Wi-Fi/cell) location, not GPS: a campus geofence is
    // hundreds of metres wide, so we don't need GPS precision — and high
    // accuracy makes iOS time out indoors (a school building) where GPS is
    // weak. maximumAge lets the OS hand back its recent fix instead of a slow
    // cold start, so `latest` stays populated.
    { enableHighAccuracy: false, maximumAge: 30000, timeout: 30000 }
  );
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getPermission() {
  return permission;
}

/**
 * The freshest usable fix for a scan. Uses the watched reading only if it
 * arrived within the last few seconds (i.e. live tracking is actually
 * working right now); otherwise requests a brand-new position with no
 * browser-side caching. Resolves to { latitude, longitude, accuracy } or
 * null when no current fix is available — callers must treat null as "no
 * location", never reuse an older fix. (Without this, switching location
 * off right after one real fix would let every later scan keep riding on
 * that stale reading.)
 */
export async function getLocationForScan({ maxAgeMs = 60000, timeout = 15000 } = {}) {
  if (latest && Date.now() - latest.ts <= maxAgeMs) {
    const { latitude, longitude, accuracy } = latest;
    return { latitude, longitude, accuracy };
  }
  if (typeof navigator === "undefined" || !navigator.geolocation) return null;
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        latest = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
          ts: Date.now(),
        };
        permission = "granted";
        emit();
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        });
      },
      (err) => {
        // A fresh read just failed (denied/off/no signal) — drop any cached
        // fix and report "no location" rather than falling back to a stale
        // one.
        latest = null;
        permission = err.code === 1 ? "denied" : "unavailable";
        emit();
        resolve(null);
      },
      // Coarse + allow a recent OS-cached fix (see startWatching): enough for a
      // campus-sized geofence and far more reliable than a GPS cold start
      // indoors, which is exactly where staff scan (inside the building).
      { enableHighAccuracy: false, timeout, maximumAge: 60000 }
    );
  });
}
