const FP_KEY = "topkapi_device_fingerprint";

/**
 * Build a stable, device-derived fingerprint from browser/hardware signals.
 * Computed once and cached so it stays identical across silent refreshes; the
 * backend stores a hash of it and rejects refreshes from a different device.
 */
export function getDeviceFingerprint() {
  const cached = localStorage.getItem(FP_KEY);
  if (cached) return cached;

  const parts = [
    navigator.userAgent,
    navigator.language,
    navigator.platform || "",
    `${screen.width}x${screen.height}x${screen.colorDepth}`,
    navigator.hardwareConcurrency || "",
    navigator.maxTouchPoints || "",
    Intl.DateTimeFormat().resolvedOptions().timeZone || "",
  ];

  // base64 of the joined signals (URL-safe enough; backend only hashes it).
  const raw = btoa(unescape(encodeURIComponent(parts.join("|")))).slice(0, 240);
  localStorage.setItem(FP_KEY, raw);
  return raw;
}
