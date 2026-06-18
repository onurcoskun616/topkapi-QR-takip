import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api, downloadLogsXlsx, downloadReportsXlsx } from "../api";

function iso(d) {
  const off = d.getTimezoneOffset();
  return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
}

// "Öğretmen · Matematik" — the person's görev (job_title) and branş (branch),
// shown together in report tables so a manager sees who each row is at a glance.
function roleLabel(row) {
  const parts = [row.job_title, row.branch].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

function presetRange(kind) {
  const today = new Date();
  if (kind === "today") return { start: iso(today), end: iso(today) };
  if (kind === "week") {
    const day = today.getDay() || 7; // Monday = 1 ... Sunday = 7
    const monday = new Date(today);
    monday.setDate(today.getDate() - day + 1);
    const sunday = new Date(monday);
    sunday.setDate(monday.getDate() + 6);
    return { start: iso(monday), end: iso(sunday) };
  }
  if (kind === "month") {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    const last = new Date(today.getFullYear(), today.getMonth() + 1, 0);
    return { start: iso(first), end: iso(last) };
  }
  if (kind === "year") {
    return { start: `${today.getFullYear()}-01-01`, end: `${today.getFullYear()}-12-31` };
  }
  return { start: iso(today), end: iso(today) };
}

// Inline stacked-bar trend chart (no chart library): one bar per day, split
// into present / on-leave / unresolved segments scaled to the busiest day.
function TrendChart({ trend }) {
  if (!trend || trend.entries.length === 0) return <p className="muted">Veri yok.</p>;
  const max = Math.max(1, ...trend.entries.map((e) => e.expected));
  return (
    <div className="trend">
      <div className="trend__bars">
        {trend.entries.map((e) => {
          const h = (v) => `${(v / max) * 100}%`;
          const label = e.date.slice(5); // MM-DD
          return (
            <div className="trend__col" key={e.date} title={`${e.date}\nBeklenen: ${e.expected}\nGelen: ${e.present}\nİzinli: ${e.on_leave}\nDurum girilmedi: ${e.unresolved}`}>
              <div className="trend__stack">
                <div className="trend__seg trend__seg--unresolved" style={{ height: h(e.unresolved) }} />
                <div className="trend__seg trend__seg--leave" style={{ height: h(e.on_leave) }} />
                <div className="trend__seg trend__seg--present" style={{ height: h(e.present) }} />
              </div>
              <span className="trend__label">{label}</span>
            </div>
          );
        })}
      </div>
      <div className="trend__legend">
        <span><i className="dot dot--present" /> Gelen ({trend.total_present})</span>
        <span><i className="dot dot--leave" /> İzinli ({trend.total_on_leave})</span>
        <span><i className="dot dot--unresolved" /> Durum girilmedi ({trend.total_unresolved})</span>
      </div>
    </div>
  );
}

// Horizontal bars for absence reasons (share of total absent days).
function ReasonBars({ byReason }) {
  if (!byReason || byReason.length === 0) return <p className="muted">Veri yok.</p>;
  const max = Math.max(1, ...byReason.map((r) => r.day_count));
  return (
    <div className="hbars">
      {byReason.map((r) => (
        <div className="hbar" key={r.leave_type}>
          <span className="hbar__label">{r.leave_type}</span>
          <div className="hbar__track">
            <div className="hbar__fill" style={{ width: `${(r.day_count / max) * 100}%` }} />
          </div>
          <span className="hbar__value">{r.day_count} gün · {r.staff_count} kişi</span>
        </div>
      ))}
    </div>
  );
}

export default function Reports({ isHq }) {
  const { token } = useAuth();
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [staffList, setStaffList] = useState([]);
  const [userId, setUserId] = useState("");
  const [range, setRange] = useState(presetRange("month"));
  const [thresholdMinutes, setThresholdMinutes] = useState(0);
  const [excludeWeekends, setExcludeWeekends] = useState(true);

  const [late, setLate] = useState([]);
  const [early, setEarly] = useState([]);
  const [lateList, setLateList] = useState([]);
  const [earlyList, setEarlyList] = useState([]);
  const [summary, setSummary] = useState(null);
  const [detail, setDetail] = useState([]);
  const [trend, setTrend] = useState(null);
  const [showDetail, setShowDetail] = useState(false);

  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  // Staff picker for the "kişiye göre rapor" filter — active staff only,
  // re-loaded when the campus filter changes (hq) so the list stays in scope.
  useEffect(() => {
    api
      .listStaff(token, { status: "active", campusId: isHq ? campusId || undefined : undefined })
      .then(setStaffList)
      .catch(() => {});
  }, [token, isHq, campusId]);

  // A campus switch may drop the previously selected person out of scope.
  useEffect(() => {
    setUserId("");
  }, [campusId]);

  const filters = {
    startDate: range.start,
    endDate: range.end,
    campusId: isHq ? campusId || undefined : undefined,
    userId: userId || undefined,
    thresholdMinutes,
    excludeWeekends,
  };

  const load = async () => {
    if (!range.start || !range.end) return;
    setBusy(true);
    setError(null);
    try {
      const [lateRows, earlyRows, lateListRows, earlyListRows, summaryRes, detailRows, trendRes] =
        await Promise.all([
          api.lateRanking(token, filters),
          api.earlyLeaveRanking(token, filters),
          api.lateDetail(token, filters),
          api.earlyLeaveDetail(token, filters),
          api.absenceSummary(token, filters),
          api.absenceDetail(token, filters),
          api.dailyTrend(token, filters),
        ]);
      setLate(lateRows);
      setEarly(earlyRows);
      setLateList(lateListRows);
      setEarlyList(earlyListRows);
      setSummary(summaryRes);
      setDetail(detailRows);
      setTrend(trendRes);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, range.start, range.end, campusId, userId, thresholdMinutes, excludeWeekends]);

  const onLogsXlsx = async () => {
    try {
      await downloadLogsXlsx(token, {
        startDate: range.start,
        endDate: range.end,
        campusId: isHq ? campusId || undefined : undefined,
        userId: userId || undefined,
      });
    } catch (e) {
      setError(e.message);
    }
  };

  const onReportsXlsx = async () => {
    try {
      await downloadReportsXlsx(token, filters);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="stack">
      <section className="card">
        <div className="filters">
          <div className="actions">
            <button className="btn btn--ghost btn--sm" onClick={() => setRange(presetRange("today"))}>
              Bugün
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setRange(presetRange("week"))}>
              Bu Hafta
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setRange(presetRange("month"))}>
              Bu Ay
            </button>
            <button className="btn btn--ghost btn--sm" onClick={() => setRange(presetRange("year"))}>
              Bu Yıl
            </button>
          </div>
        </div>
        <div className="filters">
          <label className="field field--inline">
            <span>Başlangıç</span>
            <input
              type="date"
              value={range.start}
              onChange={(e) => setRange({ ...range, start: e.target.value })}
            />
          </label>
          <label className="field field--inline">
            <span>Bitiş</span>
            <input
              type="date"
              value={range.end}
              onChange={(e) => setRange({ ...range, end: e.target.value })}
            />
          </label>
          <label className="field field--inline">
            <span>Tolerans (dk)</span>
            <input
              type="number"
              min={0}
              max={240}
              style={{ width: 80 }}
              value={thresholdMinutes}
              onChange={(e) => setThresholdMinutes(Number(e.target.value))}
            />
          </label>
          <label className="field field--inline">
            <span>
              <input
                type="checkbox"
                checked={excludeWeekends}
                onChange={(e) => setExcludeWeekends(e.target.checked)}
              />{" "}
              Hafta sonlarını hariç tut
            </span>
          </label>
          {isHq && (
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
          )}
          <label className="field field--inline">
            <span>Personel</span>
            <select value={userId} onChange={(e) => setUserId(e.target.value)}>
              <option value="">Tüm personel</option>
              {staffList.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </label>
          <div className="grow" />
          <button className="btn btn--primary" onClick={onReportsXlsx}>
            Rapor Excel İndir
          </button>
          <button className="btn btn--ghost" onClick={onLogsXlsx}>
            Ham Kayıtlar (Excel)
          </button>
          <button className="btn btn--ghost" onClick={() => window.print()}>
            Yazdır / PDF
          </button>
        </div>
        {error && <p className="error">{error}</p>}
        {busy && <p className="muted">Yükleniyor…</p>}
      </section>

      <section className="kpis">
        <div className="kpi">
          <div className="kpi__value">{summary?.unresolved_count ?? "—"}</div>
          <div className="kpi__label">Durum girilmemiş gün (unresolved)</div>
        </div>
        <div className="kpi">
          <div className="kpi__value">{late.length}</div>
          <div className="kpi__label">Geç kalan personel sayısı</div>
        </div>
        <div className="kpi">
          <div className="kpi__value">{early.length}</div>
          <div className="kpi__label">Erken çıkan personel sayısı</div>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">Günlük Devam Eğilimi</h2>
        <TrendChart trend={trend} />
      </section>

      <section className="card">
        <h2 className="card__title">Devamsızlık Sebeplerine Göre Dağılım</h2>
        <ReasonBars byReason={summary?.by_reason} />
      </section>

      <section className="card">
        <h2 className="card__title">En Çok Geç Kalanlar</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                <th>Görev / Branş</th>
                {isHq && <th>Kampüs</th>}
                <th>Geç Kaldığı Gün</th>
                <th>Ortalama Gecikme (dk)</th>
              </tr>
            </thead>
            <tbody>
              {late.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 5 : 4} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                late.map((r) => (
                  <tr key={r.user_id}>
                    <td>{r.full_name}</td>
                    <td className="muted small">{roleLabel(r)}</td>
                    {isHq && <td className="muted small">{r.campus_name || "—"}</td>}
                    <td>{r.late_days}</td>
                    <td>{r.average_late_minutes}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">En Çok Erken Çıkanlar</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                <th>Görev / Branş</th>
                {isHq && <th>Kampüs</th>}
                <th>Erken Çıktığı Gün</th>
                <th>Ortalama Erken Çıkma (dk)</th>
              </tr>
            </thead>
            <tbody>
              {early.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 5 : 4} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                early.map((r) => (
                  <tr key={r.user_id}>
                    <td>{r.full_name}</td>
                    <td className="muted small">{roleLabel(r)}</td>
                    {isHq && <td className="muted small">{r.campus_name || "—"}</td>}
                    <td>{r.early_leave_days}</td>
                    <td>{r.average_early_minutes}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">Geç Giriş Listesi — Tarih / Saat ({lateList.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Saat</th>
                <th>Personel</th>
                <th>Görev / Branş</th>
                {isHq && <th>Kampüs</th>}
                <th>Mesai Başlangıcı</th>
                <th>Gecikme (dk)</th>
              </tr>
            </thead>
            <tbody>
              {lateList.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 7 : 6} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                lateList.map((e, i) => (
                  <tr key={`${e.user_id}-${e.date}-${i}`}>
                    <td className="muted small">{e.date}</td>
                    <td><strong>{e.arrival_time}</strong></td>
                    <td>{e.full_name}</td>
                    <td className="muted small">{roleLabel(e)}</td>
                    {isHq && <td className="muted small">{e.campus_name || "—"}</td>}
                    <td className="muted small">{e.shift_start}</td>
                    <td>
                      <span className="badge badge--out">{e.minutes_late} dk</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">Erken Çıkış Listesi — Tarih / Saat ({earlyList.length})</h2>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tarih</th>
                <th>Saat</th>
                <th>Personel</th>
                <th>Görev / Branş</th>
                {isHq && <th>Kampüs</th>}
                <th>Mesai Bitişi</th>
                <th>Erken (dk)</th>
              </tr>
            </thead>
            <tbody>
              {earlyList.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 7 : 6} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                earlyList.map((e, i) => (
                  <tr key={`${e.user_id}-${e.date}-${i}`}>
                    <td className="muted small">{e.date}</td>
                    <td><strong>{e.leave_time}</strong></td>
                    <td>{e.full_name}</td>
                    <td className="muted small">{roleLabel(e)}</td>
                    {isHq && <td className="muted small">{e.campus_name || "—"}</td>}
                    <td className="muted small">{e.shift_end}</td>
                    <td>
                      <span className="badge badge--out">{e.minutes_early} dk</span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2 className="card__title">Devamsızlık Özeti</h2>
        {summary && summary.by_reason.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>İzin / Durum Türü</th>
                  <th>Toplam Gün</th>
                  <th>Personel Sayısı</th>
                </tr>
              </thead>
              <tbody>
                {summary.by_reason.map((r) => (
                  <tr key={r.leave_type}>
                    <td>{r.leave_type}</td>
                    <td>{r.day_count}</td>
                    <td>{r.staff_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <h3 className="card__title">En Çok Devamsız Olanlar</h3>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Personel</th>
                <th>Görev / Branş</th>
                {isHq && <th>Kampüs</th>}
                <th>Toplam Devamsız Gün</th>
                <th>Durum Girilmemiş Gün</th>
              </tr>
            </thead>
            <tbody>
              {!summary || summary.totals_by_staff.length === 0 ? (
                <tr>
                  <td colSpan={isHq ? 5 : 4} className="muted">
                    Kayıt yok.
                  </td>
                </tr>
              ) : (
                summary.totals_by_staff.map((t) => (
                  <tr key={t.user_id}>
                    <td>{t.full_name}</td>
                    <td className="muted small">{roleLabel(t)}</td>
                    {isHq && <td className="muted small">{t.campus_name || "—"}</td>}
                    <td>{t.absent_days}</td>
                    <td>
                      {t.unresolved_days > 0 ? (
                        <span className="badge badge--out">{t.unresolved_days}</span>
                      ) : (
                        0
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <div className="filters">
          <h2 className="card__title" style={{ margin: 0 }}>
            Devamsızlık Detayı ({detail.length})
          </h2>
          <div className="grow" />
          <button className="btn btn--ghost btn--sm" onClick={() => setShowDetail(!showDetail)}>
            {showDetail ? "Gizle" : "Göster"}
          </button>
        </div>
        {showDetail && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Personel</th>
                  {isHq && <th>Kampüs</th>}
                  <th>Tarih</th>
                  <th>Durum</th>
                </tr>
              </thead>
              <tbody>
                {detail.length === 0 ? (
                  <tr>
                    <td colSpan={isHq ? 4 : 3} className="muted">
                      Kayıt yok.
                    </td>
                  </tr>
                ) : (
                  detail.map((d) => (
                    <tr key={`${d.user_id}-${d.date}`}>
                      <td>{d.full_name}</td>
                      {isHq && <td className="muted small">{d.campus_name || "—"}</td>}
                      <td className="muted small">{d.date}</td>
                      <td>
                        {d.status === "unresolved" ? (
                          <span className="badge badge--out">Durum girilmedi</span>
                        ) : (
                          <span className="badge badge--auto">{d.status}</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
