import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

const MONTHS = [
  "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
];
const WEEKDAY_LABELS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];

function iso(d) {
  // Local YYYY-MM-DD (avoids UTC offset rollover).
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

// Each day a leave covers, clamped to [start, end], as ISO strings.
function* daysBetween(startISO, endISO) {
  const d = new Date(`${startISO}T12:00:00`);
  const end = new Date(`${endISO}T12:00:00`);
  while (d <= end) {
    yield iso(d);
    d.setDate(d.getDate() + 1);
  }
}

export default function Calendar({ isHq }) {
  const { token } = useAuth();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-based
  const [campuses, setCampuses] = useState([]);
  const [campusId, setCampusId] = useState("");
  const [leaves, setLeaves] = useState([]);
  const [holidays, setHolidays] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);

  const monthStart = useMemo(() => iso(new Date(year, month, 1)), [year, month]);
  const monthEnd = useMemo(() => iso(new Date(year, month + 1, 0)), [year, month]);

  useEffect(() => {
    if (isHq) api.campuses().then(setCampuses).catch(() => {});
  }, [isHq]);

  const load = useCallback(async () => {
    setError(null);
    const campusFilter = isHq && campusId ? { campusId } : {};
    try {
      const [lv, hol] = await Promise.all([
        api.listLeaves(token, {
          ...campusFilter,
          status: "active",
          startDate: monthStart,
          endDate: monthEnd,
        }),
        api.listHolidays(token, { ...campusFilter, startDate: monthStart, endDate: monthEnd }),
      ]);
      setLeaves(lv);
      setHolidays(hol);
    } catch (e) {
      setError(e.message);
    }
  }, [token, isHq, campusId, monthStart, monthEnd]);

  useEffect(() => {
    load();
  }, [load]);

  // Build per-day index: { "YYYY-MM-DD": { leaves: [...], holidays: [...] } }
  const byDay = useMemo(() => {
    const map = {};
    const touch = (d) => (map[d] = map[d] || { leaves: [], holidays: [] });
    for (const lv of leaves) {
      for (const d of daysBetween(lv.start_date, lv.end_date)) {
        if (d >= monthStart && d <= monthEnd) touch(d).leaves.push(lv);
      }
    }
    for (const h of holidays) touch(h.date).holidays.push(h);
    return map;
  }, [leaves, holidays, monthStart, monthEnd]);

  // Calendar grid: weeks starting Monday, covering the whole month.
  const cells = useMemo(() => {
    const first = new Date(year, month, 1);
    const startOffset = (first.getDay() + 6) % 7; // Mon=0 … Sun=6
    const gridStart = new Date(year, month, 1 - startOffset);
    const out = [];
    const cur = new Date(gridStart);
    // 6 weeks max; stop after we've passed the month and completed the week.
    for (let i = 0; i < 42; i++) {
      out.push(new Date(cur));
      cur.setDate(cur.getDate() + 1);
    }
    // Trim trailing full weeks that are entirely in the next month.
    while (out.length > 35 && out[out.length - 7].getMonth() !== month) {
      out.splice(out.length - 7, 7);
    }
    return out;
  }, [year, month]);

  const prev = () => {
    setSelected(null);
    if (month === 0) {
      setYear((y) => y - 1);
      setMonth(11);
    } else setMonth((m) => m - 1);
  };
  const next = () => {
    setSelected(null);
    if (month === 11) {
      setYear((y) => y + 1);
      setMonth(0);
    } else setMonth((m) => m + 1);
  };

  const todayISO = iso(today);
  const sel = selected ? byDay[selected] : null;

  return (
    <div className="stack">
      <section className="card">
        <div className="filters">
          <button className="btn btn--ghost btn--sm" onClick={prev}>
            ← Önceki
          </button>
          <h2 className="card__title" style={{ margin: 0 }}>
            {MONTHS[month]} {year}
          </h2>
          <button className="btn btn--ghost btn--sm" onClick={next}>
            Sonraki →
          </button>
          <div className="grow" />
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
        </div>
        {error && <p className="error">{error}</p>}

        <div className="cal">
          <div className="cal__head">
            {WEEKDAY_LABELS.map((w) => (
              <div className="cal__hcell" key={w}>
                {w}
              </div>
            ))}
          </div>
          <div className="cal__grid">
            {cells.map((d) => {
              const dISO = iso(d);
              const info = byDay[dISO];
              const inMonth = d.getMonth() === month;
              const holiday = info && info.holidays.length > 0;
              const leaveCount = info ? info.leaves.length : 0;
              const cls = [
                "cal__cell",
                inMonth ? "" : "cal__cell--muted",
                holiday ? "cal__cell--holiday" : "",
                dISO === todayISO ? "cal__cell--today" : "",
                dISO === selected ? "cal__cell--sel" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <button className={cls} key={dISO} onClick={() => setSelected(dISO)}>
                  <span className="cal__day">{d.getDate()}</span>
                  {holiday && (
                    <span className="cal__tag cal__tag--holiday" title={info.holidays.map((h) => h.name).join(", ")}>
                      {info.holidays[0].name}
                    </span>
                  )}
                  {leaveCount > 0 && (
                    <span className="cal__tag cal__tag--leave">{leaveCount} izinli</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {selected && (
        <section className="card">
          <h2 className="card__title">{selected} — Detay</h2>
          {sel && sel.holidays.length > 0 && (
            <p>
              {sel.holidays.map((h) => (
                <span key={h.id} className="badge badge--in" style={{ marginRight: 6 }}>
                  Tatil: {h.name} {h.campus_id == null ? "(tüm kampüsler)" : `(${h.campus_name || "kampüs"})`}
                </span>
              ))}
            </p>
          )}
          {!sel || sel.leaves.length === 0 ? (
            <p className="muted">Bu gün izinli personel yok.</p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Personel</th>
                    {isHq && <th>Kampüs</th>}
                    <th>Tür</th>
                    <th>Aralık</th>
                  </tr>
                </thead>
                <tbody>
                  {sel.leaves.map((lv) => (
                    <tr key={lv.id}>
                      <td>{lv.user_full_name}</td>
                      {isHq && <td className="muted small">{lv.campus_name || "—"}</td>}
                      <td>{lv.leave_type}</td>
                      <td className="muted small">
                        {lv.start_date} → {lv.end_date}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
