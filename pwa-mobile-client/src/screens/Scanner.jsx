import { useCallback, useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { useAuth } from "../auth";
import {
  startWatching,
  subscribe as subscribeGeo,
  getPermission,
  getLocationForScan,
} from "../geolocation";
import LeaveRequest from "./LeaveRequest";

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

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const loopRef = useRef(null);
  const lockRef = useRef(false);

  const stopScanner = useCallback(() => {
    if (loopRef.current) {
      clearTimeout(loopRef.current);
      loopRef.current = null;
    }
    const v = videoRef.current;
    if (v) {
      try {
        v.pause();
      } catch {
        /* ignore */
      }
      v.srcObject = null;
    }
    const s = streamRef.current;
    streamRef.current = null;
    if (s) s.getTracks().forEach((t) => t.stop());
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

  // Open the rear camera and decode QR frames OURSELVES with jsQR. We grab raw
  // video frames onto an off-screen canvas and run jsQR on the pixels. This is
  // far more reliable on iPhones (11/12/13/14) than html5-qrcode's bundled
  // decoder, which failed to read on iOS while Android worked. Because decoding
  // reads the raw frame, the on-screen video can fill the screen (object-fit:
  // cover) without affecting what the decoder sees.
  useEffect(() => {
    if (mode !== "scan" || phase !== "scanning") return;
    let cancelled = false;
    lockRef.current = false;
    setCameraError(null);

    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });

    const tick = () => {
      if (cancelled) return;
      const v = videoRef.current;
      if (v && v.readyState >= 2 && v.videoWidth > 0 && ctx) {
        // Downscale big camera frames so jsQR stays fast; a QR still decodes
        // well at this size.
        const scale = Math.min(1, 720 / Math.max(v.videoWidth, v.videoHeight));
        const w = Math.max(1, Math.round(v.videoWidth * scale));
        const h = Math.max(1, Math.round(v.videoHeight * scale));
        if (canvas.width !== w) canvas.width = w;
        if (canvas.height !== h) canvas.height = h;
        ctx.drawImage(v, 0, 0, w, h);
        try {
          const img = ctx.getImageData(0, 0, w, h);
          const code = jsQR(img.data, w, h, { inversionAttempts: "dontInvert" });
          if (code && code.data) {
            handleDecoded(code.data);
            return; // handleDecoded tears the camera down
          }
        } catch {
          /* transient canvas read error; keep scanning */
        }
      }
      loopRef.current = setTimeout(tick, 120);
    };

    (async () => {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraError("Kameraya erişilemedi. Lütfen tarayıcı izinlerini kontrol edin.");
        return;
      }
      try {
        // Keep the request MINIMAL (just the rear camera). Resolution hints make
        // getUserMedia reject on some iPhones, blanking the camera entirely.
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "environment" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        const v = videoRef.current;
        if (!v) return;
        v.setAttribute("playsinline", "true");
        v.muted = true;
        v.srcObject = stream;
        await v.play().catch(() => {});
        loopRef.current = setTimeout(tick, 200);
      } catch {
        if (!cancelled) {
          setCameraError(
            "Kameraya erişilemedi. Lütfen tarayıcı izinlerini kontrol edin."
          );
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

      {/* Camera viewport: the rear-camera video; jsQR reads frames off-screen. */}
      <div className="scanner__reader">
        <video ref={videoRef} playsInline muted autoPlay />
      </div>

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
