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

  // Separate edit/busy state for the geofence (location) card.
  const [geoEdits, setGeoEdits] = useState({});
  const [geoBusyId, setGeoBusyId] = useState(null);
  const [geoLocatingId, setGeoLocatingId] = useState(null);
  const [geoError, setGeoError] = useState(null);
  const [geoNotice, setGeoNotice] = useState(null);

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
      // A <input type="time"> gives "HH:MM"; the backend accepts that directly.
      // Append ":00" only when seconds are missing so we never send "HH:MM:00:00"
      // (which would be rejected as an invalid time).
      const withSeconds = (t) => (t && t.length === 5 ? `${t}:00` : t);
      await api.updateCampusShift(token, c.id, {
        shift_start: withSeconds(f.shift_start),
        shift_end: withSeconds(f.shift_end),
      });
      setNotice(`${c.name} mesai saatleri güncellendi.`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  };

  // ---- Geofence (location verification) ----------------------------------
  const geoFor = (c) =>
    geoEdits[c.id] || {
      latitude: c.latitude ?? "",
      longitude: c.longitude ?? "",
      radius: c.geofence_radius_m ?? 500,
    };

  const setGeo = (c, key, value) =>
    setGeoEdits({ ...geoEdits, [c.id]: { ...geoFor(c), [key]: value } });

  const useCurrentLocation = (c) => {
    if (!navigator.geolocation) {
      setGeoError("Bu tarayıcı konum almayı desteklemiyor.");
      return;
    }
    setGeoLocatingId(c.id);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeo(c, "latitude", pos.coords.latitude.toFixed(6));
        setGeoEdits((prev) => ({
          ...prev,
          [c.id]: {
            ...(prev[c.id] || geoFor(c)),
            latitude: pos.coords.latitude.toFixed(6),
            longitude: pos.coords.longitude.toFixed(6),
          },
        }));
        setGeoLocatingId(null);
      },
      () => {
        setGeoError("Konum alınamadı. Tarayıcı konum iznini kontrol edin.");
        setGeoLocatingId(null);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const saveGeo = async (c) => {
    const g = geoFor(c);
    const hasLat = g.latitude !== "" && g.latitude !== null;
    const hasLng = g.longitude !== "" && g.longitude !== null;
    if (hasLat !== hasLng) {
      setGeoError("Enlem ve boylamı birlikte girin.");
      return;
    }
    setGeoBusyId(c.id);
    setGeoError(null);
    setGeoNotice(null);
    try {
      await api.updateCampusLocation(token, c.id, {
        latitude: hasLat ? Number(g.latitude) : null,
        longitude: hasLng ? Number(g.longitude) : null,
        geofence_radius_m: Number(g.radius) || 500,
      });
      setGeoNotice(
        hasLat
          ? `${c.name} konum doğrulaması açıldı (${Number(g.radius) || 500} m).`
          : `${c.name} konum doğrulaması kapatıldı.`
      );
      setGeoEdits((prev) => {
        const next = { ...prev };
        delete next[c.id];
        return next;
      });
      await load();
    } catch (e) {
      setGeoError(e.message);
    } finally {
      setGeoBusyId(null);
    }
  };

  const toggleGeoEnabled = async (c, enabled) => {
    setGeoBusyId(c.id);
    setGeoError(null);
    setGeoNotice(null);
    try {
      await api.setCampusGeofenceEnabled(token, c.id, enabled);
      setGeoNotice(
        enabled
          ? `${c.name} konum doğrulaması açıldı.`
          : `${c.name} konum doğrulaması duraklatıldı (konum korundu).`
      );
      await load();
    } catch (e) {
      setGeoError(e.message);
    } finally {
      setGeoBusyId(null);
    }
  };

  const clearGeo = async (c) => {
    if (!window.confirm(`${c.name} için konum doğrulaması kapatılsın mı?`)) return;
    setGeoBusyId(c.id);
    setGeoError(null);
    try {
      await api.updateCampusLocation(token, c.id, {
        latitude: null,
        longitude: null,
        geofence_radius_m: c.geofence_radius_m || 500,
      });
      setGeoNotice(`${c.name} konum doğrulaması kapatıldı.`);
      await load();
    } catch (e) {
      setGeoError(e.message);
    } finally {
      setGeoBusyId(null);
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

      <section className="card">
        <h2 className="card__title">Konum Doğrulaması (Geofence)</h2>
        <p className="muted small">
          Bir kampüsün konumunu (enlem/boylam) ve izin verilen yarıçapı girin.
          Personel giriş/çıkış için QR okuttuğunda telefonun konumu bu alanın
          dışındaysa işlem yapılmaz ve denemesi <strong>Konum Uyarıları</strong>{" "}
          sekmesine düşer. Konum boş bırakılan kampüste doğrulama kapalıdır
          (eskisi gibi çalışır). Önerilen yarıçap: 500 m.
        </p>
        <p className="muted small">
          İpucu: Kampüsteyseniz <em>“Bu cihazın konumunu kullan”</em> ile
          koordinatları otomatik doldurabilir; ya da Google Haritalar’da okul
          noktasına sağ tıklayıp çıkan koordinatları yapıştırabilirsiniz.
        </p>

        {geoError && <p className="error">{geoError}</p>}
        {geoNotice && <p className="notice">{geoNotice}</p>}

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Kampüs</th>
                <th>Enlem</th>
                <th>Boylam</th>
                <th>Yarıçap (m)</th>
                <th>Durum</th>
                <th>İşlem</th>
              </tr>
            </thead>
            <tbody>
              {campuses.map((c) => {
                const g = geoFor(c);
                const hasCoords = c.latitude != null && c.longitude != null;
                const enabled = c.geofence_enabled !== false;
                const active = hasCoords && enabled;
                return (
                  <tr key={c.id}>
                    <td>{c.name}</td>
                    <td>
                      <input
                        type="number"
                        step="0.000001"
                        style={{ width: 120 }}
                        placeholder="41.012345"
                        value={g.latitude}
                        onChange={(e) => setGeo(c, "latitude", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        step="0.000001"
                        style={{ width: 120 }}
                        placeholder="28.987654"
                        value={g.longitude}
                        onChange={(e) => setGeo(c, "longitude", e.target.value)}
                      />
                    </td>
                    <td>
                      <input
                        type="number"
                        min="50"
                        max="20000"
                        style={{ width: 80 }}
                        value={g.radius}
                        onChange={(e) => setGeo(c, "radius", e.target.value)}
                      />
                    </td>
                    <td>
                      {active ? (
                        <span className="badge badge--in">Açık</span>
                      ) : hasCoords ? (
                        <span className="badge badge--auto">Duraklatıldı</span>
                      ) : (
                        <span className="badge badge--out">Kapalı</span>
                      )}
                    </td>
                    <td className="actions">
                      <button
                        className="btn btn--ghost btn--sm"
                        disabled={geoLocatingId === c.id}
                        onClick={() => useCurrentLocation(c)}
                      >
                        {geoLocatingId === c.id ? "Alınıyor…" : "Bu cihazın konumunu kullan"}
                      </button>
                      <button
                        className="btn btn--primary btn--sm"
                        disabled={geoBusyId === c.id}
                        onClick={() => saveGeo(c)}
                      >
                        {geoBusyId === c.id ? "Kaydediliyor…" : "Kaydet"}
                      </button>
                      {hasCoords && (
                        enabled ? (
                          <button
                            className="btn btn--warn btn--sm"
                            disabled={geoBusyId === c.id}
                            onClick={() => toggleGeoEnabled(c, false)}
                            title="Konumu silmeden kontrolü duraklatır"
                          >
                            Duraklat
                          </button>
                        ) : (
                          <button
                            className="btn btn--primary btn--sm"
                            disabled={geoBusyId === c.id}
                            onClick={() => toggleGeoEnabled(c, true)}
                            title="Kayıtlı konumla kontrolü yeniden açar"
                          >
                            Aç
                          </button>
                        )
                      )}
                      {hasCoords && (
                        <button
                          className="btn btn--ghost btn--sm"
                          disabled={geoBusyId === c.id}
                          onClick={() => clearGeo(c)}
                          title="Kayıtlı konumu tamamen siler"
                        >
                          Konumu Sil
                        </button>
                      )}
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
