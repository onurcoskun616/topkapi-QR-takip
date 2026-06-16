import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const STATUS_LABEL = {
  pending: "Onay bekliyor",
  active: "Aktif",
  disabled: "Devre dışı",
};

export default function Staff({ isHq }) {
  const { token } = useAuth();
  const [staff, setStaff] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStaff(await api.listStaff(token, { campusId: isHq ? campusId : undefined }));
    } catch (e) {
      setError(e.message);
    }
  }, [token, isHq, campusId]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (id, fn, msg) => {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(msg);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  const approve = (u) =>
    act(u.id, () => api.approveStaff(token, u.id), `${u.full_name} onaylandı.`);

  const reset = (u) => {
    if (
      !window.confirm(
        `${u.full_name} için cihaz kaydı sıfırlansın mı? Personel yeni telefonunu aynı numarayla yeniden tanıtabilir.`
      )
    )
      return;
    act(u.id, () => api.resetDevice(token, u.id), `${u.full_name} için cihaz sıfırlandı.`);
  };

  const disable = (u) => {
    if (!window.confirm(`${u.full_name} devre dışı bırakılsın mı?`)) return;
    act(u.id, () => api.disableStaff(token, u.id), `${u.full_name} devre dışı bırakıldı.`);
  };

  const pending = staff.filter((u) => u.status === "pending");
  const others = staff.filter((u) => u.status !== "pending");

  const Row = ({ u }) => (
    <tr>
      <td>
        <strong>{u.full_name}</strong>
        <div className="muted small">
          {u.job_title} · {u.branch}
        </div>
      </td>
      <td className="muted small">{u.phone || "—"}</td>
      {isHq && <td className="muted small">{u.campus_name || "—"}</td>}
      <td>
        <span
          className={
            u.status === "active"
              ? "badge badge--in"
              : u.status === "pending"
                ? "badge badge--auto"
                : "badge badge--out"
          }
        >
          {STATUS_LABEL[u.status]}
        </span>
      </td>
      <td>
        {u.has_device ? (
          <span className="badge badge--in">Cihaz bağlı</span>
        ) : (
          <span className="muted small">cihaz yok</span>
        )}
      </td>
      <td className="actions">
        {u.status === "pending" && (
          <button
            className="btn btn--primary btn--sm"
            disabled={busyId === u.id}
            onClick={() => approve(u)}
          >
            Onayla
          </button>
        )}
        {u.status === "active" && (
          <>
            <button
              className="btn btn--ghost btn--sm"
              disabled={busyId === u.id || !u.has_device}
              onClick={() => reset(u)}
              title="Telefon değişikliği için cihaz kaydını sıfırlar"
            >
              Cihazı Sıfırla
            </button>
            <button
              className="btn btn--warn btn--sm"
              disabled={busyId === u.id}
              onClick={() => disable(u)}
            >
              Devre Dışı
            </button>
          </>
        )}
        {u.status === "disabled" && (
          <button
            className="btn btn--primary btn--sm"
            disabled={busyId === u.id}
            onClick={() => approve(u)}
          >
            Yeniden Aktifleştir
          </button>
        )}
      </td>
    </tr>
  );

  const cols = isHq ? 6 : 5;

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

      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <section className="card">
        <h2 className="card__title">Onay Bekleyenler ({pending.length})</h2>
        {pending.length === 0 ? (
          <p className="muted">Bekleyen kayıt yok.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ad Soyad</th>
                  <th>Telefon</th>
                  {isHq && <th>Kampüs</th>}
                  <th>Durum</th>
                  <th>Cihaz</th>
                  <th>İşlem</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((u) => (
                  <Row key={u.id} u={u} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card__title">Personel ({others.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Ad Soyad</th>
                <th>Telefon</th>
                {isHq && <th>Kampüs</th>}
                <th>Durum</th>
                <th>Cihaz</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {others.length === 0 ? (
                <tr>
                  <td colSpan={cols} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                others.map((u) => <Row key={u.id} u={u} />)
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
