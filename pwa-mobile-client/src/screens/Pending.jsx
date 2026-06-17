import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth";

export default function Pending() {
  const { user, recheck, logout } = useAuth();
  const [checking, setChecking] = useState(false);
  const timer = useRef(null);

  // Poll for approval every 15s so the teacher flips to the scanner
  // automatically once the director approves — no app restart needed.
  useEffect(() => {
    timer.current = setInterval(() => recheck(), 15000);
    return () => clearInterval(timer.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onCheck = async () => {
    setChecking(true);
    try {
      await recheck();
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="screen center login">
      <div className="login__card">
        <div className="overlay__icon" style={{ color: "#f5b301" }}>
          ⏳
        </div>
        <h1 className="login__title">Onay Bekleniyor</h1>
        <p className="muted login__sub">
          Merhaba {user?.full_name}. Kaydınız{" "}
          <strong>{user?.campus_name || "kampüs"}</strong> müdürünün onayına
          gönderildi.
        </p>
        <p className="muted login__hint">
          Onaylandığında bu ekran otomatik olarak kameraya geçer. Müdürünüz
          onayladıktan sonra "Şimdi Kontrol Et"e dokunabilirsiniz.
        </p>

        <button className="btn btn--primary" disabled={checking} onClick={onCheck}>
          {checking ? "Kontrol ediliyor…" : "Şimdi Kontrol Et"}
        </button>
        <button className="link" onClick={logout}>
          Vazgeç / Çıkış
        </button>
      </div>
    </div>
  );
}
