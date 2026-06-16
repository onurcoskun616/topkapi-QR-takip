const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request(path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const text = await res.text();
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const detail = (data && data.detail) || `İstek başarısız (${res.status})`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

const qs = (params) => {
  const sp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") sp.set(k, v);
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // --- auth ---------------------------------------------------------------
  login: (email, password, deviceFingerprint) =>
    request("/api/auth/login", {
      method: "POST",
      body: { email, password, device_fingerprint: deviceFingerprint },
    }),

  refresh: (refreshToken, deviceFingerprint) =>
    request("/api/auth/refresh", {
      method: "POST",
      body: { refresh_token: refreshToken, device_fingerprint: deviceFingerprint },
    }),

  me: (token) => request("/api/auth/me", { token }),

  // --- campuses -----------------------------------------------------------
  campuses: () => request("/api/campuses"),

  // --- staff management (director: own campus, hq: all/filter) ------------
  listStaff: (token, { status, campusId } = {}) =>
    request(`/api/staff${qs({ status, campus_id: campusId })}`, { token }),

  approveStaff: (token, id) =>
    request(`/api/staff/${id}/approve`, { method: "POST", token }),

  disableStaff: (token, id) =>
    request(`/api/staff/${id}/disable`, { method: "POST", token }),

  resetDevice: (token, id) =>
    request(`/api/staff/${id}/reset-device`, { method: "POST", token }),

  updateStaff: (token, id, payload) =>
    request(`/api/staff/${id}`, { method: "PATCH", token, body: payload }),

  // --- directors (hq only) ------------------------------------------------
  listDirectors: (token) => request("/api/directors", { token }),

  createDirector: (token, payload) =>
    request("/api/directors", { method: "POST", token, body: payload }),

  disableDirector: (token, id) =>
    request(`/api/directors/${id}/disable`, { method: "POST", token }),

  // --- reporting ----------------------------------------------------------
  todaySummary: (token, { campusId } = {}) =>
    request(`/api/logs/summary/today${qs({ campus_id: campusId })}`, { token }),

  logs: (token, { userId, campusId, day, limit = 200 } = {}) =>
    request(
      `/api/logs${qs({ user_id: userId, campus_id: campusId, day, limit })}`,
      { token }
    ),

  runAutoClose: (token) =>
    request("/api/admin/run-auto-close", { method: "POST", token }),
};

/** Trigger a browser download of the CSV export with auth header. */
export async function downloadCsv(token, { userId, campusId, day } = {}) {
  const res = await fetch(
    `${API_BASE_URL}/api/logs/export${qs({ user_id: userId, campus_id: campusId, day })}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  if (!res.ok) throw new Error(`CSV dışa aktarım başarısız (${res.status})`);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `attendance_${day || "all"}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export { API_BASE_URL };
