import { useAuth } from "./auth";
import Login from "./screens/Login";
import Scanner from "./screens/Scanner";

export default function App() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="screen center">
        <div className="spinner" />
        <p className="muted">Oturum kontrol ediliyor…</p>
      </div>
    );
  }

  // Authenticated teachers go straight to the camera; no login screen.
  return status === "authed" ? <Scanner /> : <Login />;
}
