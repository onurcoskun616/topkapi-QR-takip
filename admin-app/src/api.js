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

  updateCampusShift: (token, campusId, payload) =>
    request(`/api/campuses/${campusId}/shift`, { method: "PATCH", token, body: payload }),

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

  logs: (token, { userId, campusId, day, startDate, endDate, limit = 200 } = {}) =>
    request(
      `/api/logs${qs({
        user_id: userId,
        campus_id: campusId,
        day,
        start_date: startDate,
        end_date: endDate,
        limit,
      })}`,
      { token }
    ),

  runAutoClose: (token) =>
    request("/api/admin/run-auto-close", { method: "POST", token }),

  // --- manual attendance entry (gap-fill, never edits a real qr_scan) -----
  createManualLog: (token, payload) =>
    request("/api/logs/manual", { method: "POST", token, body: payload }),

  // --- leave / absence records ---------------------------------------------
  leaveTypes: (token) => request("/api/leaves/types", { token }),

  listLeaves: (token, { userId, campusId, status, startDate, endDate } = {}) =>
    request(
      `/api/leaves${qs({
        user_id: userId,
        campus_id: campusId,
        status,
        start_date: startDate,
        end_date: endDate,
      })}`,
      { token }
    ),

  createLeave: (token, payload) =>
    request("/api/leaves", { method: "POST", token, body: payload }),

  updateLeave: (token, id, payload) =>
    request(`/api/leaves/${id}`, { method: "PATCH", token, body: payload }),

  cancelLeave: (token, id) =>
    request(`/api/leaves/${id}/cancel`, { method: "POST", token }),

  approveLeave: (token, id) =>
    request(`/api/leaves/${id}/approve`, { method: "POST", token }),

  rejectLeave: (token, id) =>
    request(`/api/leaves/${id}/reject`, { method: "POST", token }),

  // --- holidays / campus closures ----------------------------------------
  listHolidays: (token, { campusId, startDate, endDate } = {}) =>
    request(
      `/api/holidays${qs({ campus_id: campusId, start_date: startDate, end_date: endDate })}`,
      { token }
    ),

  createHoliday: (token, payload) =>
    request("/api/holidays", { method: "POST", token, body: payload }),

  deleteHoliday: (token, id) =>
    request(`/api/holidays/${id}`, { method: "DELETE", token }),

  // --- unresolved-status reminder (durum girilmedi) ----------------------
  unresolvedReminder: (token, { campusId, days, excludeWeekends } = {}) =>
    request(
      `/api/reports/unresolved-reminder${qs({
        campus_id: campusId,
        days,
        exclude_weekends: excludeWeekends,
      })}`,
      { token }
    ),

  // --- reports: late/early-leave rankings, absence detail + summary -------
  lateRanking: (token, { startDate, endDate, campusId, thresholdMinutes, excludeWeekends } = {}) =>
    request(
      `/api/reports/late${qs({
        start_date: startDate,
        end_date: endDate,
        campus_id: campusId,
        threshold_minutes: thresholdMinutes,
        exclude_weekends: excludeWeekends,
      })}`,
      { token }
    ),

  earlyLeaveRanking: (token, { startDate, endDate, campusId, thresholdMinutes, excludeWeekends } = {}) =>
    request(
      `/api/reports/early-leave${qs({
        start_date: startDate,
        end_date: endDate,
        campus_id: campusId,
        threshold_minutes: thresholdMinutes,
        exclude_weekends: excludeWeekends,
      })}`,
      { token }
    ),

  absenceDetail: (token, { startDate, endDate, campusId, userId, excludeWeekends } = {}) =>
    request(
      `/api/reports/absences${qs({
        start_date: startDate,
        end_date: endDate,
        campus_id: campusId,
        user_id: userId,
        exclude_weekends: excludeWeekends,
      })}`,
      { token }
    ),

  absenceSummary: (token, { startDate, endDate, campusId, excludeWeekends } = {}) =>
    request(
      `/api/reports/absence-summary${qs({
        start_date: startDate,
        end_date: endDate,
        campus_id: campusId,
        exclude_weekends: excludeWeekends,
      })}`,
      { token }
    ),
};

async function downloadFile(token, path, params, filename, failMessage) {
  const res = await fetch(`${API_BASE_URL}${path}${qs(params)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`${failMessage} (${res.status})`);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

/** Trigger a browser download of the CSV export with auth header. */
export async function downloadCsv(token, { userId, campusId, day, startDate, endDate } = {}) {
  await downloadFile(
    token,
    "/api/logs/export",
    { user_id: userId, campus_id: campusId, day, start_date: startDate, end_date: endDate },
    `attendance_${day || "all"}.csv`,
    "CSV dışa aktarım başarısız"
  );
}

/** Trigger a browser download of the raw log export as .xlsx. */
export async function downloadLogsXlsx(token, { userId, campusId, day, startDate, endDate } = {}) {
  await downloadFile(
    token,
    "/api/logs/export.xlsx",
    { user_id: userId, campus_id: campusId, day, start_date: startDate, end_date: endDate },
    `attendance_${day || "all"}.xlsx`,
    "Excel dışa aktarım başarısız"
  );
}

/** Trigger a browser download of the combined report workbook as .xlsx. */
export async function downloadReportsXlsx(
  token,
  { startDate, endDate, campusId, thresholdMinutes, excludeWeekends } = {}
) {
  await downloadFile(
    token,
    "/api/reports/export.xlsx",
    {
      start_date: startDate,
      end_date: endDate,
      campus_id: campusId,
      threshold_minutes: thresholdMinutes,
      exclude_weekends: excludeWeekends,
    },
    `raporlar_${startDate}_${endDate}.xlsx`,
    "Excel rapor dışa aktarım başarısız"
  );
}

export { API_BASE_URL };
