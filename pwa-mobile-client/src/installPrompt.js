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

// Once a home-screen launch is confirmed, we remember it: some launchers open
// the installed icon in a plain tab (no display-mode standalone) and in-app
// navigations can drop the ?app=1 marker, which would otherwise bounce the user
// back to the install gate on every screen change.
const LAUNCH_KEY = "yoklama_launched_installed";

/** True when the app is running as an installed PWA (home-screen launch). */
export function isStandalone() {
  try {
    const byDisplay = ["standalone", "fullscreen", "minimal-ui"].some(
      (m) => window.matchMedia(`(display-mode: ${m})`).matches
    );
    const byIOS = window.navigator.standalone === true;
    // Our manifest start_url is "/?app=1", so a launch from the installed icon
    // carries this marker even when display-mode detection fails on the device.
    let byParam = false;
    try {
      byParam = new URLSearchParams(window.location.search).get("app") === "1";
    } catch {
      byParam = false;
    }
    if (byDisplay || byIOS || byParam) {
      try {
        localStorage.setItem(LAUNCH_KEY, "1");
      } catch {
        /* storage blocked — fall through to the live signals */
      }
      return true;
    }
    try {
      return localStorage.getItem(LAUNCH_KEY) === "1";
    } catch {
      return false;
    }
  } catch {
    return false;
  }
}

/** iOS Safari has no beforeinstallprompt — it needs manual Share → Add steps. */
export function isIOS() {
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}
