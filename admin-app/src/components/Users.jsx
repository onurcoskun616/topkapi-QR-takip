import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const EMPTY = { full_name: "", email: "", password: "", role: "teacher" };

export default function Users() {
  const { token } = useAuth();
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () =>
    api.listUsers(token).then(setUsers).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.createUser(token, form);
      setNotice(`${created.full_name} oluşturuldu.`);
      setForm(EMPTY);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack two-col">
      <section className="card">
        <h2 className="card__title">Yeni Kullanıcı</h2>
        <form className="stack" onSubmit={onSubmit}>
          <label className="field">
            <span>Ad Soyad</span>
            <input value={form.full_name} onChange={onChange("full_name")} required />
          </label>
          <label className="field">
            <span>E-posta</span>
            <input
              type="email"
              value={form.email}
              onChange={onChange("email")}
              required
            />
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
            <span>Rol</span>
            <select value={form.role} onChange={onChange("role")}>
              <option value="teacher">Öğretmen</option>
              <option value="admin">Yönetici</option>
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
        <h2 className="card__title">Kullanıcılar ({users.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Ad Soyad</th>
                <th>E-posta</th>
                <th>Rol</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.full_name}</td>
                  <td className="muted small">{u.email}</td>
                  <td>
                    <span
                      className={
                        u.role === "admin" ? "badge badge--auto" : "badge badge--in"
                      }
                    >
                      {u.role === "admin" ? "Yönetici" : "Öğretmen"}
                    </span>
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
