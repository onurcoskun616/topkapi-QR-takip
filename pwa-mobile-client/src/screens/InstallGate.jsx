import { useEffect, useState } from "react";
import {
  subscribe,
  getDeferredPrompt,
  promptInstall,
  isStandalone,
  isIOS,
  wasInstalled,
} from "../installPrompt";
import PhoneDemo from "./PhoneDemo";

// Remembers a "continue in browser" choice for the current tab session only, so
// the install nudge reappears on the next visit (we want install-first) without
// hard-locking anyone who genuinely can't install (iOS edge cases, in-app
// browsers, desktop).
const SKIP_KEY = "yoklama_install_skip";

export default function InstallGate({ children }) {
  const [standalone] = useState(isStandalone);
  const [skipped, setSkipped] = useState(
    () => sessionStorage.getItem(SKIP_KEY) === "1"
  );
  const [busy, setBusy] = useState(false);
  // Re-render when the install event arrives / the app gets installed.
  const [, force] = useState(0);

  useEffect(() => subscribe(() => force((n) => n + 1)), []);

  // Installed app (launched from the home screen) → straight to the real app.
  if (standalone || skipped) return children;

  const hasPrompt = !!getDeferredPrompt();
  const ios = isIOS();
  const demoVariant = hasPrompt ? "button" : ios ? "ios" : "android";

  const onInstall = async () => {
    setBusy(true);
    await promptInstall();
    setBusy(false);
    // On "accepted", the appinstalled event flips us to the success message.
  };

  const onContinue = () => {
    sessionStorage.setItem(SKIP_KEY, "1");
    setSkipped(true);
  };

  return (
    <div className="screen center install">
      <div className="install__brand">
        <img
          src="/topkapi-logo.png"
          alt="Topkapı Okulları"
          className="install__brandimg"
        />
      </div>
      <p className="install__appname">Personel Yoklama Uygulaması</p>

      {wasInstalled() ? (
        <div className="install__done">
          <p className="install__lead">Uygulama ana ekranınıza eklendi. ✅</p>
          <p className="muted">
            Şimdi telefonunuzun ana ekranındaki <b>Yoklama</b> simgesinden açın
            ve kaydınızı oradan yapın.
          </p>
        </div>
      ) : (
        <>
          <p className="install__lead">
            Devam etmeden önce uygulamayı telefonunuzun <b>ana ekranına ekleyin</b>.
            Kayıt ve giriş/çıkış işlemleri yalnızca uygulama üzerinden yapılır.
          </p>

          <PhoneDemo variant={demoVariant} />

          {hasPrompt ? (
            <button
              className="btn btn--primary install__cta"
              disabled={busy}
              onClick={onInstall}
            >
              {busy ? "Açılıyor…" : "📲 Ana Ekrana Ekle"}
            </button>
          ) : ios ? (
            <ol className="install__steps">
              <li>
                Alt çubuktaki <b>Paylaş</b> simgesine dokunun (kareden yukarı ok).
              </li>
              <li>
                Açılan listede <b>Ana Ekrana Ekle</b> seçeneğine dokunun.
              </li>
              <li>
                Sağ üstte <b>Ekle</b>’ye dokunun.
              </li>
              <li>
                Ana ekrandaki <b>Yoklama</b> simgesinden açın.
              </li>
            </ol>
          ) : (
            <ol className="install__steps">
              <li>
                Sağ üstteki <b>⋮</b> (üç nokta) menüsüne dokunun.
              </li>
              <li>
                <b>Ana ekrana ekle</b> ya da <b>Uygulamayı yükle</b> seçeneğine
                dokunun.
              </li>
              <li>
                <b>Ekle / Yükle</b> diyerek onaylayın.
              </li>
              <li>
                Ana ekrandaki <b>Yoklama</b> simgesinden açın.
              </li>
            </ol>
          )}

          <button className="link install__skip" onClick={onContinue}>
            Uygulamayı kuramıyorum, tarayıcıda devam et
          </button>
        </>
      )}
    </div>
  );
}
