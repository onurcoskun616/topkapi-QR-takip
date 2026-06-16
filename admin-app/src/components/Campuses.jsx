import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

export default function Campuses() {
  const { token } = useAuth();
  const [campuses, setCampuses] = useState([]);
  const [edits, setEdits] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = () => api.campuses().then(setCampuses).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fieldFor = (c) =>
    edits[c.id] || {
      shift_start: c.shift_start || "",
      shift_end: c.shift_end || "",
    };

  const setField = (c, key, value) =>
    setEdits({ ...edits, [c.id]: { ...fieldFor(c), [key]: value } });

  const save = async (c) => {
    const f = fieldFor(c);
    if (!f.shift_start || !f.shift_end) {
      setError("Mesai başlangıç ve bitiş saatleri gerekli.");
      return;
    }
    setBusyId(c.id);
    setError(null);
    setNotice(null);
    try {
      await api.updateCampusShift(token, c.id, {
        shift_start: `${f.shift_start}:00`,
        shift_end: `${f.shift_end}:00`,
      });
      setNotice(`${c.name} mesai saatleri güncellendi.`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="stack">
      <section className="card">
        <h2 className="card__title">Kampüs Mesai Saatleri</h2>
        <p className="muted small">
          Mesai saatlerini yalnızca genel merkez belirleyebilir. Bu saatler, geç kalma ve erken
          çıkış raporlarının dayanağıdır.
        </p>

        {error && <p className="error">{error}</p>}
        {notice && <p className="notice">{notice}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Kampüs</th>
                <th>Mesai Başlangıç</th>
                <th>Mesai Bitiş</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {campuses.map((c) => {
                const f = fieldFor(c);
                return (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>
                      <input
                        type="time"
                        value={f.shift_start}
                        onChange={(e) => setField(c, "shift_start", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="time"
                        value={f.shift_end}
                        onChange={(e) => setField(c, "shift_end", e.target.value)}
                      />
                    </td>
                    <td>
                      <button
                        className="btn btn--primary btn--sm"
                        disabled={busyId === c.id}
                        onClick={() => save(c)}
                      >
                        {busyId === c.id ? "Kaydediliyor…" : "Kaydet"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
