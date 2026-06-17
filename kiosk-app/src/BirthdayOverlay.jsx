import { useMemo } from "react";

/**
 * Full-screen birthday greeting shown on the kiosk when a staff member whose
 * birthday is today scans their first IN. Pure CSS confetti — no dependencies.
 */
const CONFETTI_COLORS = ["#ffc83d", "#ff6b6b", "#4dd4ac", "#5a9bff", "#c779ff", "#ffffff"];

export default function BirthdayOverlay({ name, onDone }) {
  // Pre-compute confetti pieces once so they don't reshuffle on every render.
  const pieces = useMemo(
    () =>
      Array.from({ length: 60 }, (_, i) => ({
        id: i,
        left: Math.random() * 100,
        delay: Math.random() * 2,
        duration: 2.5 + Math.random() * 2,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        size: 8 + Math.random() * 8,
      })),
    []
  );

  return (
    <div className="birthday" role="dialog" aria-live="polite" onClick={onDone}>
      <div className="birthday__confetti" aria-hidden="true">
        {pieces.map((p) => (
          <span
            key={p.id}
            className="birthday__piece"
            style={{
              left: `${p.left}%`,
              animationDelay: `${p.delay}s`,
              animationDuration: `${p.duration}s`,
              background: p.color,
              width: `${p.size}px`,
              height: `${p.size}px`,
            }}
          />
        ))}
      </div>

      <div className="birthday__card">
        <div className="birthday__emoji">🎂🎉</div>
        <div className="birthday__greeting">İyi ki doğdun!</div>
        <div className="birthday__name">{name}</div>
        <div className="birthday__sub">Doğum günün kutlu olsun 🎈</div>
      </div>
    </div>
  );
}
