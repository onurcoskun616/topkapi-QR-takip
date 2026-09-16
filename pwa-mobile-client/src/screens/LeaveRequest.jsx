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

const EMPTY = {
  leave_type: "",
  start_date: "",
  end_date: "",
  hourly: false,
  start_time: "",
  end_time: "",
  note: "",
};

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
    if (!form.leave_type || !form.start_date) {
      setError("Lütfen tür ve tarih girin.");
      return;
    }
    let payload;
    if (form.hourly) {
      if (!form.start_time || !form.end_time) {
        setError("Saatlik izin için başlangıç ve bitiş saatini girin.");
        return;
      }
      if (form.end_time <= form.start_time) {
        setError("Bitiş saati, başlangıç saatinden sonra olmalıdır.");
        return;
      }
      payload = {
        leave_type: form.leave_type,
        start_date: form.start_date,
        end_date: form.start_date, // hourly leave is a single day
        start_time: form.start_time,
        end_time: form.end_time,
        note: form.note || null,
      };
    } else {
      if (!form.end_date) {
        setError("Lütfen bitiş tarihini girin.");
        return;
      }
      if (form.end_date < form.start_date) {
        setError("Bitiş tarihi, başlangıçtan önce olamaz.");
        return;
      }
      payload = {
        leave_type: form.leave_type,
        start_date: form.start_date,
        end_date: form.end_date,
        note: form.note || null,
      };
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await requestLeave(payload);
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
          <div className="leave__mode">
            <button
              type="button"
              className={`btn btn--sm ${form.hourly ? "btn--ghost" : "btn--primary"}`}
              onClick={() => setForm({ ...form, hourly: false })}
              disabled={busy}
            >
              Tüm gün
            </button>
            <button
              type="button"
              className={`btn btn--sm ${form.hourly ? "btn--primary" : "btn--ghost"}`}
              onClick={() => setForm({ ...form, hourly: true })}
              disabled={busy}
            >
              Saatlik
            </button>
          </div>

          {form.hourly ? (
            <>
              <label className="field-label">
                Tarih
                <input
                  className="input"
                  type="date"
                  value={form.start_date}
                  onChange={onChange("start_date")}
                  disabled={busy}
                />
              </label>
              <label className="field-label">
                Başlangıç saati
                <input
                  className="input"
                  type="time"
                  value={form.start_time}
                  onChange={onChange("start_time")}
                  disabled={busy}
                />
              </label>
              <label className="field-label">
                Bitiş saati
                <input
                  className="input"
                  type="time"
                  value={form.end_time}
                  onChange={onChange("end_time")}
                  disabled={busy}
                />
              </label>
            </>
          ) : (
            <>
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
            </>
          )}
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
                    {lv.start_time && lv.end_time
                      ? `${lv.start_date} · ${lv.start_time.slice(0, 5)}–${lv.end_time.slice(0, 5)} (saatlik)`
                      : `${lv.start_date} → ${lv.end_date}`}
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
