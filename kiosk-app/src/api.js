const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * Fetch a fresh kiosk QR token from the backend.
 * The backend is the single source of truth for timing (server UTC).
 */
export async function fetchQrToken(campusId, signal) {
  const url = campusId
    ? `${API_BASE_URL}/api/qr/token?campus_id=${encodeURIComponent(campusId)}`
    : `${API_BASE_URL}/api/qr/token`;
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`QR token isteği başarısız (${res.status})`);
  }
  return res.json(); // { token, jti, issued_at, expires_at, ttl_seconds, server_time }
}

/**
 * Has the currently-displayed token already been scanned? Polled frequently
 * so the kiosk can roll over to a fresh code the instant it's used, instead
 * of leaving a dead code on screen for the rest of its 15s window.
 */
export async function fetchQrTokenStatus(jti, signal) {
  const res = await fetch(`${API_BASE_URL}/api/qr/token/${encodeURIComponent(jti)}/status`, {
    signal,
  });
  if (!res.ok) {
    throw new Error(`QR durum isteği başarısız (${res.status})`);
  }
  return res.json(); // { used }
}

/**
 * Poll for this campus's most recent successful QR scans so the tablet can
 * confirm them (green "Giriş/Çıkış başarılı"), with a `birthday` flag for a
 * staff member's first IN on their birthday. Returns an empty list when no
 * campus is configured or nothing recent is found.
 */
export async function fetchRecentScans(campusId, signal) {
  if (!campusId) return { scans: [] };
  const res = await fetch(
    `${API_BASE_URL}/api/kiosk/recent-scans?campus_id=${encodeURIComponent(campusId)}`,
    { signal }
  );
  if (!res.ok) {
    throw new Error(`Tarama isteği başarısız (${res.status})`);
  }
  return res.json(); // { scans: [{ log_id, user_id, full_name, type, scan_time, birthday }] }
}
