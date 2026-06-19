import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api, downloadLogsXlsx } from "../api";
import PresenceTrendChart from "./PresenceTrendChart";

function todayLocalISO() {
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

// ISO date `days` before today (local), for the dashboard trend window.
function daysAgoLocalISO(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

const fmt = (iso) =>
  new Date(iso).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "medium" });

export default function Dashboard({ isHq }) {
  const { token } = useAuth();
  const [summary, setSummary] = useState(null);
  const [staff, setStaff] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [logs, setLogs] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [userId, setUserId] = useState("");
  const [day, setDay] = useState(todayLocalISO());
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [reminder, setReminder] = useState(null);
  const [pendingLeaves, setPendingLeaves] = useState(0);
  const [forgot, setForgot] = useState([]);
  const [trend, setTrend] = useState(null);

  const campusFilter = isHq && campusId ? { campusId } : {};

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.todaySummary(token, campusFilter));
    } catch (e) {
      setError(e.message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, campusId]);

  const loadLogs = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setLogs(await api.logs(token, { userId, day, ...campusFilter }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, userId, day, campusId]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    api
      .listStaff(token, { ...campusFilter })
      .then(setStaff)
      .catch((e) => setError(e.message));
    loadSummary();
    // "Durum girilmedi" reminder: recent absence days still missing a status.
    api
      .unresolvedReminder(token, { ...campusFilter, days: 14 })
      .then(setReminder)
      .catch(() => {});
    // Pending staff leave requests awaiting approval.
    api
      .listLeaves(token, { ...campusFilter, status: "requested" })
      .then((rows) => setPendingLeaves(rows.length))
      .catch(() => {});
    // Staff still inside after their shift ended (likely forgot to scan out).
    api
      .forgotCheckout(token, { ...campusFilter })
      .then((res) => setForgot(res.entries))
      .catch(() => {});
    // Last 14 days' attendance trend for the dashboard chart.
    api
      .dailyTrend(token, {
        startDate: daysAgoLocalISO(13),
        endDate: todayLocalISO(),
        excludeWeekends: true,
        ...campusFilter,
      })
      .then(setTrend)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, campusId]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const onExport = async () => {
    try {
      await downloadLogsXlsx(token, { userId, day, ...campusFilter });
    } catch (e) {
      setError(e.message);
    }
  };

  const onRunAutoClose = async () => {
    if (!window.confirm("İçeride kalan herkes için çıkış kaydı oluşturulsun mu?"))
      return;
    try {
      const res = await api.runAutoClose(token);
      setNotice(`${res.auto_closed} kayıt otomatik kapatıldı.`);
      await Promise.all([loadSummary(), loadLogs()]);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="stack">
      {isHq && (
        <section className="card">
          <label className="field field--inline">
            <span>Kampüs</span>
            <select value={campusId} onChange={(e) => setCampusId(e.target.value)}>
              <option value="">Tüm kampüsler</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        </section>
      )}

      {/* Attention banners: unresolved-status reminder + pending leave requests */}
      {reminder && reminder.unresolved_count > 0 && (
        <div className="banner banner--warn">
          <strong>Durum girilmedi:</strong> {reminder.start_date} – {reminder.end_date}{" "}
          aralığında <strong>{reminder.unresolved_count}</strong> gün için durum girilmemiş
          (devamsızlık açıklanmamış). "İzin / Devamsızlık" veya manuel kayıt ile çözümleyin.
        </div>
      )}
      {pendingLeaves > 0 && (
        <div className="banner banner--info">
          <strong>{pendingLeaves}</strong> personel izin talebi onayınızı bekliyor — "İzin /
          Devamsızlık" sekmesinden onaylayın veya reddedin.
        </div>
      )}
      {forgot.length > 0 && (
        <div className="banner banner--warn">
          <strong>Çıkış okutmayı unutmuş olabilir:</strong> mesai bitmesine rağmen{" "}
          <strong>{forgot.length}</strong> personel hâlâ "içeride" görünüyor. Gece 23:59
          otomatik kapanıştan önce hatırlatın.
          <ul className="banner__list">
            {forgot.slice(0, 8).map((e) => (
              <li key={e.user_id}>
                {e.full_name}
                {isHq && e.campus_name ? ` · ${e.campus_name}` : ""} — {fmt(e.since)}'den beri (
                {Math.floor(e.minutes_overdue / 60)} sa {e.minutes_overdue % 60} dk gecikme)
              </li>
            ))}
            {forgot.length > 8 && <li>… ve {forgot.length - 8} kişi daha</li>}
          </ul>
        </div>
      )}

      {/* KPI cards */}
      <section className="kpis">
        <div className="kpi">
          <div className="kpi__value">{summary?.currently_in_count ?? "—"}</div>
          <div className="kpi__label">Şu an içeride</div>
        </div>
        <div className="kpi">
          <div className="kpi__value">{summary?.active_today ?? "—"}</div>
          <div className="kpi__label">Bugün hareketli personel</div>
        </div>
        {isHq && (
          <div className="kpi kpi--action">
            <button className="btn btn--warn" onClick={onRunAutoClose}>
              Gece Kapanışını Çalıştır
            </button>
            <span className="muted small">Tüm kampüslerde içeride kalanları kapatır</span>
          </div>
        )}
      </section>

      {notice && <p className="notice">{notice}</p>}

      {/* 14-day attendance trend */}
      <section className="card">
        <h2 className="card__title">Son 14 Gün — Geliş Oranı</h2>
        <PresenceTrendChart trend={trend} />
      </section>

      {/* Currently inside */}
      <section className="card">
        <h2 className="card__title">Şu an içeride olanlar</h2>
        {summary?.currently_in?.length ? (
          <ul className="presence">
            {summary.currently_in.map((p) => (
              <li key={p.user_id}>
                <strong>{p.full_name}</strong>
                {isHq && p.campus_name && (
                  <span className="badge badge--in">{p.campus_name}</span>
                )}
                <span className="muted small">{fmt(p.since)}'den beri</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">İçeride kimse yok.</p>
        )}
      </section>

      {/* Filters + logs */}
      <section className="card">
        <div className="filters">
          <label className="field field--inline">
            <span>Personel</span>
            <select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">Tümü</option>
              {staff.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field field--inline">
            <span>Gün</span>
            <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </label>
          <button className="btn btn--ghost" onClick={() => setDay("")}>
            Tüm günler
          </button>
          <div className="grow" />
          <button className="btn btn--primary" onClick={onExport}>
            Excel İndir
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                {isHq && <th>Kampüs</th>}
                <th>Tür</th>
                <th>Kaynak</th>
                <th>Durum</th>
                <th>Zaman</th>
              </tr>
            </thead>
            <tbody>
              {busy ? (
                <tr>
                  <td colSpan={isHq ? 6 : 5} className="muted">
                    Yükleniyor…
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 6 : 5} className="muted">
                    Kayıt bulunamadı.
                  </td>
                </tr>
              ) : (
                logs.map((l) => (
                  <tr key={l.id}>
                    <td>{l.user_full_name}</td>
                    {isHq && <td className="muted small">{l.campus_name || "—"}</td>}
                    <td>
                      <span
                        className={l.type === "IN" ? "badge badge--in" : "badge badge--out"}
                      >
                        {l.type === "IN" ? "GİRİŞ" : "ÇIKIŞ"}
                      </span>
                    </td>
                    <td>
                      {l.source === "director_manual" ? (
                        <span className="badge badge--manual" title={l.recorded_by_name ? `Giren: ${l.recorded_by_name}` : undefined}>
                          Müdür girişi
                        </span>
                      ) : (
                        <span className="muted small">QR okuma</span>
                      )}
                    </td>
                    <td>
                      {l.status === "auto_closed_by_system" ? (
                        <span className="badge badge--auto">Sistem kapattı</span>
                      ) : (
                        <span className="muted small">geçerli</span>
                      )}
                    </td>
                    <td>{fmt(l.scan_time)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
