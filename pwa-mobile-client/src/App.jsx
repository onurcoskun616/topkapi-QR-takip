import { useAuth } from "./auth";
import Register from "./screens/Register";
import Pending from "./screens/Pending";
import Scanner from "./screens/Scanner";

export default function App() {
  const { phase } = useAuth();

  if (phase === "loading") {
    return (
      <div className="screen center">
        <div className="spinner" />
        <p className="muted">Oturum kontrol ediliyor…</p>
      </div>
    );
  }

  // Approved staff go straight to the camera; pending wait for director approval.
  if (phase === "authed") return <Scanner />;
  if (phase === "pending") return <Pending />;
  return <Register />;
}
