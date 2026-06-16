import { useState } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    if (!email || !password) {
      setError("E-posta ve şifre gereklidir.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || "Giriş başarısız.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screen center login">
      <form className="login__card" onSubmit={onSubmit}>
        <h1 className="login__title">Topkapı Okulları</h1>
        <p className="muted login__sub">Personel Giriş/Çıkış</p>

        <input
          className="input"
          type="email"
          inputMode="email"
          autoComplete="username"
          placeholder="E-posta"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={busy}
        />
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          placeholder="Şifre"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={busy}
        />

        {error && <p className="error">{error}</p>}

        <button className="btn btn--primary" disabled={busy} type="submit">
          {busy ? "Giriş yapılıyor…" : "Giriş Yap"}
        </button>

        <p className="muted login__hint">
          Bir kez giriş yaptıktan sonra cihazınız hatırlanır; ertesi günler
          doğrudan kamera açılır.
        </p>
      </form>
    </div>
  );
}
