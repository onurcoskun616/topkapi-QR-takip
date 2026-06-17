import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const EMPTY = { full_name: "", email: "", password: "", campus_id: "" };

export default function Directors() {
  const { token } = useAuth();
  const [directors, setDirectors] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listDirectors(token).then(setDirectors).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    api.campuses().then(setCampuses).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.createDirector(token, {
        ...form,
        campus_id: Number(form.campus_id),
      });
      setNotice(`${created.full_name} (müdür) oluşturuldu.`);
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const disable = async (d) => {
    if (!window.confirm(`${d.full_name} müdür hesabı devre dışı bırakılsın mı?`)) return;
    try {
      await api.disableDirector(token, d.id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="stack two-col">
      <section className="card">
        <h2 className="card__title">Yeni Kampüs Müdürü</h2>
        <form className="stack" onSubmit={onSubmit}>
          <label className="field">
            <span>Ad Soyad</span>
            <input value={form.full_name} onChange={onChange("full_name")} required />
          </label>
          <label className="field">
            <span>E-posta</span>
            <input type="email" value={form.email} onChange={onChange("email")} required />
          </label>
          <label className="field">
            <span>Şifre (min 8)</span>
            <input
              type="password"
              minLength={8}
              value={form.password}
              onChange={onChange("password")}
              required
            />
          </label>
          <label className="field">
            <span>Kampüs</span>
            <select value={form.campus_id} onChange={onChange("campus_id")} required>
              <option value="">Kampüs seçin…</option>
              {campuses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>

          {error && <p className="error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy ? "Kaydediliyor…" : "Oluştur"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2 className="card__title">Kampüs Müdürleri ({directors.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Ad Soyad</th>
                <th>E-posta</th>
                <th>Kampüs</th>
                <th>Durum</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {directors.map((d) => (
                <tr key={d.id}>
                  <td>{d.full_name}</td>
                  <td className="muted small">{d.email}</td>
                  <td>{d.campus_name || "—"}</td>
                  <td>
                    <span
                      className={
                        d.status === "active" ? "badge badge--in" : "badge badge--out"
                      }
                    >
                      {d.status === "active" ? "Aktif" : "Devre dışı"}
                    </span>
                  </td>
                  <td>
                    {d.status === "active" && (
                      <button className="btn btn--warn btn--sm" onClick={() => disable(d)}>
                        Devre Dışı
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
