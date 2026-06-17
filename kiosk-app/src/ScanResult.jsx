/**
 * Brief full-screen confirmation shown on the kiosk after a successful QR scan:
 * a green check with the person's name and "Giriş başarılı" / "Çıkış başarılı".
 * Tapping dismisses it early.
 */
export default function ScanResult({ name, type, onDone }) {
  const isIn = type === "IN";
  return (
    <div className="scanok" role="dialog" aria-live="polite" onClick={onDone}>
      <div className="scanok__card">
        <div className="scanok__check" aria-hidden="true">
          <svg viewBox="0 0 52 52" className="scanok__svg">
            <circle className="scanok__circle" cx="26" cy="26" r="24" fill="none" />
            <path className="scanok__tick" fill="none" d="M14 27 l8 8 l16 -18" />
          </svg>
        </div>
        <div className="scanok__title">
          {isIn ? "Giriş başarılı" : "Çıkış başarılı"}
        </div>
        <div className="scanok__name">{name}</div>
      </div>
    </div>
  );
}
