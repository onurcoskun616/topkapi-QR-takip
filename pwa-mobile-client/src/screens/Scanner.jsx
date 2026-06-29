import { useCallback, useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { useAuth } from "../auth";
import {
  startWatching,
  subscribe as subscribeGeo,
  getPermission,
  getLocationForScan,
} from "../geolocation";
import LeaveRequest from "./LeaveRequest";

const READER_ID = "qr-reader";

export default function Scanner() {
  const { user, scan, myStatus, notificationStatus, enableNotifications, disableNotifications } =
    useAuth();
  const [mode, setMode] = useState("scan"); // scan | leave
  const [phase, setPhase] = useState("scanning"); // scanning | processing | result
  const [result, setResult] = useState(null); // { kind, message }
  const [cameraError, setCameraError] = useState(null);
  const [checkout, setCheckout] = useState(null); // {should_check_out, minutes_overdue}
  const [geoPerm, setGeoPerm] = useState(getPermission());

  // Web Push toggle state: "unsupported" | "disabled" | "denied" | "off" |
  // "on" | "busy". Only shown when the device supports it and the server has
  // push enabled (i.e. not "unsupported"/"disabled").
  const [pushState, setPushState] = useState(null);
  useEffect(() => {
    notificationStatus().then(setPushState).catch(() => setPushState("unsupported"));
  }, [notificationStatus]);

  const toggleNotifications = async () => {
    const prev = pushState;
    setPushState("busy");
    try {
      setPushState(prev === "on" ? await disableNotifications() : await enableNotifications());
    } catch (err) {
      setPushState(prev);
      alert(err.message || "Bildirim ayarı değiştirilemedi.");
    }
  };

  // Start watching the device location as soon as the scan screen opens, so the
  // browser asks for permission up front and a fresh fix is ready at scan time
  // (needed for campus geofencing).
  useEffect(() => {
    startWatching();
    return subscribeGeo(() => setGeoPerm(getPermission()));
  }, []);

  // Refresh the "still inside after shift" reminder (shown so the staff member
  // scans out before the nightly auto-close marks the day as a system OUT).
  const refreshStatus = useCallback(async () => {
    try {
      const s = await myStatus();
      setCheckout(s && s.should_check_out ? s : null);
    } catch {
      /* non-critical */
    }
  }, [myStatus]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const scannerRef = useRef(null);
  const lockRef = useRef(false);

  const stopScanner = useCallback(async () => {
    const s = scannerRef.current;
    scannerRef.current = null;
    if (s) {
      try {
        await s.stop();
        await s.clear();
      } catch {
        /* already stopped */
      }
    }
  }, []);

  const handleDecoded = useCallback(
    async (decodedText) => {
      if (lockRef.current) return;
      lockRef.current = true;
      setPhase("processing");
      // Grab the freshest location fix, then scan. The camera tears down in
      // parallel so the result shows as soon as the server replies.
      const scanPromise = getLocationForScan().then((loc) => scan(decodedText, loc));
      stopScanner();
      try {
        const res = await scanPromise;
        setResult({
          kind: res.type === "IN" ? "in" : "out",
          message: res.message,
        });
      } catch (err) {
        setResult({ kind: "error", message: err.message || "Geçersiz kod" });
      }
      setPhase("result");
      refreshStatus();
    },
    [scan, stopScanner, refreshStatus]
  );

  // Start the camera whenever we (re)enter the scanning phase — but not while
  // the leave-request view is open (the camera must release then).
  useEffect(() => {
    if (mode !== "scan" || phase !== "scanning") return;
    let cancelled = false;
    lockRef.current = false;
    setCameraError(null);

    const scanner = new Html5Qrcode(READER_ID, { verbose: false });
    scannerRef.current = scanner;

    // No qrbox: the library would otherwise draw its own scan-region UI (corner
    // brackets) positioned from the raw video frame, which drifts out of
    // alignment with our CSS-centered yellow frame once the video is letterboxed
    // by object-fit: cover. Scanning the whole frame keeps a single, accurate
    // guide (our .scanner__frame) and decodes anywhere.
    // useBarCodeDetectorIfSupported uses the platform's native QR decoder when
    // present (faster/more reliable than the bundled JS fallback), silently
    // falling back where it isn't.
    const scanConfig = {
      fps: 10,
      experimentalFeatures: { useBarCodeDetectorIfSupported: true },
    };

    (async () => {
      // Prefer a higher-resolution rear camera: iPhones often default to a
      // capture too low-res to decode a QR shown on a tablet across the counter
      // (camera opens but never reads). But some iOS versions REJECT resolution
      // hints outright (the camera then won't open at all), so if the rich
      // request fails we retry with the plain rear-camera request that always
      // worked before. Only a real permission/hardware failure shows the error.
      try {
        await scanner.start(
          { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
          scanConfig,
          handleDecoded,
          () => {} // per-frame decode failures are normal; ignore
        );
      } catch {
        if (cancelled) return;
        try {
          await scanner.start({ facingMode: "environment" }, scanConfig, handleDecoded, () => {});
        } catch {
          if (!cancelled) {
            setCameraError(
              "Kameraya erişilemedi. Lütfen tarayıcı izinlerini kontrol edin."
            );
          }
        }
      }
    })();

    return () => {
      cancelled = true;
      stopScanner();
    };
  }, [mode, phase, handleDecoded, stopScanner]);

  const scanAgain = () => {
    setResult(null);
    setPhase("scanning");
  };

  // Open the leave-request view: stop the camera first, then switch.
  const openLeave = async () => {
    await stopScanner();
    setResult(null);
    setMode("leave");
  };

  const backToScan = () => {
    setMode("scan");
    setPhase("scanning");
  };

  if (mode === "leave") {
    return <LeaveRequest onBack={backToScan} />;
  }

  return (
    <div className="screen scanner">
      <header className="scanner__header">
        <span className="scanner__name">{user?.full_name}</span>
        <div className="scanner__header-actions">
          {/* No "Çıkış": one phone is permanently bound to one employee. Switching
              devices is only possible after a manager's "Cihazı Sıfırla". */}
          {pushState && pushState !== "unsupported" && pushState !== "disabled" && (
            <button
              className="link"
              onClick={toggleNotifications}
              disabled={pushState === "busy" || pushState === "denied"}
              title={
                pushState === "denied"
                  ? "Bildirim izni reddedilmiş — tarayıcı ayarlarından açın"
                  : undefined
              }
            >
              {pushState === "on"
                ? "🔔 Bildirimler açık"
                : pushState === "busy"
                  ? "…"
                  : pushState === "denied"
                    ? "🔕 Bildirim engelli"
                    : "🔔 Bildirimleri Aç"}
            </button>
          )}
          <button className="link" onClick={openLeave}>
            İzin Talebi
          </button>
        </div>
      </header>

      {checkout && phase === "scanning" && (
        <div className="checkout-reminder">
          Mesai bitti ama hâlâ <strong>"içeride"</strong> görünüyorsunuz. Çıkış için QR
          okutmayı unutmayın — yoksa gün, sistem tarafından otomatik kapatılır.
        </div>
      )}

      {(geoPerm === "denied" || geoPerm === "unavailable") && phase === "scanning" && (
        <div className="checkout-reminder">
          Konum kapalı görünüyor. Giriş/çıkış yalnızca okul konumunda yapılabildiği
          için telefonunuzun <strong>konum iznini</strong> açın ve sayfayı yenileyin.
        </div>
      )}

      {/* Camera viewport (html5-qrcode injects the video here) */}
      <div id={READER_ID} className="scanner__reader" />

      {phase === "scanning" && !cameraError && (
        <div className="scanner__hint">
          <div className="scanner__frame" />
          <p>Tabletteki QR kodu çerçeveye alın</p>
        </div>
      )}

      {cameraError && (
        <div className="overlay overlay--error">
          <p className="overlay__msg">{cameraError}</p>
          <button className="btn btn--light" onClick={scanAgain}>
            Tekrar Dene
          </button>
        </div>
      )}

      {phase === "processing" && (
        <div className="overlay overlay--busy">
          <div className="spinner" />
        </div>
      )}

      {phase === "result" && result && (
        <div className={`overlay overlay--${result.kind}`}>
          <div className="overlay__icon">
            {result.kind === "in" ? "✓" : result.kind === "out" ? "↩" : "✕"}
          </div>
          <h2 className="overlay__title">
            {result.kind === "in"
              ? "Giriş Başarılı"
              : result.kind === "out"
                ? "Çıkış Başarılı"
                : "Geçersiz Kod"}
          </h2>
          <p className="overlay__msg">{result.message}</p>
          <button className="btn btn--light" onClick={scanAgain}>
            Tekrar Okut
          </button>
        </div>
      )}
    </div>
  );
}
