const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function parse(res) {
  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `İstek başarısız (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

const json = (path, body) =>
  fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(parse);

export const api = {
  campuses: () => fetch(`${API_BASE_URL}/api/campuses`).then(parse),

  // Staff self-registration / new-phone re-claim (passwordless, device-bound).
  register: (payload) => json("/api/auth/register", payload),

  refresh: (refreshToken, deviceFingerprint) =>
    json("/api/auth/refresh", {
      refresh_token: refreshToken,
      device_fingerprint: deviceFingerprint,
    }),

  me: (accessToken) =>
    fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    }).then(parse),

  logout: (accessToken) =>
    fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
    }),

  scan: (accessToken, qrToken) =>
    fetch(`${API_BASE_URL}/api/scan`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ qr_token: qrToken }),
    }).then(parse),
};

export { API_BASE_URL };
