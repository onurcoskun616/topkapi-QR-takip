import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Browsers only allow entering fullscreen (hides the address bar/browser chrome)
// from a real user gesture, so we can't do it on load — we arm a one-time
// listener that fires on the kiosk's very first tap/click and then removes
// itself. Tablets that "Add to Home Screen" skip this entirely (the
// manifest's display:fullscreen/standalone already hides the browser shell).
function requestKioskFullscreen() {
  const el = document.documentElement;
  if (document.fullscreenElement || el.requestFullscreen === undefined) return;
  el.requestFullscreen().catch(() => {});
}
document.addEventListener("click", requestKioskFullscreen, { once: true });
document.addEventListener("touchend", requestKioskFullscreen, { once: true });
