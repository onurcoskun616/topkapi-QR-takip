import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const EMPTY = { date: "", name: "", campus_id: "" };

export default function Holidays({ isHq }) {
  const { token } = useAuth();
  const [holidays, setHolidays] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setHolidays(await api.listHolidays(token));
    } catch (e) {
      setError(e.message);
    }
  }, [token]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    load();
  }, [load]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.date || !form.name) {
      setError("Tarih ve ad gerekli.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createHoliday(token, {
        date: form.date,
        name: form.name,
        // Director: backend pins to own campus. hq: "" → national (all campuses).
        campus_id: isHq && form.campus_id ? Number(form.campus_id) : null,
      });
      setNotice("Tatil kaydı eklendi.");
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (h) => {
    if (!window.confirm(`${h.date} — ${h.name} tatili silinsin mi?`)) return;
    setError(null);
    try {
      await api.deleteHoliday(token, h.id);
      setNotice("Tatil kaydı silindi.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="stack two-col">
      <section className="card">
        <h2 className="card__title">Yeni Tatil / Kapanış</h2>
        <p className="muted small">
          Tatil günleri devamsızlık sayımından otomatik düşülür — o gün için kimseden giriş
          beklenmez. {isHq
            ? "Kampüs seçmezseniz tüm kampüsler için (resmi/ulusal) tatil tanımlanır."
            : "Tanımladığınız tatil yalnızca kendi kampüsünüz için geçerlidir."}
        </p>
        <form className="stack" onSubmit={onSubmit}>
          <label className="field">
            <span>Tarih</span>
            <input type="date" value={form.date} onChange={onChange("date")} required />
          </label>
          <label className="field">
            <span>Ad (örn. Ramazan Bayramı)</span>
            <input
              type="text"
              maxLength={120}
              value={form.name}
              onChange={onChange("name")}
              required
            />
          </label>
          {isHq && (
            <label className="field">
              <span>Kapsam</span>
              <select value={form.campus_id} onChange={onChange("campus_id")}>
                <option value="">Tüm kampüsler (ulusal/resmi)</option>
                {campuses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          {error && <p className="error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy ? "Kaydediliyor…" : "Ekle"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2 className="card__title">Tatil Günleri ({holidays.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Ad</th>
                <th>Kapsam</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {holidays.length === 0 ? (
                <tr>
                  <td colSpan={4} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                holidays.map((h) => {
                  const national = h.campus_id == null;
                  const canDelete = isHq || !national;
                  return (
                    <tr key={h.id}>
                      <td>{h.date}</td>
                      <td>{h.name}</td>
                      <td>
                        {national ? (
                          <span className="badge badge--in">Tüm kampüsler</span>
                        ) : (
                          <span className="badge badge--auto">{h.campus_name || "Kampüs"}</span>
                        )}
                      </td>
                      <td className="actions">
                        {canDelete ? (
                          <button className="btn btn--warn btn--sm" onClick={() => remove(h)}>
                            Sil
                          </button>
                        ) : (
                          <span className="muted small">genel merkez</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
