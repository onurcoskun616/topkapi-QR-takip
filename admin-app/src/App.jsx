import { useState } from "react";
import { useAuth } from "./auth";
import { api } from "./api";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import Staff from "./components/Staff";
import Leaves from "./components/Leaves";
import Holidays from "./components/Holidays";
import Announcements from "./components/Announcements";
import Calendar from "./components/Calendar";
import Reports from "./components/Reports";
import Directors from "./components/Directors";
import Campuses from "./components/Campuses";

function ChangePasswordModal({ token, onClose }) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(token, currentPassword, newPassword);
      setNotice("Şifreniz güncellendi.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="card" onClick={(e) => e.stopPropagation()}>
        <h2 className="card__title">Şifremi Değiştir</h2>
        <form className="stack" onSubmit={submit}>
          <label className="field">
            <span>Mevcut şifre</span>
            <input
              type="password"
              required
              autoFocus
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Yeni şifre (min 8)</span>
            <input
              type="password"
              minLength={8}
              required
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>

          {error && <p className="error">{error}</p>}
          {notice && <p className="notice">{notice}</p>}

          <div className="actions">
            <button className="btn btn--primary" disabled={busy} type="submit">
              {busy ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button className="btn btn--ghost" type="button" disabled={busy} onClick={onClose}>
              Kapat
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const { isAuthed, loading, user, logout, token } = useAuth();
  const [tab, setTab] = useState("dashboard");
  const [showPasswordModal, setShowPasswordModal] = useState(false);

  if (loading) {
    return <div className="centered muted">Yükleniyor…</div>;
  }
  if (!isAuthed) {
    return <Login />;
  }

  const isHq = user?.role === "hq";
  const scopeLabel = isHq ? "Genel Merkez" : user?.campus_name || "Kampüs";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">●</span> Topkapı Yoklama —{" "}
          {isHq ? "Genel Merkez" : "Kampüs Paneli"}
        </div>
        <nav className="tabs">
          <button
            className={tab === "dashboard" ? "tab tab--active" : "tab"}
            onClick={() => setTab("dashboard")}
          >
            Gösterge Paneli
          </button>
          <button
            className={tab === "staff" ? "tab tab--active" : "tab"}
            onClick={() => setTab("staff")}
          >
            Personel
          </button>
          <button
            className={tab === "leaves" ? "tab tab--active" : "tab"}
            onClick={() => setTab("leaves")}
          >
            İzin / Devamsızlık
          </button>
          <button
            className={tab === "holidays" ? "tab tab--active" : "tab"}
            onClick={() => setTab("holidays")}
          >
            Tatiller
          </button>
          <button
            className={tab === "announcements" ? "tab tab--active" : "tab"}
            onClick={() => setTab("announcements")}
          >
            Duyurular
          </button>
          <button
            className={tab === "calendar" ? "tab tab--active" : "tab"}
            onClick={() => setTab("calendar")}
          >
            Takvim
          </button>
          <button
            className={tab === "reports" ? "tab tab--active" : "tab"}
            onClick={() => setTab("reports")}
          >
            Raporlar
          </button>
          {isHq && (
            <button
              className={tab === "directors" ? "tab tab--active" : "tab"}
              onClick={() => setTab("directors")}
            >
              Müdürler
            </button>
          )}
          {isHq && (
            <button
              className={tab === "campuses" ? "tab tab--active" : "tab"}
              onClick={() => setTab("campuses")}
            >
              Kampüsler
            </button>
          )}
        </nav>
        <div className="topbar__right">
          <span className="badge badge--in">{scopeLabel}</span>
          <span className="muted">{user?.full_name}</span>
          <button className="btn btn--ghost" onClick={() => setShowPasswordModal(true)}>
            Şifremi Değiştir
          </button>
          <button className="btn btn--ghost" onClick={logout}>
            Çıkış
          </button>
        </div>
      </header>

      <main className="content">
        {tab === "dashboard" && <Dashboard isHq={isHq} />}
        {tab === "staff" && <Staff isHq={isHq} />}
        {tab === "leaves" && <Leaves isHq={isHq} />}
        {tab === "holidays" && <Holidays isHq={isHq} />}
        {tab === "announcements" && <Announcements isHq={isHq} />}
        {tab === "calendar" && <Calendar isHq={isHq} />}
        {tab === "reports" && <Reports isHq={isHq} />}
        {tab === "directors" && isHq && <Directors />}
        {tab === "campuses" && isHq && <Campuses />}
      </main>

      {showPasswordModal && (
        <ChangePasswordModal token={token} onClose={() => setShowPasswordModal(false)} />
      )}
    </div>
  );
}
