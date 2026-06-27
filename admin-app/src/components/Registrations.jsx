import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const GRADES = [9, 10, 11, 12];

const STATUS_LABEL = {
  prospective: "Aday",
  registered: "Kayıt yapıldı",
  cancelled: "İptal",
};

const STATUS_BADGE = {
  prospective: "badge badge--auto",
  registered: "badge badge--in",
  cancelled: "badge badge--out",
};

// Suggested arrival channels (Geliş Kanalı). "İç Kayıt" is the one internal
// channel; everything else is treated as external by the backend.
const CHANNELS = ["İç Kayıt", "Tavsiye", "Reklam", "Web Sitesi", "Sosyal Medya", "Diğer"];

const EMPTY_REG = {
  department_id: "",
  full_name: "",
  grade: "9",
  section: "",
  arrival_channel: "",
  status: "prospective",
  approved: false,
};

const EMPTY_DEPT = { campus_id: "", name: "", license_quota: "0" };

export default function Registrations({ isHq }) {
  const { token } = useAuth();
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState(""); // hq filter (blank = all)

  const [departments, setDepartments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [registrations, setRegistrations] = useState([]);

  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  // --- search form (arama formu) -----------------------------------------
  const [filters, setFilters] = useState({
    department_id: "",
    grade: "",
    section: "",
    status: "",
    approved: "",
    channel: "",
    q: "",
  });

  // --- new registration form ---------------------------------------------
  const [regForm, setRegForm] = useState(EMPTY_REG);
  const [regBusy, setRegBusy] = useState(false);
  const [rowBusyId, setRowBusyId] = useState(null);

  // --- department editor (hq) --------------------------------------------
  const [deptForm, setDeptForm] = useState(EMPTY_DEPT);
  const [deptBusy, setDeptBusy] = useState(false);
  const [deptEdits, setDeptEdits] = useState({}); // id -> { license_quota, targets:{grade:{i,e}} }
  const [deptBusyId, setDeptBusyId] = useState(null);

  const scopeCampus = isHq ? campusId || undefined : undefined;

  const loadDepartments = useCallback(async () => {
    try {
      setDepartments(await api.listDepartments(token, { campusId: scopeCampus }));
    } catch (e) {
      setError(e.message);
    }
  }, [token, scopeCampus]);

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await api.registrationSummary(token, { campusId: scopeCampus }));
    } catch (e) {
      setError(e.message);
    }
  }, [token, scopeCampus]);

  const loadRegistrations = useCallback(async () => {
    setError(null);
    try {
      setRegistrations(
        await api.listRegistrations(token, {
          campusId: scopeCampus,
          departmentId: filters.department_id || undefined,
          grade: filters.grade || undefined,
          section: filters.section || undefined,
          status: filters.status || undefined,
          approved: filters.approved === "" ? undefined : filters.approved,
          channel: filters.channel || undefined,
          q: filters.q || undefined,
        })
      );
    } catch (e) {
      setError(e.message);
    }
  }, [token, scopeCampus, filters]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  useEffect(() => {
    loadDepartments();
    loadSummary();
  }, [loadDepartments, loadSummary]);

  useEffect(() => {
    loadRegistrations();
  }, [loadRegistrations]);

  const reloadAll = async () => {
    await Promise.all([loadDepartments(), loadSummary(), loadRegistrations()]);
  };

  const campusName = (id) => campuses.find((c) => c.id === id)?.name || "";

  // ---- registrations -----------------------------------------------------
  const submitReg = async (e) => {
    e.preventDefault();
    setRegBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createRegistration(token, {
        department_id: Number(regForm.department_id),
        full_name: regForm.full_name,
        grade: Number(regForm.grade),
        section: regForm.section || null,
        arrival_channel: regForm.arrival_channel,
        status: regForm.status,
        approved: regForm.approved,
      });
      setNotice("Öğrenci kaydı eklendi.");
      setRegForm({ ...EMPTY_REG, department_id: regForm.department_id });
      await reloadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setRegBusy(false);
    }
  };

  const rowAction = async (fn) => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      await reloadAll();
    } catch (err) {
      setError(err.message);
    }
  };

  const approve = (r) =>
    rowAction(async () => {
      setRowBusyId(r.id);
      try {
        await api.approveRegistration(token, r.id);
        setNotice(`${r.full_name} kaydı onaylandı.`);
      } finally {
        setRowBusyId(null);
      }
    });

  const unapprove = (r) =>
    rowAction(async () => {
      setRowBusyId(r.id);
      try {
        await api.unapproveRegistration(token, r.id);
      } finally {
        setRowBusyId(null);
      }
    });

  const setRegistered = (r) =>
    rowAction(async () => {
      setRowBusyId(r.id);
      try {
        await api.updateRegistration(token, r.id, { status: "registered" });
      } finally {
        setRowBusyId(null);
      }
    });

  const removeReg = (r) =>
    rowAction(async () => {
      if (!window.confirm(`${r.full_name} kaydı silinsin mi?`)) return;
      setRowBusyId(r.id);
      try {
        await api.deleteRegistration(token, r.id);
      } finally {
        setRowBusyId(null);
      }
    });

  // ---- departments (hq) --------------------------------------------------
  const submitDept = async (e) => {
    e.preventDefault();
    setDeptBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createDepartment(token, {
        campus_id: Number(deptForm.campus_id),
        name: deptForm.name,
        license_quota: Number(deptForm.license_quota) || 0,
      });
      setNotice("Bölüm eklendi.");
      setDeptForm(EMPTY_DEPT);
      await reloadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeptBusy(false);
    }
  };

  const deptEditFor = (d) => {
    const existing = deptEdits[d.id];
    if (existing) return existing;
    const targets = {};
    for (const g of GRADES) {
      const t = d.targets.find((x) => x.grade === g);
      targets[g] = {
        internal_target: t ? t.internal_target : 0,
        external_target: t ? t.external_target : 0,
      };
    }
    return { license_quota: d.license_quota, targets };
  };

  const setDeptEdit = (d, patch) =>
    setDeptEdits({ ...deptEdits, [d.id]: { ...deptEditFor(d), ...patch } });

  const setTargetEdit = (d, grade, key, value) => {
    const cur = deptEditFor(d);
    setDeptEdits({
      ...deptEdits,
      [d.id]: {
        ...cur,
        targets: { ...cur.targets, [grade]: { ...cur.targets[grade], [key]: value } },
      },
    });
  };

  const saveDept = async (d) => {
    const edit = deptEditFor(d);
    setDeptBusyId(d.id);
    setError(null);
    setNotice(null);
    try {
      await api.updateDepartment(token, d.id, {
        license_quota: Number(edit.license_quota) || 0,
      });
      await api.setDepartmentTargets(
        token,
        d.id,
        GRADES.map((g) => ({
          grade: g,
          internal_target: Number(edit.targets[g].internal_target) || 0,
          external_target: Number(edit.targets[g].external_target) || 0,
        }))
      );
      setNotice(`${d.name} güncellendi.`);
      setDeptEdits((prev) => {
        const next = { ...prev };
        delete next[d.id];
        return next;
      });
      await reloadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeptBusyId(null);
    }
  };

  const removeDept = async (d) => {
    if (!window.confirm(`${d.name} bölümü silinsin mi?`)) return;
    setDeptBusyId(d.id);
    setError(null);
    try {
      await api.deleteDepartment(token, d.id);
      setNotice(`${d.name} silindi.`);
      await reloadAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeptBusyId(null);
    }
  };

  return (
    <div className="stack">
      {isHq && (
        <section className="card">
          <h2 className="card__title">Kampüs Filtresi</h2>
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
        </section>
      )}

      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      {/* ---- Quota + target dashboard --------------------------------- */}
      <section className="card">
        <h2 className="card__title">Kontenjan ve Kayıt Hedefleri</h2>
        <p className="muted small">
          Her bölümün MEB ruhsat kontenjanı, o bölüme alınabilecek toplam kaydın üst sınırıdır.
          Sayımlara yalnızca <strong>kayıt yapıldı</strong> ve <strong>onaylanmış</strong> öğrenciler
          dahildir. Geliş kanalı <strong>İç Kayıt</strong> olanlar iç, diğerleri dış kayıt sayılır.
        </p>
        {summary && summary.departments.length === 0 && (
          <p className="muted">Bu kapsamda tanımlı bölüm yok.</p>
        )}
        {summary &&
          summary.departments.map((d) => (
            <div key={d.department_id} className="table-wrap" style={{ marginBottom: 18 }}>
              <h3 style={{ margin: "8px 0" }}>
                {d.department_name}
                {isHq && <span className="muted small"> — {d.campus_name}</span>}{" "}
                <span className={d.over_quota ? "badge badge--out" : "badge badge--in"}>
                  Kontenjan: {d.confirmed_count}/{d.license_quota} (kalan {d.remaining_quota})
                </span>
              </h3>
              <table className="table">
                <thead>
                  <tr>
                    <th>Sınıf</th>
                    <th>İç Kayıt (gerçekleşen / hedef)</th>
                    <th>Dış Kayıt (gerçekleşen / hedef)</th>
                  </tr>
                </thead>
                <tbody>
                  {d.grades.map((g) => (
                    <tr key={g.grade}>
                      <td>
                        <strong>{g.grade}. sınıf</strong>
                      </td>
                      <td>
                        {g.internal_count} / {g.internal_target}
                      </td>
                      <td>
                        {g.external_count} / {g.external_target}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </section>

      {/* ---- Department management (hq only) -------------------------- */}
      {isHq && (
        <section className="card">
          <h2 className="card__title">Bölüm ve Kontenjan Yönetimi (Genel Merkez)</h2>
          <p className="muted small">
            Bölüm ruhsat kontenjanını ve her sınıfın iç/dış kayıt hedeflerini buradan belirleyin.
          </p>

          <form className="row" onSubmit={submitDept} style={{ gap: 8, flexWrap: "wrap" }}>
            <label className="field">
              <span>Kampüs</span>
              <select
                required
                value={deptForm.campus_id}
                onChange={(e) => setDeptForm({ ...deptForm, campus_id: e.target.value })}
              >
                <option value="">Seçin…</option>
                {campuses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Bölüm adı</span>
              <input
                required
                value={deptForm.name}
                placeholder="Anadolu Lisesi"
                onChange={(e) => setDeptForm({ ...deptForm, name: e.target.value })}
              />
            </label>
            <label className="field">
              <span>Ruhsat kontenjanı</span>
              <input
                type="number"
                min="0"
                value={deptForm.license_quota}
                onChange={(e) => setDeptForm({ ...deptForm, license_quota: e.target.value })}
              />
            </label>
            <button className="btn btn--primary" disabled={deptBusy} type="submit">
              {deptBusy ? "Ekleniyor…" : "Bölüm Ekle"}
            </button>
          </form>

          {departments.map((d) => {
            const edit = deptEditFor(d);
            return (
              <div key={d.id} className="table-wrap" style={{ marginTop: 16 }}>
                <h3 style={{ margin: "8px 0" }}>
                  {d.name} <span className="muted small">— {campusName(d.campus_id) || d.campus_name}</span>
                </h3>
                <div className="row" style={{ gap: 8, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <label className="field">
                    <span>Ruhsat kontenjanı</span>
                    <input
                      type="number"
                      min="0"
                      style={{ width: 120 }}
                      value={edit.license_quota}
                      onChange={(e) => setDeptEdit(d, { license_quota: e.target.value })}
                    />
                  </label>
                  <span className="muted small">Dolu: {d.confirmed_count}</span>
                </div>
                <table className="table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr>
                      <th>Sınıf</th>
                      <th>İç Kayıt Hedefi</th>
                      <th>Dış Kayıt Hedefi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {GRADES.map((g) => (
                      <tr key={g}>
                        <td>
                          <strong>{g}. sınıf</strong>
                        </td>
                        <td>
                          <input
                            type="number"
                            min="0"
                            style={{ width: 90 }}
                            value={edit.targets[g].internal_target}
                            onChange={(e) => setTargetEdit(d, g, "internal_target", e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="number"
                            min="0"
                            style={{ width: 90 }}
                            value={edit.targets[g].external_target}
                            onChange={(e) => setTargetEdit(d, g, "external_target", e.target.value)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="actions" style={{ marginTop: 8 }}>
                  <button
                    className="btn btn--primary btn--sm"
                    disabled={deptBusyId === d.id}
                    onClick={() => saveDept(d)}
                  >
                    {deptBusyId === d.id ? "Kaydediliyor…" : "Kaydet"}
                  </button>
                  <button
                    className="btn btn--warn btn--sm"
                    disabled={deptBusyId === d.id}
                    onClick={() => removeDept(d)}
                  >
                    Sil
                  </button>
                </div>
              </div>
            );
          })}
        </section>
      )}

      {/* ---- New registration ----------------------------------------- */}
      <section className="card">
        <h2 className="card__title">Yeni Öğrenci Kaydı</h2>
        <form className="row" onSubmit={submitReg} style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="field">
            <span>Bölüm</span>
            <select
              required
              value={regForm.department_id}
              onChange={(e) => setRegForm({ ...regForm, department_id: e.target.value })}
            >
              <option value="">Seçin…</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                  {isHq ? ` — ${campusName(d.campus_id) || d.campus_name}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Ad Soyad</span>
            <input
              required
              value={regForm.full_name}
              onChange={(e) => setRegForm({ ...regForm, full_name: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Sınıf</span>
            <select
              value={regForm.grade}
              onChange={(e) => setRegForm({ ...regForm, grade: e.target.value })}
            >
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Şube</span>
            <input
              style={{ width: 70 }}
              value={regForm.section}
              placeholder="A"
              onChange={(e) => setRegForm({ ...regForm, section: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Geliş Kanalı</span>
            <input
              required
              list="arrival-channels"
              value={regForm.arrival_channel}
              onChange={(e) => setRegForm({ ...regForm, arrival_channel: e.target.value })}
            />
            <datalist id="arrival-channels">
              {CHANNELS.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Kayıt Durumu</span>
            <select
              value={regForm.status}
              onChange={(e) => setRegForm({ ...regForm, status: e.target.value })}
            >
              <option value="prospective">Aday</option>
              <option value="registered">Kayıt yapıldı</option>
            </select>
          </label>
          <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <input
              type="checkbox"
              checked={regForm.approved}
              onChange={(e) => setRegForm({ ...regForm, approved: e.target.checked })}
            />
            <span>Onaylı</span>
          </label>
          <button className="btn btn--primary" disabled={regBusy} type="submit">
            {regBusy ? "Ekleniyor…" : "Kaydet"}
          </button>
        </form>
      </section>

      {/* ---- Search + list -------------------------------------------- */}
      <section className="card">
        <h2 className="card__title">Öğrenci Kayıtları</h2>
        <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="field">
            <span>Ara (ad)</span>
            <input
              value={filters.q}
              onChange={(e) => setFilters({ ...filters, q: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Bölüm</span>
            <select
              value={filters.department_id}
              onChange={(e) => setFilters({ ...filters, department_id: e.target.value })}
            >
              <option value="">Tümü</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Sınıf</span>
            <select
              value={filters.grade}
              onChange={(e) => setFilters({ ...filters, grade: e.target.value })}
            >
              <option value="">Tümü</option>
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  {g}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Şube</span>
            <input
              style={{ width: 70 }}
              value={filters.section}
              onChange={(e) => setFilters({ ...filters, section: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Durum</span>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            >
              <option value="">Tümü</option>
              <option value="prospective">Aday</option>
              <option value="registered">Kayıt yapıldı</option>
              <option value="cancelled">İptal</option>
            </select>
          </label>
          <label className="field">
            <span>Onay</span>
            <select
              value={filters.approved}
              onChange={(e) => setFilters({ ...filters, approved: e.target.value })}
            >
              <option value="">Tümü</option>
              <option value="true">Onaylı</option>
              <option value="false">Onaysız</option>
            </select>
          </label>
        </div>

        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Ad Soyad</th>
                {isHq && <th>Kampüs</th>}
                <th>Bölüm</th>
                <th>Sınıf/Şube</th>
                <th>Geliş Kanalı</th>
                <th>Durum</th>
                <th>Onay</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {registrations.length === 0 && (
                <tr>
                  <td colSpan={isHq ? 8 : 7} className="muted">
                    Kayıt bulunamadı.
                  </td>
                </tr>
              )}
              {registrations.map((r) => (
                <tr key={r.id}>
                  <td>
                    {r.full_name}
                    {r.counts_toward_target && (
                      <span className="muted small"> ✓ hedefe sayılıyor</span>
                    )}
                  </td>
                  {isHq && <td>{r.campus_name}</td>}
                  <td>{r.department_name}</td>
                  <td>
                    {r.grade}
                    {r.section ? `/${r.section}` : ""}
                  </td>
                  <td>
                    {r.arrival_channel}{" "}
                    <span className={r.is_internal ? "badge badge--in" : "badge badge--auto"}>
                      {r.is_internal ? "İç" : "Dış"}
                    </span>
                  </td>
                  <td>
                    <span className={STATUS_BADGE[r.status]}>{STATUS_LABEL[r.status]}</span>
                  </td>
                  <td>
                    {r.approved ? (
                      <span className="badge badge--in">Onaylı</span>
                    ) : (
                      <span className="badge badge--out">Onaysız</span>
                    )}
                  </td>
                  <td className="actions">
                    {r.status !== "registered" && (
                      <button
                        className="btn btn--ghost btn--sm"
                        disabled={rowBusyId === r.id}
                        onClick={() => setRegistered(r)}
                      >
                        Kayıt Yapıldı
                      </button>
                    )}
                    {r.approved ? (
                      <button
                        className="btn btn--ghost btn--sm"
                        disabled={rowBusyId === r.id}
                        onClick={() => unapprove(r)}
                      >
                        Onayı Kaldır
                      </button>
                    ) : (
                      <button
                        className="btn btn--primary btn--sm"
                        disabled={rowBusyId === r.id}
                        onClick={() => approve(r)}
                      >
                        Onayla
                      </button>
                    )}
                    <button
                      className="btn btn--warn btn--sm"
                      disabled={rowBusyId === r.id}
                      onClick={() => removeReg(r)}
                    >
                      Sil
                    </button>
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
