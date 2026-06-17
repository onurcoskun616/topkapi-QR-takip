import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const STATUS_LABEL = {
  pending: "Onay bekliyor",
  active: "Aktif",
  disabled: "Devre dışı",
};

// ISO weekday numbers (1=Mon … 7=Sun) with short Turkish labels.
const WEEKDAYS = [
  { n: 1, label: "Pzt" },
  { n: 2, label: "Sal" },
  { n: 3, label: "Çar" },
  { n: 4, label: "Per" },
  { n: 5, label: "Cum" },
  { n: 6, label: "Cmt" },
  { n: 7, label: "Paz" },
];

const DEFAULT_WORKING = [1, 2, 3, 4, 5];

function workingDaysLabel(days) {
  if (!days || days.length === 0) return "Pzt–Cum (varsayılan)";
  return WEEKDAYS.filter((d) => days.includes(d.n))
    .map((d) => d.label)
    .join(", ");
}

function nowLocal() {
  const d = new Date();
  const off = d.getTimezoneOffset();
  const local = new Date(d.getTime() - off * 60000).toISOString();
  return { date: local.slice(0, 10), time: local.slice(11, 16) };
}

// Parse pasted CSV/TSV roster lines into staff rows. Columns (in order):
// Ad Soyad, Telefon, Görev, Branş, Doğum (YYYY-AA-GG, opsiyonel). Separator
// may be comma, semicolon or tab. A header line is auto-skipped.
function parseRoster(text) {
  const out = [];
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  for (const line of lines) {
    const cells = line.split(/[\t;,]/).map((c) => c.trim());
    const [full_name, phone, job_title, branch, birth_date] = cells;
    // Skip an obvious header row.
    if (/ad\s*soyad|telefon/i.test(full_name) && /telefon|phone/i.test(phone || "")) continue;
    const row = { full_name, phone, job_title, branch };
    if (birth_date && /^\d{4}-\d{2}-\d{2}$/.test(birth_date)) row.birth_date = birth_date;
    const errors = [];
    if (!full_name || full_name.length < 2) errors.push("ad");
    if (!phone || phone.replace(/\D/g, "").length < 7) errors.push("telefon");
    if (!job_title) errors.push("görev");
    if (!branch) errors.push("branş");
    row._error = errors.length ? `eksik/geçersiz: ${errors.join(", ")}` : null;
    out.push(row);
  }
  return out;
}

export default function Staff({ isHq }) {
  const { token } = useAuth();
  const [staff, setStaff] = useState([]);
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const [manualForId, setManualForId] = useState(null);
  const [manualForm, setManualForm] = useState({ type: "IN", date: "", time: "", note: "" });
  const [manualBusy, setManualBusy] = useState(false);
  const [manualError, setManualError] = useState(null);

  const [workingForId, setWorkingForId] = useState(null);
  const [workingSel, setWorkingSel] = useState(DEFAULT_WORKING);
  const [workingBusy, setWorkingBusy] = useState(false);
  const [workingError, setWorkingError] = useState(null);

  const [showBulk, setShowBulk] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkCampusId, setBulkCampusId] = useState("");
  const [bulkRows, setBulkRows] = useState([]);
  const [bulkResult, setBulkResult] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkError, setBulkError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStaff(await api.listStaff(token, { campusId: isHq ? campusId : undefined }));
    } catch (e) {
      setError(e.message);
    }
  }, [token, isHq, campusId]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (id, fn, msg) => {
    setBusyId(id);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(msg);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  const approve = (u) =>
    act(u.id, () => api.approveStaff(token, u.id), `${u.full_name} onaylandı.`);

  const reset = (u) => {
    if (
      !window.confirm(
        `${u.full_name} için cihaz kaydı sıfırlansın mı? Personel yeni telefonunu aynı numarayla yeniden tanıtabilir.`
      )
    )
      return;
    act(u.id, () => api.resetDevice(token, u.id), `${u.full_name} için cihaz sıfırlandı.`);
  };

  const disable = (u) => {
    if (!window.confirm(`${u.full_name} devre dışı bırakılsın mı?`)) return;
    act(u.id, () => api.disableStaff(token, u.id), `${u.full_name} devre dışı bırakıldı.`);
  };

  const openManual = (u) => {
    setManualForId(u.id);
    setManualError(null);
    setManualForm({ type: "IN", ...nowLocal(), note: "" });
  };

  const closeManual = () => {
    setManualForId(null);
    setManualError(null);
  };

  const submitManual = async (e, u) => {
    e.preventDefault();
    setManualBusy(true);
    setManualError(null);
    try {
      await api.createManualLog(token, {
        user_id: u.id,
        type: manualForm.type,
        date: manualForm.date,
        time: `${manualForm.time}:00`,
        note: manualForm.note || undefined,
      });
      setNotice(`${u.full_name} için manuel ${manualForm.type === "IN" ? "giriş" : "çıkış"} kaydı eklendi.`);
      closeManual();
      await load();
    } catch (err) {
      setManualError(err.message);
    } finally {
      setManualBusy(false);
    }
  };

  const openWorking = (u) => {
    setWorkingForId(u.id);
    setWorkingError(null);
    setWorkingSel(u.working_days && u.working_days.length ? u.working_days : DEFAULT_WORKING);
  };

  const closeWorking = () => {
    setWorkingForId(null);
    setWorkingError(null);
  };

  const toggleDay = (n) =>
    setWorkingSel((sel) =>
      sel.includes(n) ? sel.filter((x) => x !== n) : [...sel, n].sort((a, b) => a - b)
    );

  const submitWorking = async (u) => {
    if (workingSel.length === 0) {
      setWorkingError("En az bir çalışma günü seçin (veya varsayılana sıfırlayın).");
      return;
    }
    setWorkingBusy(true);
    setWorkingError(null);
    try {
      await api.updateStaff(token, u.id, { working_days: workingSel });
      setNotice(`${u.full_name} için çalışma günleri güncellendi.`);
      closeWorking();
      await load();
    } catch (err) {
      setWorkingError(err.message);
    } finally {
      setWorkingBusy(false);
    }
  };

  const resetWorking = async (u) => {
    setWorkingBusy(true);
    setWorkingError(null);
    try {
      await api.updateStaff(token, u.id, { working_days: [] });
      setNotice(`${u.full_name} için çalışma günleri varsayılana (Pzt–Cum) sıfırlandı.`);
      closeWorking();
      await load();
    } catch (err) {
      setWorkingError(err.message);
    } finally {
      setWorkingBusy(false);
    }
  };

  const previewBulk = () => {
    setBulkResult(null);
    setBulkError(null);
    const rows = parseRoster(bulkText);
    if (rows.length === 0) {
      setBulkError("Çözümlenecek satır bulunamadı.");
    }
    setBulkRows(rows);
  };

  const submitBulk = async () => {
    const valid = bulkRows.filter((r) => !r._error);
    if (valid.length === 0) {
      setBulkError("Geçerli satır yok.");
      return;
    }
    if (isHq && !bulkCampusId) {
      setBulkError("Genel merkez için hedef kampüs seçin.");
      return;
    }
    setBulkBusy(true);
    setBulkError(null);
    try {
      const res = await api.bulkImportStaff(token, {
        rows: valid.map(({ _error, ...r }) => ({ ...r, phone: r.phone })),
        campus_id: isHq ? Number(bulkCampusId) : undefined,
      });
      setBulkResult(res);
      setNotice(`${res.created_count} personel içe aktarıldı (${res.skipped_count} atlandı).`);
      setBulkRows([]);
      setBulkText("");
      await load();
    } catch (e) {
      setBulkError(e.message);
    } finally {
      setBulkBusy(false);
    }
  };

  const pending = staff.filter((u) => u.status === "pending");
  const others = staff.filter((u) => u.status !== "pending");

  const validCount = bulkRows.filter((r) => !r._error).length;

  const WorkingRow = ({ u }) => (
    <tr className="manual-row">
      <td colSpan={isHq ? 6 : 5}>
        <div className="manual-form">
          <span className="manual-form__title">
            <strong>{u.full_name}</strong> için çalışma günleri — dönüşümlü çalışan personel için
            işaretleyin (devamsızlık raporu yalnızca seçili günleri bekler)
          </span>
          <div className="weekday-picker">
            {WEEKDAYS.map((d) => (
              <label key={d.n} className={workingSel.includes(d.n) ? "weekday weekday--on" : "weekday"}>
                <input
                  type="checkbox"
                  checked={workingSel.includes(d.n)}
                  onChange={() => toggleDay(d.n)}
                />
                {d.label}
              </label>
            ))}
          </div>
          <div className="actions">
            <button
              className="btn btn--primary btn--sm"
              disabled={workingBusy}
              onClick={() => submitWorking(u)}
            >
              {workingBusy ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button
              className="btn btn--ghost btn--sm"
              disabled={workingBusy}
              onClick={() => resetWorking(u)}
              title="Pzt–Cum varsayılanına döner"
            >
              Varsayılana Sıfırla
            </button>
            <button className="btn btn--ghost btn--sm" disabled={workingBusy} onClick={closeWorking}>
              Vazgeç
            </button>
          </div>
          {workingError && <p className="error">{workingError}</p>}
        </div>
      </td>
    </tr>
  );

  const ManualRow = ({ u }) => (
    <tr className="manual-row">
      <td colSpan={isHq ? 6 : 5}>
        <form className="manual-form" onSubmit={(e) => submitManual(e, u)}>
          <span className="manual-form__title">
            <strong>{u.full_name}</strong> için manuel kayıt — telefon arızalı / taranmayı unuttu
          </span>
          <label className="field field--inline">
            <span>Tür</span>
            <select
              value={manualForm.type}
              onChange={(e) => setManualForm({ ...manualForm, type: e.target.value })}
            >
              <option value="IN">Giriş</option>
              <option value="OUT">Çıkış</option>
            </select>
          </label>
          <label className="field field--inline">
            <span>Tarih</span>
            <input
              type="date"
              required
              value={manualForm.date}
              onChange={(e) => setManualForm({ ...manualForm, date: e.target.value })}
            />
          </label>
          <label className="field field--inline">
            <span>Saat</span>
            <input
              type="time"
              required
              value={manualForm.time}
              onChange={(e) => setManualForm({ ...manualForm, time: e.target.value })}
            />
          </label>
          <label className="field field--inline manual-form__note">
            <span>Not (opsiyonel)</span>
            <input
              type="text"
              maxLength={255}
              value={manualForm.note}
              onChange={(e) => setManualForm({ ...manualForm, note: e.target.value })}
              placeholder="Telefon arızalı"
            />
          </label>
          <div className="actions">
            <button className="btn btn--primary btn--sm" disabled={manualBusy} type="submit">
              {manualBusy ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button className="btn btn--ghost btn--sm" type="button" onClick={closeManual}>
              Vazgeç
            </button>
          </div>
          {manualError && <p className="error">{manualError}</p>}
        </form>
      </td>
    </tr>
  );

  const Row = ({ u }) => (
    <>
      <tr>
        <td>
          <strong>{u.full_name}</strong>
          <div className="muted small">
            {u.job_title} · {u.branch}
          </div>
          {u.status === "active" && (
            <div className="muted small">Çalışma: {workingDaysLabel(u.working_days)}</div>
          )}
        </td>
        <td className="muted small">{u.phone || "—"}</td>
        {isHq && <td className="muted small">{u.campus_name || "—"}</td>}
        <td>
          <span
            className={
              u.status === "active"
                ? "badge badge--in"
                : u.status === "pending"
                  ? "badge badge--auto"
                  : "badge badge--out"
            }
          >
            {STATUS_LABEL[u.status]}
          </span>
        </td>
        <td>
          {u.has_device ? (
            <span className="badge badge--in">Cihaz bağlı</span>
          ) : (
            <span className="muted small">cihaz yok</span>
          )}
        </td>
        <td className="actions">
          {u.status === "pending" && (
            <button
              className="btn btn--primary btn--sm"
              disabled={busyId === u.id}
              onClick={() => approve(u)}
            >
              Onayla
            </button>
          )}
          {u.status === "active" && (
            <>
              <button
                className="btn btn--ghost btn--sm"
                disabled={busyId === u.id}
                onClick={() => (manualForId === u.id ? closeManual() : openManual(u))}
                title="Telefon arızalı/taranmadı durumunda manuel giriş-çıkış ekler"
              >
                Manuel Kayıt
              </button>
              <button
                className="btn btn--ghost btn--sm"
                disabled={busyId === u.id}
                onClick={() => (workingForId === u.id ? closeWorking() : openWorking(u))}
                title="Dönüşümlü/özel çalışma günleri tanımlar"
              >
                Çalışma Günleri
              </button>
              <button
                className="btn btn--ghost btn--sm"
                disabled={busyId === u.id || !u.has_device}
                onClick={() => reset(u)}
                title="Telefon değişikliği için cihaz kaydını sıfırlar"
              >
                Cihazı Sıfırla
              </button>
              <button
                className="btn btn--warn btn--sm"
                disabled={busyId === u.id}
                onClick={() => disable(u)}
              >
                Devre Dışı
              </button>
            </>
          )}
          {u.status === "disabled" && (
            <button
              className="btn btn--primary btn--sm"
              disabled={busyId === u.id}
              onClick={() => approve(u)}
            >
              Yeniden Aktifleştir
            </button>
          )}
        </td>
      </tr>
      {manualForId === u.id && <ManualRow u={u} />}
      {workingForId === u.id && <WorkingRow u={u} />}
    </>
  );

  const cols = isHq ? 6 : 5;

  return (
    <div className="stack">
      {isHq && (
        <section className="card">
          <label className="field field--inline">
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
        </section>
      )}

      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <section className="card">
        <div className="filters">
          <h2 className="card__title" style={{ margin: 0 }}>
            Toplu Personel İçe Aktarma
          </h2>
          <div className="grow" />
          <button className="btn btn--ghost btn--sm" onClick={() => setShowBulk((v) => !v)}>
            {showBulk ? "Gizle" : "Aç"}
          </button>
        </div>
        {showBulk && (
          <div className="stack">
            <p className="muted small">
              Her satıra bir personel yapıştırın — sütunlar:{" "}
              <code>Ad Soyad, Telefon, Görev, Branş, Doğum(YYYY-AA-GG, ops.)</code>. Ayraç virgül,
              noktalı virgül veya sekme olabilir (Excel'den kopyalanabilir). Kayıtlar <strong>aktif</strong>{" "}
              olarak açılır; personel aynı telefon numarasıyla PWA'dan kaydolunca cihazına bağlanır.
            </p>
            {isHq && (
              <label className="field field--inline">
                <span>Hedef Kampüs</span>
                <select value={bulkCampusId} onChange={(e) => setBulkCampusId(e.target.value)}>
                  <option value="">Kampüs seçin…</option>
                  {campuses.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <textarea
              className="input"
              rows={6}
              placeholder={"Ali Veli, 0532 111 22 33, Öğretmen, Matematik, 1990-05-20\nAyşe Kaya; 0533 444 55 66; Öğretmen; Fizik"}
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              style={{ fontFamily: "monospace", width: "100%" }}
            />
            <div className="actions">
              <button className="btn btn--ghost btn--sm" onClick={previewBulk}>
                Önizle
              </button>
              <button
                className="btn btn--primary btn--sm"
                disabled={bulkBusy || validCount === 0}
                onClick={submitBulk}
              >
                {bulkBusy ? "Aktarılıyor…" : `İçe Aktar (${validCount} geçerli)`}
              </button>
            </div>
            {bulkError && <p className="error">{bulkError}</p>}

            {bulkRows.length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ad Soyad</th>
                      <th>Telefon</th>
                      <th>Görev</th>
                      <th>Branş</th>
                      <th>Doğum</th>
                      <th>Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkRows.map((r, i) => (
                      <tr key={i}>
                        <td>{r.full_name}</td>
                        <td className="muted small">{r.phone}</td>
                        <td className="muted small">{r.job_title}</td>
                        <td className="muted small">{r.branch}</td>
                        <td className="muted small">{r.birth_date || "—"}</td>
                        <td>
                          {r._error ? (
                            <span className="badge badge--out">{r._error}</span>
                          ) : (
                            <span className="badge badge--in">hazır</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {bulkResult && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ad Soyad</th>
                      <th>Telefon</th>
                      <th>Sonuç</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bulkResult.results.map((r, i) => (
                      <tr key={i}>
                        <td>{r.full_name}</td>
                        <td className="muted small">{r.phone}</td>
                        <td>
                          {r.created ? (
                            <span className="badge badge--in">eklendi</span>
                          ) : (
                            <span className="badge badge--auto">{r.reason || "atlandı"}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card__title">Onay Bekleyenler ({pending.length})</h2>
        {pending.length === 0 ? (
          <p className="muted">Bekleyen kayıt yok.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ad Soyad</th>
                  <th>Telefon</th>
                  {isHq && <th>Kampüs</th>}
                  <th>Durum</th>
                  <th>Cihaz</th>
                  <th>İşlem</th>
                </tr>
              </thead>
              <tbody>
                {pending.map((u) => (
                  <Row key={u.id} u={u} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="card__title">Personel ({others.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Ad Soyad</th>
                <th>Telefon</th>
                {isHq && <th>Kampüs</th>}
                <th>Durum</th>
                <th>Cihaz</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {others.length === 0 ? (
                <tr>
                  <td colSpan={cols} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                others.map((u) => <Row key={u.id} u={u} />)
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
