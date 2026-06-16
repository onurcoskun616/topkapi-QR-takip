import { Fragment, useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const STATUS_LABEL = { active: "Aktif", cancelled: "İptal edildi" };

const EMPTY_FORM = { user_id: "", leave_type: "", start_date: "", end_date: "", note: "" };

export default function Leaves({ isHq }) {
  const { token } = useAuth();
  const [leaves, setLeaves] = useState([]);
  const [staff, setStaff] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [suggestedTypes, setSuggestedTypes] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [statusFilter, setStatusFilter] = useState("active");
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const [editId, setEditId] = useState(null);
  const [editForm, setEditForm] = useState({ leave_type: "", start_date: "", end_date: "", note: "" });
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setLeaves(
        await api.listLeaves(token, {
          campusId: isHq ? campusId : undefined,
          status: statusFilter || undefined,
        })
      );
    } catch (e) {
      setError(e.message);
    }
  }, [token, isHq, campusId, statusFilter]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
    api
      .leaveTypes(token)
      .then((r) => setSuggestedTypes(r.suggested))
      .catch(() => {});
  }, [isHq, token]);

  useEffect(() => {
    api
      .listStaff(token, { status: "active", campusId: isHq ? campusId : undefined })
      .then(setStaff)
      .catch(() => {});
  }, [token, isHq, campusId]);

  useEffect(() => {
    load();
  }, [load]);

  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createLeave(token, { ...form, user_id: Number(form.user_id) });
      setNotice("İzin/devamsızlık kaydı oluşturuldu.");
      setForm(EMPTY_FORM);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (lv) => {
    setEditId(lv.id);
    setEditError(null);
    setEditForm({
      leave_type: lv.leave_type,
      start_date: lv.start_date,
      end_date: lv.end_date,
      note: lv.note || "",
    });
  };

  const cancelEdit = () => {
    setEditId(null);
    setEditError(null);
  };

  const saveEdit = async (lv) => {
    setEditBusy(true);
    setEditError(null);
    try {
      await api.updateLeave(token, lv.id, editForm);
      setNotice("İzin kaydı güncellendi.");
      setEditId(null);
      await load();
    } catch (err) {
      setEditError(err.message);
    } finally {
      setEditBusy(false);
    }
  };

  const cancelLeave = async (lv) => {
    if (
      !window.confirm(
        `${lv.user_full_name} için '${lv.leave_type}' kaydı iptal edilsin mi? Personel normal şekilde QR okutabilir hale gelir.`
      )
    )
      return;
    setError(null);
    try {
      await api.cancelLeave(token, lv.id);
      setNotice("İzin kaydı iptal edildi.");
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="stack two-col">
      <section className="card">
        <h2 className="card__title">Yeni İzin / Devamsızlık Kaydı</h2>
        <form className="stack" onSubmit={onSubmit}>
          {isHq && (
            <label className="field">
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
          )}
          <label className="field">
            <span>Personel</span>
            <select value={form.user_id} onChange={onChange("user_id")} required>
              <option value="">Personel seçin…</option>
              {staff.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Tür / Sebep</span>
            <input
              list="leave-type-suggestions"
              value={form.leave_type}
              onChange={onChange("leave_type")}
              placeholder="Sağlık raporu, Ücretli izin, vb."
              required
            />
            <datalist id="leave-type-suggestions">
              {suggestedTypes.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Başlangıç</span>
            <input type="date" value={form.start_date} onChange={onChange("start_date")} required />
          </label>
          <label className="field">
            <span>Bitiş</span>
            <input type="date" value={form.end_date} onChange={onChange("end_date")} required />
          </label>
          <label className="field">
            <span>Not (opsiyonel)</span>
            <input
              type="text"
              maxLength={255}
              value={form.note}
              onChange={onChange("note")}
            />
          </label>

          {error && <p className="error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}

          <button className="btn btn--primary" disabled={busy} type="submit">
            {busy ? "Kaydediliyor…" : "Oluştur"}
          </button>
        </form>
      </section>

      <section className="card">
        <div className="filters">
          <h2 className="card__title" style={{ margin: 0 }}>
            İzin / Devamsızlık Kayıtları ({leaves.length})
          </h2>
          <div className="grow" />
          <label className="field field--inline">
            <span>Durum</span>
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">Tümü</option>
              <option value="active">Aktif</option>
              <option value="cancelled">İptal edildi</option>
            </select>
          </label>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                {isHq && <th>Kampüs</th>}
                <th>Tür</th>
                <th>Tarih Aralığı</th>
                <th>Durum</th>
                <th>Oluşturan</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {leaves.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 7 : 6} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                leaves.map((lv) => (
                  <Fragment key={lv.id}>
                    <tr>
                      <td>{lv.user_full_name}</td>
                      {isHq && <td className="muted small">{lv.campus_name || "—"}</td>}
                      <td>{lv.leave_type}</td>
                      <td className="muted small">
                        {lv.start_date} → {lv.end_date}
                      </td>
                      <td>
                        <span
                          className={lv.status === "active" ? "badge badge--in" : "badge badge--out"}
                        >
                          {STATUS_LABEL[lv.status]}
                        </span>
                      </td>
                      <td className="muted small">{lv.created_by_name || "—"}</td>
                      <td className="actions">
                        {lv.status === "active" && (
                          <>
                            <button
                              className="btn btn--ghost btn--sm"
                              onClick={() => (editId === lv.id ? cancelEdit() : startEdit(lv))}
                            >
                              Düzelt
                            </button>
                            <button className="btn btn--warn btn--sm" onClick={() => cancelLeave(lv)}>
                              İptal Et
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                    {editId === lv.id && (
                      <tr className="manual-row">
                        <td colSpan={isHq ? 7 : 6}>
                          <div className="manual-form">
                            <span className="manual-form__title">
                              <strong>{lv.user_full_name}</strong> kaydını düzelt — örn. personel
                              aslında gelip taradıysa aralığı kısaltın
                            </span>
                            <label className="field field--inline">
                              <span>Tür</span>
                              <input
                                list="leave-type-suggestions"
                                value={editForm.leave_type}
                                onChange={(e) =>
                                  setEditForm({ ...editForm, leave_type: e.target.value })
                                }
                              />
                            </label>
                            <label className="field field--inline">
                              <span>Başlangıç</span>
                              <input
                                type="date"
                                value={editForm.start_date}
                                onChange={(e) =>
                                  setEditForm({ ...editForm, start_date: e.target.value })
                                }
                              />
                            </label>
                            <label className="field field--inline">
                              <span>Bitiş</span>
                              <input
                                type="date"
                                value={editForm.end_date}
                                onChange={(e) =>
                                  setEditForm({ ...editForm, end_date: e.target.value })
                                }
                              />
                            </label>
                            <label className="field field--inline manual-form__note">
                              <span>Not</span>
                              <input
                                type="text"
                                maxLength={255}
                                value={editForm.note}
                                onChange={(e) => setEditForm({ ...editForm, note: e.target.value })}
                              />
                            </label>
                            <div className="actions">
                              <button
                                className="btn btn--primary btn--sm"
                                disabled={editBusy}
                                onClick={() => saveEdit(lv)}
                              >
                                {editBusy ? "Kaydediliyor…" : "Kaydet"}
                              </button>
                              <button className="btn btn--ghost btn--sm" onClick={cancelEdit}>
                                Vazgeç
                              </button>
                            </div>
                            {editError && <p className="error">{editError}</p>}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
