// Web Push subscription helpers for the staff PWA.
//
// Push needs three things to line up: the browser must support it, the server
// must have VAPID keys configured, and the user must grant permission. These
// helpers keep that flow in one place so the UI just calls enable/disable and
// reads a status string. Notifications only fire for an INSTALLED PWA on iOS
// (16.4+); on Android Chrome they work in the browser too.
import { api } from "./api";

export function pushSupported() {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

// VAPID applicationServerKey arrives as base64url; the browser wants a Uint8Array.
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function readyRegistration() {
  // vite-plugin-pwa registers the SW; wait for it to be active.
  return navigator.serviceWorker.ready;
}

// Current state without prompting: "unsupported" | "disabled" (server off) |
// "denied" | "off" | "on".
export async function pushStatus() {
  if (!pushSupported()) return "unsupported";
  let cfg;
  try {
    cfg = await api.pushPublicKey();
  } catch {
    return "disabled";
  }
  if (!cfg.enabled) return "disabled";
  if (Notification.permission === "denied") return "denied";
  try {
    const reg = await readyRegistration();
    const sub = await reg.pushManager.getSubscription();
    return sub ? "on" : "off";
  } catch {
    return "off";
  }
}

// Ask permission, subscribe with the server's VAPID key, and register the
// subscription. Returns the new status; throws with a message on hard failures.
export async function enablePush(accessToken) {
  if (!pushSupported()) throw new Error("Bu cihaz/ tarayıcı bildirimleri desteklemiyor.");

  const cfg = await api.pushPublicKey();
  if (!cfg.enabled || !cfg.public_key) throw new Error("Bildirimler sunucuda etkin değil.");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Bildirim izni verilmedi.");

  const reg = await readyRegistration();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(cfg.public_key),
    });
  }
  await api.pushSubscribe(accessToken, sub.toJSON());
  return "on";
}

// Unsubscribe this device and tell the server to forget it.
export async function disablePush(accessToken) {
  if (!pushSupported()) return "unsupported";
  const reg = await readyRegistration();
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    const json = sub.toJSON();
    try {
      await sub.unsubscribe();
    } catch {
      /* best effort; still drop it server-side */
    }
    try {
      await api.pushUnsubscribe(accessToken, json);
    } catch {
      /* server prunes dead endpoints on next send anyway */
    }
  }
  return "off";
}
