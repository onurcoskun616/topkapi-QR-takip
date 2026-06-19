import React from "react";
import ReactDOM from "react-dom/client";
import { registerSW } from "virtual:pwa-register";
import "./installPrompt"; // capture beforeinstallprompt as early as possible
import App from "./App.jsx";
import InstallGate from "./screens/InstallGate.jsx";
import { AuthProvider } from "./auth.jsx";
import "./index.css";

// Auto-update the service worker in the background so teachers always get the
// latest app shell without a manual reinstall.
registerSW({ immediate: true });

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AuthProvider>
      <InstallGate>
        <App />
      </InstallGate>
    </AuthProvider>
  </React.StrictMode>
);
