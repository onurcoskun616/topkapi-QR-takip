import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

// Default to the last 30 days so the panel opens with recent activity.
function isoDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

function fmt(dt) {
  try {
    return new Date(dt).toLocaleString("tr-TR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dt;
  }
}

export default function LocationAlerts({ isHq }) {
  const { token } = useAuth();
  const [entries, setEntries] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [startDate, setStartDate] = useState(isoDaysAgo(30));
  const [endDate, setEndDate] = useState(isoDaysAgo(0));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.locationAlerts(token, {
        campusId: isHq && campusId ? Number(campusId) : undefined,
        startDate,
        endDate,
      });
      setEntries(res.entries || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [token, isHq, campusId, startDate, endDate]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      <section className="card">
        <h2 className="card__title">Konum Uyarıları</h2>
        <p className="muted small">
          Personelin okul konumundan uzaktayken yaptığı QR okuma denemeleri.
          Bu denemelerde giriş/çıkış <strong>kaydedilmez</strong>; aşağıda yalnızca
          bilgilendirme amacıyla listelenir. Konum doğrulaması, kampüsün
          koordinatları <em>Kampüsler</em> sekmesinden girildiğinde devreye girer.
        </p>

        <div className="filters">
          {isHq && (
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
          )}
          <label className="field field--inline">
            <span>Başlangıç</span>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </label>
          <label className="field field--inline">
            <span>Bitiş</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        </div>

        {error && <p className="error">{error}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tarih / Saat</th>
                <th>Personel</th>
                <th>Görev / Branş</th>
                <th>Kampüs</th>
                <th>Uzaklık</th>
                <th>Konum</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    {busy ? "Yükleniyor…" : "Bu aralıkta uzaktan deneme kaydı yok."}
                  </td>
                </tr>
              ) : (
                entries.map((e) => (
                  <tr key={e.id}>
                    <td className="small">{fmt(e.created_at)}</td>
                    <td>
                      <strong>{e.full_name}</strong>
                    </td>
                    <td className="small muted">
                      {[e.job_title, e.branch].filter(Boolean).join(" / ") || "—"}
                    </td>
                    <td>{e.campus_name || "—"}</td>
                    <td>
                      <span className="badge badge--out">~{e.distance_m} m</span>
                      {e.accuracy_m != null && (
                        <span className="muted small"> (±{e.accuracy_m} m)</span>
                      )}
                    </td>
                    <td>
                      <a
                        href={e.maps_url}
                        target="_blank"
                        rel="noreferrer"
                        className="link"
                      >
                        Haritada gör
                      </a>
                    </td>
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
