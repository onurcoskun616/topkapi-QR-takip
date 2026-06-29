const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

/**
 * Fetch a fresh kiosk QR token from the backend.
 * The backend is the single source of truth for timing (server UTC).
 * `kioskId` (this tablet's own id) rides along on the token so a scan can
 * later be confirmed only on the tablet that displayed it.
 */
export async function fetchQrToken(campusId, kioskId, signal) {
  const params = new URLSearchParams();
  if (campusId) params.set("campus_id", campusId);
  if (kioskId) params.set("kiosk_id", kioskId);
  const qs = params.toString();
  const url = `${API_BASE_URL}/api/qr/token${qs ? `?${qs}` : ""}`;
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
 * Poll for this tablet's own most recent successful QR scans so it can
 * confirm them (green "Giriş/Çıkış başarılı"), with a `birthday` flag for a
 * staff member's first IN on their birthday. Scoped by `kioskId` so a campus
 * running several tablets only confirms scans made against *this* tablet's
 * own code, not a colleague's scan confirmed on a different tablet. Returns
 * an empty list when no campus is configured or nothing recent is found.
 */
export async function fetchRecentScans(campusId, kioskId, signal) {
  if (!campusId) return { scans: [] };
  const params = new URLSearchParams({ campus_id: campusId });
  if (kioskId) params.set("kiosk_id", kioskId);
  const res = await fetch(`${API_BASE_URL}/api/kiosk/recent-scans?${params}`, { signal });
  if (!res.ok) {
    throw new Error(`Tarama isteği başarısız (${res.status})`);
  }
  return res.json(); // { scans: [{ log_id, user_id, full_name, type, scan_time, birthday }] }
}

/**
 * Poll the notices this kiosk's campus should display right now (full-screen
 * announcements / images / videos created from the admin panel). Media paths
 * are made absolute against the API base so <img>/<video> can load them
 * directly. Returns an empty list when no campus is configured.
 */
export async function fetchAnnouncements(campusId, signal) {
  if (!campusId) return { announcements: [] };
  const res = await fetch(
    `${API_BASE_URL}/api/kiosk/announcements?campus_id=${encodeURIComponent(campusId)}`,
    { signal }
  );
  if (!res.ok) {
    throw new Error(`Duyuru isteği başarısız (${res.status})`);
  }
  const data = await res.json();
  return {
    announcements: (data.announcements || []).map((a) => ({
      ...a,
      image_url: a.image_url ? `${API_BASE_URL}${a.image_url}` : null,
      video_url: a.video_url ? `${API_BASE_URL}${a.video_url}` : null,
    })),
  };
}
