import { useState } from "react";
import { useAuth } from "../../auth";

export default function MeetingSetup({ onBack, onStarted }) {
  const { createMeeting, startMeeting } = useAuth();
  const [title, setTitle] = useState("");
  const [agendaItems, setAgendaItems] = useState([]);
  const [agendaDraft, setAgendaDraft] = useState("");
  const [participants, setParticipants] = useState([]);
  const [participantDraft, setParticipantDraft] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const addAgendaItem = () => {
    const v = agendaDraft.trim();
    if (!v) return;
    setAgendaItems([...agendaItems, v]);
    setAgendaDraft("");
  };

  const addParticipant = () => {
    const v = participantDraft.trim();
    if (!v) return;
    setParticipants([...participants, v]);
    setParticipantDraft("");
  };

  const onStart = async () => {
    if (!title.trim()) {
      setError("Lütfen toplantı başlığı girin.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const meeting = await createMeeting({
        title: title.trim(),
        agenda_items: agendaItems,
        participants,
      });
      const started = await startMeeting(meeting.id);
      onStarted(started);
    } catch (err) {
      setError(err.message || "Toplantı başlatılamadı.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screen mtg">
      <header className="scanner__header">
        <button className="link" onClick={onBack}>
          ← Geri
        </button>
        <span className="scanner__name">Toplantıyı Kur</span>
      </header>

      <div className="mtg-body">
        <div className="mtg-field-label">Toplantı Başlığı</div>
        <input
          className="input mtg-input"
          placeholder="Örn. Şubat Ayı Değerlendirme Toplantısı"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={busy}
        />

        <div className="mtg-field-label">Gündem Maddeleri (opsiyonel)</div>
        {agendaItems.map((item, i) => (
          <div className="mtg-list-item" key={i}>
            <span className="mtg-idx">{String(i + 1).padStart(2, "0")}</span>
            <span className="mtg-list-item-text">{item}</span>
            <button
              className="mtg-remove"
              onClick={() => setAgendaItems(agendaItems.filter((_, j) => j !== i))}
              aria-label="Kaldır"
            >
              ×
            </button>
          </div>
        ))}
        <div className="mtg-add-row">
          <input
            className="input mtg-input"
            placeholder="Gündem maddesi ekle…"
            value={agendaDraft}
            onChange={(e) => setAgendaDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addAgendaItem()}
            disabled={busy}
          />
          <button className="mtg-add-btn" onClick={addAgendaItem} disabled={busy}>
            +
          </button>
        </div>

        <div className="mtg-field-label">Katılımcılar</div>
        {participants.map((name, i) => (
          <div className="mtg-list-item" key={i}>
            <span className="mtg-avatar">{name.slice(0, 2).toUpperCase()}</span>
            <span className="mtg-list-item-text">{name}</span>
            <button
              className="mtg-remove"
              onClick={() => setParticipants(participants.filter((_, j) => j !== i))}
              aria-label="Kaldır"
            >
              ×
            </button>
          </div>
        ))}
        <div className="mtg-add-row">
          <input
            className="input mtg-input"
            placeholder="Katılımcı ad-soyad ekle…"
            value={participantDraft}
            onChange={(e) => setParticipantDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addParticipant()}
            disabled={busy}
          />
          <button className="mtg-add-btn" onClick={addParticipant} disabled={busy}>
            +
          </button>
        </div>

        {error && <p className="error">{error}</p>}

        <button className="btn btn--primary mtg-start-btn" onClick={onStart} disabled={busy}>
          {busy ? "Başlatılıyor…" : "Toplantıyı Başlat"}
        </button>
        <p className="muted mtg-hint">
          Kayıt sırasında "şu an konuşan" katılımcıyı seçerek konuşmaları
          isimle etiketleyebilirsiniz — otomatik ses tanıma sonraki aşamada
          eklenecek.
        </p>
      </div>
    </div>
  );
}
