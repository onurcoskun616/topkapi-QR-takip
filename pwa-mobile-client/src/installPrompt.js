// Captures the browser's install ("Add to Home Screen") capability as early as
// possible. `beforeinstallprompt` can fire before React mounts, so this module
// is imported at the very top of main.jsx and keeps the event for later use.
let deferredPrompt = null;
let installed = false;
const listeners = new Set();

function emit() {
  listeners.forEach((fn) => fn());
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    // Stop Chrome's mini-infobar; we show our own prominent button instead.
    e.preventDefault();
    deferredPrompt = e;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferredPrompt = null;
    emit();
  });
}

/** Subscribe to install-state changes; returns an unsubscribe function. */
export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** The captured install event, or null if not (yet) available. */
export function getDeferredPrompt() {
  return deferredPrompt;
}

export function wasInstalled() {
  return installed;
}

/** Trigger the native install dialog. Returns "accepted" | "dismissed" | "unavailable". */
export async function promptInstall() {
  if (!deferredPrompt) return "unavailable";
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  deferredPrompt = null;
  emit();
  return outcome;
}

/** True when the app is running as an installed PWA (home-screen launch). */
export function isStandalone() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

/** iOS Safari has no beforeinstallprompt — it needs manual Share → Add steps. */
export function isIOS() {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}
