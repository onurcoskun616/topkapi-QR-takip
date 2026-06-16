import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const EMPTY = {
  full_name: "",
  phone: "",
  job_title: "",
  branch: "",
  campus_id: "",
};

export default function Register() {
  const { register } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [campuses, setCampuses] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .campuses()
      .then(setCampuses)
      .catch(() => setError("Kampüs listesi yüklenemedi. Bağlantıyı kontrol edin."));
  }, []);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.full_name || !form.phone || !form.job_title || !form.branch || !form.campus_id) {
      setError("Lütfen tüm alanları doldurun.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register({ ...form, campus_id: Number(form.campus_id) });
    } catch (err) {
      setError(err.message || "Kayıt başarısız.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screen center login">
      <form className="login__card" onSubmit={onSubmit}>
        <h1 className="login__title">Topkapı Okulları</h1>
        <p className="muted login__sub">Personel Kaydı</p>

        <input
          className="input"
          placeholder="Ad Soyad"
          autoComplete="name"
          value={form.full_name}
          onChange={onChange("full_name")}
          disabled={busy}
        />
        <input
          className="input"
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          placeholder="Telefon (05XX XXX XX XX)"
          value={form.phone}
          onChange={onChange("phone")}
          disabled={busy}
        />
        <input
          className="input"
          placeholder="Görev (örn. Öğretmen, İdari)"
          value={form.job_title}
          onChange={onChange("job_title")}
          disabled={busy}
        />
        <input
          className="input"
          placeholder="Branş (örn. Matematik)"
          value={form.branch}
          onChange={onChange("branch")}
          disabled={busy}
        />
        <select
          className="input"
          value={form.campus_id}
          onChange={onChange("campus_id")}
          disabled={busy || campuses.length === 0}
        >
          <option value="">Kampüs seçin…</option>
          {campuses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>

        {error && <p className="error">{error}</p>}

        <button className="btn btn--primary" disabled={busy} type="submit">
          {busy ? "Kaydediliyor…" : "Kaydol"}
        </button>

        <p className="muted login__hint">
          Kaydınız kampüs müdürünüzün onayına gönderilir. Onaylandıktan sonra bu
          telefon kalıcı kimliğiniz olur; ertesi günler uygulama doğrudan kamerayı
          açar. Telefon değiştirirseniz müdürünüzden sıfırlama isteyin.
        </p>
      </form>
    </div>
  );
}
