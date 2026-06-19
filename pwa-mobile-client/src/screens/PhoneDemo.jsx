// A tiny self-contained (CSS/SVG only, no assets) looping animation of a phone
// showing the 3 steps to install: tap → "Ana Ekrana Ekle" → icon on the home
// screen. The `variant` tailors the first two frames to how the platform
// actually installs: a native button (Android with a captured prompt), the
// Android ⋮ menu, or the iOS share sheet.
function ShareIcon() {
  return (
    <svg className="demo-share" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3v11M12 3l-4 4M12 3l4 4"
        stroke="#0b1f3a"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6 11v8a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-8"
        stroke="#0b1f3a"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function HomeFrame() {
  return (
    <div className="demo-frame demo-frame--3">
      <div className="demo-home">
        <div className="demo-home__pop">
          <img src="/pwa-192.png" className="demo-home__icon" alt="" />
          <span className="demo-home__label">Yoklama</span>
        </div>
        <span className="demo-home__check">✓ Ana ekrana eklendi</span>
      </div>
    </div>
  );
}

export default function PhoneDemo({ variant }) {
  return (
    <div className="phone" aria-hidden="true">
      <span className="phone__notch" />
      <div className="phone__screen">
        {variant === "button" && (
          <>
            <div className="demo-frame demo-frame--1">
              <div className="demo-browser">
                <div className="demo-topbar">
                  <span className="demo-url">app.topkapiokullari.com</span>
                </div>
                <div className="demo-body">
                  <span className="demo-cta">
                    📲 Ana Ekrana Ekle
                    <span className="demo-tap demo-tap--center" />
                  </span>
                </div>
              </div>
            </div>
            <div className="demo-frame demo-frame--2">
              <div className="demo-body demo-body--dim">
                <div className="demo-dialog">
                  <img src="/pwa-192.png" className="demo-dialog__icon" alt="" />
                  <span className="demo-dialog__title">Yoklama’yı yükle?</span>
                  <div className="demo-dialog__btns">
                    <span className="demo-dialog__btn">İptal</span>
                    <span className="demo-dialog__btn demo-dialog__btn--hot">
                      Yükle
                      <span className="demo-tap demo-tap--center" />
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <HomeFrame />
          </>
        )}

        {variant === "android" && (
          <>
            <div className="demo-frame demo-frame--1">
              <div className="demo-browser">
                <div className="demo-topbar">
                  <span className="demo-url">app.topkapiokullari.com</span>
                  <span className="demo-dots">
                    ⋮<span className="demo-tap demo-tap--dots" />
                  </span>
                </div>
                <div className="demo-body" />
              </div>
            </div>
            <div className="demo-frame demo-frame--2">
              <div className="demo-browser">
                <div className="demo-topbar">
                  <span className="demo-url">app.topkapiokullari.com</span>
                  <span className="demo-dots">⋮</span>
                </div>
                <div className="demo-menu">
                  <span className="demo-menu__item">Yeni sekme</span>
                  <span className="demo-menu__item demo-menu__item--hot">
                    ⊕ Ana ekrana ekle
                    <span className="demo-tap demo-tap--menu" />
                  </span>
                  <span className="demo-menu__item">Geçmiş</span>
                </div>
              </div>
            </div>
            <HomeFrame />
          </>
        )}

        {variant === "ios" && (
          <>
            <div className="demo-frame demo-frame--1">
              <div className="demo-browser">
                <div className="demo-topbar demo-topbar--center">
                  <span className="demo-url">app.topkapiokullari.com</span>
                </div>
                <div className="demo-body" />
                <div className="demo-iosbar">
                  <span className="demo-sharebtn">
                    <ShareIcon />
                    <span className="demo-tap demo-tap--share" />
                  </span>
                </div>
              </div>
            </div>
            <div className="demo-frame demo-frame--2">
              <div className="demo-body demo-body--dim">
                <div className="demo-sheet">
                  <span className="demo-sheet__row">Kopyala</span>
                  <span className="demo-sheet__row demo-sheet__row--hot">
                    <span className="demo-sheet__plus">＋</span> Ana Ekrana Ekle
                    <span className="demo-tap demo-tap--sheet" />
                  </span>
                  <span className="demo-sheet__row">Yer İşareti Ekle</span>
                </div>
              </div>
            </div>
            <HomeFrame />
          </>
        )}
      </div>
    </div>
  );
}
