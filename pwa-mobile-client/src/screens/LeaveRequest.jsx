import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const STATUS_LABEL = {
  requested: "Onay bekliyor",
  active: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
};

const STATUS_CLASS = {
  requested: "leave-pill leave-pill--pending",
  active: "leave-pill leave-pill--ok",
  rejected: "leave-pill leave-pill--no",
  cancelled: "leave-pill leave-pill--muted",
};

const EMPTY = { leave_type: "", start_date: "", end_date: "", note: "" };

export default function LeaveRequest({ onBack }) {
  const { requestLeave, myLeaves } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [types, setTypes] = useState([]);
  const [leaves, setLeaves] = useState([]);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const reload = () => myLeaves().then(setLeaves).catch(() => {});

  useEffect(() => {
    api.leaveTypes().then((r) => setTypes(r.suggested)).catch(() => {});
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!form.leave_type || !form.start_date || !form.end_date) {
      setError("Lütfen tür ve tarih aralığını girin.");
      return;
    }
    if (form.end_date < form.start_date) {
      setError("Bitiş tarihi, başlangıçtan önce olamaz.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestLeave(form);
      setNotice("İzin talebiniz müdürünüze iletildi.");
      setForm(EMPTY);
      await reload();
    } catch (err) {
      setError(err.message || "Talep gönderilemedi.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screen leave">
      <header className="scanner__header">
        <button className="link" onClick={onBack}>
          ← Geri
        </button>
        <span className="scanner__name">İzin Talebi</span>
      </header>

      <div className="leave__body">
        <form className="leave__form" onSubmit={onSubmit}>
          <label className="field-label">
            İzin türü
            <input
              className="input"
              list="leave-types"
              placeholder="Ücretli izin, Ücretsiz izin, Sağlık raporu…"
              value={form.leave_type}
              onChange={onChange("leave_type")}
              disabled={busy}
            />
            <datalist id="leave-types">
              {types.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </label>
          <label className="field-label">
            Başlangıç
            <input
              className="input"
              type="date"
              value={form.start_date}
              onChange={onChange("start_date")}
              disabled={busy}
            />
          </label>
          <label className="field-label">
            Bitiş
            <input
              className="input"
              type="date"
              value={form.end_date}
              onChange={onChange("end_date")}
              disabled={busy}
            />
          </label>
          <label className="field-label">
            Açıklama (opsiyonel)
            <input
              className="input"
              type="text"
              maxLength={255}
              value={form.note}
              onChange={onChange("note")}
              disabled={busy}
            />
          </label>

          {error && <p className="error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy ? "Gönderiliyor…" : "Talep Gönder"}
          </button>
          <p className="muted login__hint">
            Talebiniz kampüs müdürünüzün onayına gönderilir. Onaylanınca o tarih
            aralığında QR okutmanız gerekmez.
          </p>
        </form>

        <div className="leave__list">
          <h2 className="leave__list-title">Taleplerim</h2>
          {leaves.length === 0 ? (
            <p className="muted">Henüz bir talebiniz yok.</p>
          ) : (
            <ul className="leave__items">
              {leaves.map((lv) => (
                <li key={lv.id} className="leave__item">
                  <div className="leave__item-main">
                    <strong>{lv.leave_type}</strong>
                    <span className={STATUS_CLASS[lv.status] || "leave-pill"}>
                      {STATUS_LABEL[lv.status] || lv.status}
                    </span>
                  </div>
                  <div className="muted small">
                    {lv.start_date} → {lv.end_date}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
