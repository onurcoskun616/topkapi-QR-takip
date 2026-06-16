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
