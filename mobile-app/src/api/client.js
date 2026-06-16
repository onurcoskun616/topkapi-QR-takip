import Constants from "expo-constants";

const API_BASE_URL = (
  Constants.expoConfig?.extra?.apiBaseUrl || "http://localhost:8000"
).replace(/\/$/, "");

async function request(path, { method = "GET", body, token } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty / non-JSON body */
  }

  if (!res.ok) {
    const detail = data?.detail || `İstek başarısız (${res.status})`;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  login: (email, password) =>
    request("/api/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  me: (token) => request("/api/auth/me", { token }),

  scan: (token, qrToken) =>
    request("/api/scan", {
      method: "POST",
      token,
      body: { qr_token: qrToken },
    }),
};

export { API_BASE_URL };
