import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api, apiBaseUrl } from "../api";

const EMPTY = {
  title: "",
  body: "",
  campus_id: "",
  starts_at: "",
  ends_at: "",
};

// Render a stored UTC datetime in campus-local time for the table.
function fmt(dt) {
  if (!dt) return "—";
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

export default function Announcements({ isHq }) {
  const { token } = useAuth();
  const [items, setItems] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [image, setImage] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await api.listAnnouncements(token));
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
    if (!form.title && !form.body && !image) {
      setError("Bir başlık, metin veya görsel ekleyin.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createAnnouncement(token, {
        title: form.title,
        body: form.body,
        campusId: isHq && form.campus_id ? Number(form.campus_id) : null,
        startsAt: form.starts_at || null,
        endsAt: form.ends_at || null,
        image,
      });
      setNotice("Duyuru yayınlandı. Kiosk ekranlarında birkaç saniye içinde görünür.");
      setForm(EMPTY);
      setImage(null);
      e.target.reset?.();
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (a) => {
    setError(null);
    try {
      await api.setAnnouncementActive(token, a.id, !a.active);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const remove = async (a) => {
    if (!window.confirm("Bu duyuru silinsin mi?")) return;
    setError(null);
    try {
      await api.deleteAnnouncement(token, a.id);
      setNotice("Duyuru silindi.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="stack two-col">
      <section className="card">
        <h2 className="card__title">Yeni Duyuru / Görsel</h2>
        <p className="muted small">
          Kiosk (tablet) ekranında tam ekran gösterilir; QR kod sağ alt köşeye
          küçülür. Özel gün tebriği, genel duyuru veya etkinlik görseli
          paylaşabilirsiniz. Bitiş zamanı verirseniz o anda otomatik kaybolur;
          vermezseniz siz kaldırana (veya pasife alana) kadar kalır.
          {isHq
            ? " Kampüs seçmezseniz tüm kampüslerin kiosklarında gösterilir."
            : " Duyuru yalnızca kendi kampüsünüzün kioskunda gösterilir."}
        </p>
        <form className="stack" onSubmit={onSubmit}>
          <label className="field">
            <span>Başlık (isteğe bağlı)</span>
            <input
              type="text"
              maxLength={160}
              value={form.title}
              onChange={onChange("title")}
              placeholder="Örn. 23 Nisan Kutlu Olsun"
            />
          </label>
          <label className="field">
            <span>Metin (isteğe bağlı)</span>
            <textarea
              rows={3}
              value={form.body}
              onChange={onChange("body")}
              placeholder="Ekranda gösterilecek açıklama…"
            />
          </label>
          <label className="field">
            <span>Görsel (isteğe bağlı, en fazla 5 MB)</span>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setImage(e.target.files?.[0] || null)}
            />
          </label>
          <div className="row two">
            <label className="field">
              <span>Başlangıç (isteğe bağlı)</span>
              <input
                type="datetime-local"
                value={form.starts_at}
                onChange={onChange("starts_at")}
              />
            </label>
            <label className="field">
              <span>Bitiş (isteğe bağlı)</span>
              <input
                type="datetime-local"
                value={form.ends_at}
                onChange={onChange("ends_at")}
              />
            </label>
          </div>
          {isHq && (
            <label className="field">
              <span>Kapsam</span>
              <select value={form.campus_id} onChange={onChange("campus_id")}>
                <option value="">Tüm kampüsler</option>
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
            {busy ? "Yayınlanıyor…" : "Yayınla"}
          </button>
        </form>
      </section>

      <section className="card">
        <h2 className="card__title">Duyurular ({items.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Görsel</th>
                <th>İçerik</th>
                <th>Kapsam</th>
                <th>Bitiş</th>
                <th>Durum</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="muted">
                    Henüz duyuru yok.
                  </td>
                </tr>
              ) : (
                items.map((a) => {
                  const national = a.campus_id == null;
                  const canManage = isHq || !national;
                  return (
                    <tr key={a.id}>
                      <td>
                        {a.image_url ? (
                          <img
                            src={`${apiBaseUrl}${a.image_url}`}
                            alt=""
                            style={{
                              width: 64,
                              height: 44,
                              objectFit: "cover",
                              borderRadius: 6,
                            }}
                          />
                        ) : (
                          <span className="muted small">—</span>
                        )}
                      </td>
                      <td>
                        {a.title && <strong>{a.title}</strong>}
                        {a.title && a.body && <br />}
                        {a.body && <span className="muted small">{a.body}</span>}
                      </td>
                      <td>
                        {national ? (
                          <span className="badge badge--in">Tüm kampüsler</span>
                        ) : (
                          <span className="badge badge--auto">
                            {a.campus_name || "Kampüs"}
                          </span>
                        )}
                      </td>
                      <td className="small">{fmt(a.ends_at)}</td>
                      <td>
                        {a.active ? (
                          <span className="badge badge--in">Aktif</span>
                        ) : (
                          <span className="badge badge--out">Pasif</span>
                        )}
                      </td>
                      <td className="actions">
                        {canManage ? (
                          <>
                            <button
                              className="btn btn--ghost btn--sm"
                              onClick={() => toggle(a)}
                            >
                              {a.active ? "Durdur" : "Yayınla"}
                            </button>
                            <button
                              className="btn btn--warn btn--sm"
                              onClick={() => remove(a)}
                            >
                              Sil
                            </button>
                          </>
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
