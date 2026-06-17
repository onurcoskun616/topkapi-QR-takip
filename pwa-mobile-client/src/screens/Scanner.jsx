import { useCallback, useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { useAuth } from "../auth";

const READER_ID = "qr-reader";

export default function Scanner() {
  const { user, logout, scan } = useAuth();
  const [phase, setPhase] = useState("scanning"); // scanning | processing | result
  const [result, setResult] = useState(null); // { kind, message }
  const [cameraError, setCameraError] = useState(null);

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
      // Fire the scan request immediately and tear the camera down in parallel,
      // so the success/failure shows as soon as the server replies instead of
      // waiting for the camera to stop first.
      const scanPromise = scan(decodedText);
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
    },
    [scan, stopScanner]
  );

  // Start the camera whenever we (re)enter the scanning phase.
  useEffect(() => {
    if (phase !== "scanning") return;
    let cancelled = false;
    lockRef.current = false;
    setCameraError(null);

    const scanner = new Html5Qrcode(READER_ID, { verbose: false });
    scannerRef.current = scanner;

    scanner
      .start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 240, height: 240 } },
        handleDecoded,
        () => {} // per-frame decode failures are normal; ignore
      )
      .catch((err) => {
        if (!cancelled) {
          setCameraError(
            "Kameraya erişilemedi. Lütfen tarayıcı izinlerini kontrol edin."
          );
        }
      });

    return () => {
      cancelled = true;
      stopScanner();
    };
  }, [phase, handleDecoded, stopScanner]);

  const scanAgain = () => {
    setResult(null);
    setPhase("scanning");
  };

  return (
    <div className="screen scanner">
      <header className="scanner__header">
        <span className="scanner__name">{user?.full_name}</span>
        <button className="link" onClick={logout}>
          Çıkış
        </button>
      </header>

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
