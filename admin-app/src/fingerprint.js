const FP_KEY = "topkapi_admin_fingerprint";

/** Stable device fingerprint (cached) used to bind the single-device session. */
export function getDeviceFingerprint() {
  const cached = localStorage.getItem(FP_KEY);
  if (cached) return cached;
  const parts = [
    navigator.userAgent,
    navigator.language,
    navigator.platform || "",
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    navigator.hardwareConcurrency || "",
    Intl.DateTimeFormat().resolvedOptions().timeZone || "",
  ];
  const raw = btoa(unescape(encodeURIComponent(parts.join("|")))).slice(0, 240);
  localStorage.setItem(FP_KEY, raw);
  return raw;
}
