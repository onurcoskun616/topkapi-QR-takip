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
    const detail =
      (data && data.detail) || `İstek başarısız (${res.status})`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: { email, password } }),

  me: (token) => request("/api/auth/me", { token }),

  listUsers: (token) => request("/api/auth/users", { token }),

  createUser: (token, payload) =>
    request("/api/auth/users", { method: "POST", token, body: payload }),

  todaySummary: (token) => request("/api/logs/summary/today", { token }),

  logs: (token, { userId, day, limit = 200 } = {}) => {
    const qs = new URLSearchParams();
    if (userId) qs.set("user_id", userId);
    if (day) qs.set("day", day);
    qs.set("limit", limit);
    return request(`/api/logs?${qs.toString()}`, { token });
  },

  runAutoClose: (token) =>
    request("/api/admin/run-auto-close", { method: "POST", token }),
};

/** Trigger a browser download of the CSV export with auth header. */
export async function downloadCsv(token, { userId, day } = {}) {
  const qs = new URLSearchParams();
  if (userId) qs.set("user_id", userId);
  if (day) qs.set("day", day);

  const res = await fetch(`${API_BASE_URL}/api/logs/export?${qs.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
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
