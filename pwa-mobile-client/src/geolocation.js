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
      // 1 = PERMISSION_DENIED; others are position-unavailable/timeout.
      permission = err.code === 1 ? "denied" : "unavailable";
      emit();
    },
    { enableHighAccuracy: true, maximumAge: 30000, timeout: 20000 }
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
 * The freshest usable fix for a scan. Returns the watched reading if it's
 * recent enough; otherwise asks for a one-shot position (awaiting briefly).
 * Resolves to { latitude, longitude, accuracy } or null when unavailable.
 */
export async function getLocationForScan({ maxAgeMs = 60000, timeout = 8000 } = {}) {
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
        permission = err.code === 1 ? "denied" : "unavailable";
        emit();
        // Fall back to the last known fix (even if a bit stale) rather than
        // nothing, so a momentary timeout doesn't block a user who is at school.
        if (latest) {
          const { latitude, longitude, accuracy } = latest;
          resolve({ latitude, longitude, accuracy });
        } else {
          resolve(null);
        }
      },
      { enableHighAccuracy: true, timeout, maximumAge: maxAgeMs }
    );
  });
}
