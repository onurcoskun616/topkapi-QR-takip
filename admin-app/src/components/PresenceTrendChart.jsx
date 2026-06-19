// SVG line+area chart of the daily "geliş oranı" (present ÷ expected) over a
// date range. Hand-rolled (no chart library, like the rest of the panel) and
// drawn in a fixed viewBox that CSS scales to the card width. Each point
// carries a <title> so hovering shows that day's exact numbers.
const W = 600;
const H = 200;
const PAD = { top: 16, right: 12, bottom: 26, left: 34 };

function shortDate(iso) {
  const [, m, d] = iso.split("-");
  return `${d}.${m}`;
}

export default function PresenceTrendChart({ trend }) {
  const entries = (trend?.entries || []).filter((e) => e.expected > 0);
  if (entries.length === 0) return <p className="muted">Veri yok.</p>;

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const n = entries.length;

  // Rate (0–100) per day; x evenly spaced across the inner width.
  const points = entries.map((e, i) => {
    const rate = Math.round((e.present / e.expected) * 100);
    const x = PAD.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
    const y = PAD.top + innerH - (rate / 100) * innerH;
    return { ...e, rate, x, y };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath =
    `M ${points[0].x.toFixed(1)} ${(PAD.top + innerH).toFixed(1)} ` +
    points.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") +
    ` L ${points[n - 1].x.toFixed(1)} ${(PAD.top + innerH).toFixed(1)} Z`;

  // Horizontal gridlines at 0 / 50 / 100 %.
  const gridYs = [0, 50, 100].map((pct) => ({
    pct,
    y: PAD.top + innerH - (pct / 100) * innerH,
  }));

  // Show at most ~7 x-axis labels so they don't collide on a busy range.
  const labelStep = Math.max(1, Math.ceil(n / 7));

  const avgRate = Math.round(points.reduce((s, p) => s + p.rate, 0) / n);

  return (
    <div className="lchart">
      <svg className="lchart__svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img">
        {gridYs.map((g) => (
          <g key={g.pct}>
            <line className="lchart__grid" x1={PAD.left} y1={g.y} x2={W - PAD.right} y2={g.y} />
            <text className="lchart__axis" x={PAD.left - 6} y={g.y + 3} textAnchor="end">
              {g.pct}%
            </text>
          </g>
        ))}

        <path className="lchart__area" d={areaPath} />
        <path className="lchart__line" d={linePath} />

        {points.map((p, i) => (
          <g key={p.date}>
            <circle className="lchart__pt" cx={p.x} cy={p.y} r={3} />
            <title>
              {`${p.date}\nGeliş oranı: %${p.rate}\nGelen: ${p.present} / Beklenen: ${p.expected}\nİzinli: ${p.on_leave} · Durum girilmedi: ${p.unresolved}`}
            </title>
            {i % labelStep === 0 && (
              <text className="lchart__axis" x={p.x} y={H - 8} textAnchor="middle">
                {shortDate(p.date)}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="lchart__foot muted small">
        Son {n} günün ortalama geliş oranı: <strong>%{avgRate}</strong>
      </div>
    </div>
  );
}
