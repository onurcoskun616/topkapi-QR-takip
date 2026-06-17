import { useState } from "react";
import { useAuth } from "./auth";
import Login from "./components/Login";
import Dashboard from "./components/Dashboard";
import Staff from "./components/Staff";
import Leaves from "./components/Leaves";
import Holidays from "./components/Holidays";
import Reports from "./components/Reports";
import Directors from "./components/Directors";
import Campuses from "./components/Campuses";

export default function App() {
  const { isAuthed, loading, user, logout } = useAuth();
  const [tab, setTab] = useState("dashboard");

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
        {tab === "reports" && <Reports isHq={isHq} />}
        {tab === "directors" && isHq && <Directors />}
        {tab === "campuses" && isHq && <Campuses />}
      </main>
    </div>
  );
}
