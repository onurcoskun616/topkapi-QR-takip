const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * Fetch a fresh kiosk QR token from the backend.
 * The backend is the single source of truth for timing (server UTC).
 */
export async function fetchQrToken(signal) {
  const res = await fetch(`${API_BASE_URL}/api/qr/token`, { signal });
  if (!res.ok) {
    throw new Error(`QR token isteği başarısız (${res.status})`);
  }
  return res.json(); // { token, issued_at, expires_at, ttl_seconds, server_time }
}

/**
 * Poll for staff who have a birthday today and just scanned their first IN of
 * the day on this campus, so the kiosk can congratulate them. Returns an empty
 * list when no campus is configured or nothing recent is found.
 */
export async function fetchCelebrations(campusId, signal) {
  if (!campusId) return { celebrations: [] };
  const res = await fetch(
    `${API_BASE_URL}/api/kiosk/celebrations?campus_id=${encodeURIComponent(campusId)}`,
    { signal }
  );
  if (!res.ok) {
    throw new Error(`Kutlama isteği başarısız (${res.status})`);
  }
  return res.json(); // { celebrations: [{ user_id, full_name, log_id, scan_time }] }
}
