import { Fragment, useEffect, useState } from "react";
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
  const [passwordTarget, setPasswordTarget] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [passwordError, setPasswordError] = useState(null);
  const [passwordBusy, setPasswordBusy] = useState(false);

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

  const enable = async (d) => {
    try {
      await api.enableDirector(token, d.id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const openPasswordForm = (d) => {
    setPasswordTarget(d);
    setNewPassword("");
    setPasswordError(null);
  };

  const closePasswordForm = () => {
    setPasswordTarget(null);
    setNewPassword("");
    setPasswordError(null);
  };

  const submitPassword = async (e) => {
    e.preventDefault();
    setPasswordBusy(true);
    setPasswordError(null);
    try {
      await api.updateDirectorPassword(token, passwordTarget.id, newPassword);
      setNotice(`${passwordTarget.full_name} için şifre güncellendi.`);
      closePasswordForm();
    } catch (err) {
      setPasswordError(err.message);
    } finally {
      setPasswordBusy(false);
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
                <Fragment key={d.id}>
                  <tr>
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
                      <div className="actions">
                        {d.status === "active" ? (
                          <button className="btn btn--warn btn--sm" onClick={() => disable(d)}>
                            Devre Dışı
                          </button>
                        ) : (
                          <button className="btn btn--primary btn--sm" onClick={() => enable(d)}>
                            Aktif Et
                          </button>
                        )}
                        <button className="btn btn--ghost btn--sm" onClick={() => openPasswordForm(d)}>
                          Şifre Değiştir
                        </button>
                      </div>
                    </td>
                  </tr>
                  {passwordTarget?.id === d.id && (
                    <tr className="manual-row">
                      <td colSpan={5}>
                        <form className="manual-form" onSubmit={submitPassword}>
                          <span className="manual-form__title">
                            <strong>{d.full_name}</strong> için yeni şifre belirle
                          </span>
                          <label className="field field--inline">
                            <span>Yeni şifre (min 8)</span>
                            <input
                              type="password"
                              minLength={8}
                              required
                              autoFocus
                              value={newPassword}
                              onChange={(e) => setNewPassword(e.target.value)}
                            />
                          </label>
                          <div className="actions">
                            <button className="btn btn--primary btn--sm" disabled={passwordBusy} type="submit">
                              {passwordBusy ? "Kaydediliyor…" : "Kaydet"}
                            </button>
                            <button
                              className="btn btn--ghost btn--sm"
                              type="button"
                              disabled={passwordBusy}
                              onClick={closePasswordForm}
                            >
                              Vazgeç
                            </button>
                          </div>
                          {passwordError && <p className="error">{passwordError}</p>}
                        </form>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
