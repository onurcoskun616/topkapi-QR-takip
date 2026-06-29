// v2 storage: a random, collision-free per-device id.
const DEVICE_KEY = "topkapi_device_id";
// v1 storage: a fingerprint derived from browser/hardware signals. Kept only so
// devices that already bound under it (and are still logged in) keep working.
const LEGACY_KEY = "topkapi_device_fingerprint";
// Mirror of auth.jsx's refresh-token key — its presence means this device is
// already logged in (and therefore already bound server-side to its id).
const REFRESH_KEY = "topkapi_refresh_token";

/** A globally-unique random id, with fallbacks for older WebViews. */
function randomDeviceId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && crypto.getRandomValues) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }
  // Last-resort fallback (very old browsers / no crypto): still effectively
  // unique per device thanks to two independent random draws.
  return `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random()
    .toString(36)
    .slice(2)}`;
}

/**
 * Stable, per-device identifier used as the "device fingerprint": the backend
 * stores a hash of it and binds one account to one device.
 *
 * It MUST be unique per physical device. The previous version derived it from
 * browser/hardware signals, but iOS deliberately standardises those, so every
 * iPhone of the same model produced an identical value — a second staff member
 * was then refused with "Bu cihaz zaten başka bir personele tanımlı". We now use
 * a random id generated once and cached, so two devices can never collide.
 *
 * Migration: a device that is already logged in was bound server-side to its
 * old (legacy) fingerprint, so we keep that exact value for it — otherwise its
 * silent refresh would fail and it'd be forced to re-register. Brand-new or
 * previously-blocked devices (no live session) get a fresh random id.
 */
export function getDeviceFingerprint() {
  const existing = localStorage.getItem(DEVICE_KEY);
  if (existing) return existing;

  const legacy = localStorage.getItem(LEGACY_KEY);
  const loggedIn = !!localStorage.getItem(REFRESH_KEY);
  const id = legacy && loggedIn ? legacy : randomDeviceId();

  localStorage.setItem(DEVICE_KEY, id);
  return id;
}
