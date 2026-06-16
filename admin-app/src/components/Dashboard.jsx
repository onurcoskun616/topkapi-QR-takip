import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api, downloadCsv } from "../api";

function todayLocalISO() {
  // YYYY-MM-DD in the browser's local time (good enough for the day filter).
  const d = new Date();
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

const fmt = (iso) =>
  new Date(iso).toLocaleString("tr-TR", {
    dateStyle: "short",
    timeStyle: "medium",
  });

export default function Dashboard() {
  const { token } = useAuth();
  const [summary, setSummary] = useState(null);
  const [users, setUsers] = useState([]);
  const [logs, setLogs] = useState([]);
  const [userId, setUserId] = useState("");
  const [day, setDay] = useState(todayLocalISO());
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.todaySummary(token));
    } catch (e) {
      setError(e.message);
    }
  }, [token]);

  const loadLogs = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setLogs(await api.logs(token, { userId, day }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [token, userId, day]);

  useEffect(() => {
    api.listUsers(token).then(setUsers).catch((e) => setError(e.message));
    loadSummary();
  }, [token, loadSummary]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  const onExport = async () => {
    try {
      await downloadCsv(token, { userId, day });
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
        <div className="kpi kpi--action">
          <button className="btn btn--warn" onClick={onRunAutoClose}>
            Gece Kapanışını Çalıştır
          </button>
          <span className="muted small">İçeride kalanları kapatır</span>
        </div>
      </section>

      {notice && <p className="notice">{notice}</p>}

      {/* Currently inside */}
      <section className="card">
        <h2 className="card__title">Şu an içeride olanlar</h2>
        {summary?.currently_in?.length ? (
          <ul className="presence">
            {summary.currently_in.map((p) => (
              <li key={p.user_id}>
                <strong>{p.full_name}</strong>
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
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field field--inline">
            <span>Gün</span>
            <input
              type="date"
              value={day}
              onChange={(e) => setDay(e.target.value)}
            />
          </label>
          <button className="btn btn--ghost" onClick={() => setDay("")}>
            Tüm günler
          </button>
          <div className="grow" />
          <button className="btn btn--primary" onClick={onExport}>
            CSV İndir
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                <th>Tür</th>
                <th>Durum</th>
                <th>Zaman</th>
              </tr>
            </thead>
            <tbody>
              {busy ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Yükleniyor…
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Kayıt bulunamadı.
                  </td>
                </tr>
              ) : (
                logs.map((l) => (
                  <tr key={l.id}>
                    <td>{l.user_full_name}</td>
                    <td>
                      <span
                        className={
                          l.type === "IN" ? "badge badge--in" : "badge badge--out"
                        }
                      >
                        {l.type === "IN" ? "GİRİŞ" : "ÇIKIŞ"}
                      </span>
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
