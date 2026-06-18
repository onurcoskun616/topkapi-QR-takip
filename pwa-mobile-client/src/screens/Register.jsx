import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const EMPTY = {
  full_name: "",
  phone: "",
  tc_kimlik_no: "",
  job_title: "",
  branch: "",
  birth_date: "",
  campus_id: "",
};

// Turkish mobile number: a leading 0/+90 plus 10 digits starting with 5. Warns
// with the exact digit count so "too few" and "too many" read differently.
function phoneWarning(raw) {
  if (!raw) return null;
  let digits = raw.replace(/\D/g, "");
  if (digits.startsWith("90") && digits.length > 10) digits = digits.slice(2);
  if (digits.startsWith("0")) digits = digits.slice(1);
  if (digits.length < 10) {
    return `Telefon numarası eksik: ${digits.length}/10 hane girildi.`;
  }
  if (digits.length > 10) {
    return `Telefon numarası fazla karakter içeriyor: ${digits.length}/10 hane girildi.`;
  }
  if (digits[0] !== "5") {
    return "05XX XXX XX XX biçiminde bir cep telefonu numarası girin.";
  }
  return null;
}

// Standard TC Kimlik No checksum: digit 10 from the weighted odd/even digit
// sums, digit 11 from the sum of the first ten digits.
function tcKimlikValid(tc) {
  if (!/^[1-9]\d{10}$/.test(tc)) return false;
  const d = tc.split("").map(Number);
  const oddSum = d[0] + d[2] + d[4] + d[6] + d[8];
  const evenSum = d[1] + d[3] + d[5] + d[7];
  if ((oddSum * 7 - evenSum) % 10 !== d[9]) return false;
  return d.slice(0, 10).reduce((a, b) => a + b, 0) % 10 === d[10];
}

function tcKimlikWarning(raw) {
  if (!raw) return null;
  if (!/^\d+$/.test(raw)) return "TC kimlik numarası sadece rakam içermelidir.";
  if (raw.length < 11) {
    return `TC kimlik numarası eksik: ${raw.length}/11 hane girildi.`;
  }
  if (raw.length > 11) {
    return `TC kimlik numarası fazla karakter içeriyor: ${raw.length}/11 hane girildi.`;
  }
  if (!tcKimlikValid(raw)) return "Geçersiz TC kimlik numarası.";
  return null;
}

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

  const phoneHint = phoneWarning(form.phone);
  const tcHint = tcKimlikWarning(form.tc_kimlik_no);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (
      !form.full_name ||
      !form.phone ||
      !form.tc_kimlik_no ||
      !form.job_title ||
      !form.branch ||
      !form.birth_date ||
      !form.campus_id
    ) {
      setError("Lütfen tüm alanları doldurun.");
      return;
    }
    if (phoneHint) {
      setError(phoneHint);
      return;
    }
    if (tcHint) {
      setError(tcHint);
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
        {phoneHint && <p className="field-hint">{phoneHint}</p>}
        <input
          className="input"
          type="text"
          inputMode="numeric"
          maxLength={11}
          placeholder="TC Kimlik No"
          value={form.tc_kimlik_no}
          onChange={onChange("tc_kimlik_no")}
          disabled={busy}
        />
        {tcHint && <p className="field-hint">{tcHint}</p>}
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
        <label className="field-label">
          Doğum tarihi
          <input
            className="input"
            type="date"
            value={form.birth_date}
            onChange={onChange("birth_date")}
            disabled={busy}
            max={new Date().toISOString().slice(0, 10)}
          />
        </label>
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
          telefon, TC kimlik no ve cihaz birlikte kalıcı kimliğiniz olur; ertesi
          günler uygulama doğrudan kamerayı açar. Telefon veya cihaz
          değiştirirseniz müdürünüzden sıfırlama isteyin.
        </p>
      </form>
    </div>
  );
}
