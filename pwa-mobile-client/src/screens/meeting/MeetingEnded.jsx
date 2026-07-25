export default function MeetingEnded({ meeting, onBack }) {
  const started = meeting.started_at ? new Date(meeting.started_at) : null;
  const ended = meeting.ended_at ? new Date(meeting.ended_at) : null;
  const fmt = (d) =>
    d ? d.toLocaleString("tr-TR", { dateStyle: "long", timeStyle: "short" }) : "";

  return (
    <div className="screen mtg">
      <header className="scanner__header">
        <button className="link" onClick={onBack}>
          ← Geri
        </button>
        <span className="scanner__name">Tutanak</span>
      </header>

      <div className="mtg-body">
        <div className="mtg-doc-page">
          <div className="mtg-doc-title">{meeting.title}</div>
          <div className="mtg-doc-meta">
            {fmt(started)}
            {ended && ` — ${ended.toLocaleTimeString("tr-TR", { timeStyle: "short" })}`}
            {" · "}
            {meeting.participants.length} Katılımcı
          </div>
          <div className="mtg-doc-rule" />

          <div className="mtg-doc-h">Katılımcılar</div>
          <div className="mtg-doc-body">
            {meeting.participants.map((p) => p.display_name).join(", ") || "—"}
          </div>

          <div className="mtg-doc-h">Konuşma Dökümü</div>
          {meeting.segments.length === 0 ? (
            <p className="muted">Bu toplantıda kayıtlı konuşma yok.</p>
          ) : (
            meeting.segments.map((seg) => (
              <div className="mtg-doc-body" key={seg.id}>
                <strong>{seg.participant_name || "Konuşmacı belirsiz"}:</strong> {seg.text}
              </div>
            ))
          )}
        </div>

        <p className="muted mtg-hint">
          Bu, Faz 1 iskeletinin ham dökümüdür — gündem/karar bazlı derleme
          (yapay zekâ) ve imza akışı sonraki aşamalarda eklenecek.
        </p>
      </div>
    </div>
  );
}
