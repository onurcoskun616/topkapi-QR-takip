import { useState } from "react";
import { useAuth } from "./auth";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import Users from "./components/Users";

export default function App() {
  const { isAuthed, loading, user, logout } = useAuth();
  const [tab, setTab] = useState("dashboard");

  if (loading) {
    return <div className="centered muted">Yükleniyor…</div>;
  }
  if (!isAuthed) {
    return <Login />;
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand__mark">●</span> Topkapı Yoklama —
          Yönetim Paneli
        </div>
        <nav className="tabs">
          <button
            className={tab === "dashboard" ? "tab tab--active" : "tab"}
            onClick={() => setTab("dashboard")}
          >
            Gösterge Paneli
          </button>
          <button
            className={tab === "users" ? "tab tab--active" : "tab"}
            onClick={() => setTab("users")}
          >
            Kullanıcılar
          </button>
        </nav>
        <div className="topbar__right">
          <span className="muted">{user?.full_name}</span>
          <button className="btn btn--ghost" onClick={logout}>
            Çıkış
          </button>
        </div>
      </header>

      <main className="content">
        {tab === "dashboard" ? <Dashboard /> : <Users />}
      </main>
    </div>
  );
}
