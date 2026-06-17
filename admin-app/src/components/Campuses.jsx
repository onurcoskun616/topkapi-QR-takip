import { useEffect, useState } from "react";
import { useAuth } from "../auth";
import { api } from "../api";

// Build this campus' kiosk (tablet) URL from the panel's own address, e.g.
// panel.okul.com -> kiosk.okul.com/?campus=3. The deployment uses matching
// panel./kiosk. subdomains, so swapping the first label is reliable here.
function kioskUrl(campusId) {
  const { protocol, hostname, port } = window.location;
  const kioskHost = hostname.includes(".")
    ? hostname.replace(/^[^.]+/, "kiosk")
    : hostname; // dev (localhost) — no subdomain to swap
  const portPart = port ? `:${port}` : "";
  return `${protocol}//${kioskHost}${portPart}/?campus=${campusId}`;
}

export default function Campuses() {
  const { token } = useAuth();
  const [campuses, setCampuses] = useState([]);
  const [edits, setEdits] = useState({});
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const load = () => api.campuses().then(setCampuses).catch((e) => setError(e.message));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const copyKioskUrl = async (c) => {
    const url = kioskUrl(c.id);
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      /* clipboard blocked (e.g. http) — the address is still shown to copy by hand */
    }
    setCopiedId(c.id);
    setTimeout(() => setCopiedId((id) => (id === c.id ? null : id)), 2000);
  };

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
        <p className="muted small">
          <strong>Tablet (kiosk) kurulumu:</strong> Her kampüsün tabletinde aşağıdaki <em>Kiosk
          Adresi</em>ni açın. Adresteki <code>?campus=ID</code> sayesinde o tablette başarılı her
          taramada yeşil onay ve doğum günü kutlaması görünür. Adres olmadan QR yine döner ama
          tablette onay çıkmaz.
        </p>

        {error && <p className="error">{error}</p>}
        {notice && <p className="notice">{notice}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Kampüs</th>
                <th>Mesai Başlangıç</th>
                <th>Mesai Bitiş</th>
                <th>Kiosk Adresi</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {campuses.map((c) => {
                const f = fieldFor(c);
                return (
                  <tr key={c.id}>
                    <td><strong>{c.id}</strong></td>
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
                      <div className="kiosk-url">
                        <code className="kiosk-url__text">{kioskUrl(c.id)}</code>
                        <button
                          className="btn btn--ghost btn--sm"
                          onClick={() => copyKioskUrl(c)}
                        >
                          {copiedId === c.id ? "Kopyalandı ✓" : "Kopyala"}
                        </button>
                      </div>
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
