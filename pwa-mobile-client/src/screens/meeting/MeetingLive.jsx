import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth";

// Self-contained, independently-decodable audio blobs: stopping and
// restarting the recorder every CHUNK_MS (rather than one recorder with a
// `timeslice`) guarantees each blob carries its own container header, which
// is what the backend's ASR call needs to decode it on its own.
const CHUNK_MS = 6000;
const POLL_MS = 1500;

const RECORDER_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
];

function pickMimeType() {
  if (typeof MediaRecorder === "undefined") return "";
  return RECORDER_MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

export default function MeetingLive({ meeting, onEnded }) {
  const { uploadAudioChunk, getSegments, patchSegment, endMeeting } = useAuth();

  const [segments, setSegments] = useState(meeting.segments || []);
  const [activeSpeakerId, setActiveSpeakerId] = useState(null);
  const [currentAgendaIdx, setCurrentAgendaIdx] = useState(0);
  const [micError, setMicError] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState({ participant_id: "", text: "" });
  const [ending, setEnding] = useState(false);

  const activeSpeakerRef = useRef(null);
  const afterIdRef = useRef(
    segments.reduce((max, s) => Math.max(max, s.id), 0)
  );
  const mountedRef = useRef(true);

  useEffect(() => {
    activeSpeakerRef.current = activeSpeakerId;
  }, [activeSpeakerId]);

  const participantName = useCallback(
    (id) => meeting.participants.find((p) => p.id === id)?.display_name ?? null,
    [meeting.participants]
  );

  // --- Poll for new transcript lines (same idiom as kiosk-app: short
  // interval, dedupe by id via an "after_id" cursor). ---
  useEffect(() => {
    mountedRef.current = true;
    const tick = async () => {
      try {
        const fresh = await getSegments(meeting.id, afterIdRef.current);
        if (!mountedRef.current || fresh.length === 0) return;
        afterIdRef.current = Math.max(afterIdRef.current, ...fresh.map((s) => s.id));
        setSegments((prev) => [...prev, ...fresh]);
      } catch {
        /* transient network hiccup — next poll retries */
      }
    };
    const id = setInterval(tick, POLL_MS);
    return () => {
      mountedRef.current = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting.id]);

  // --- Mic capture: record ~6s self-contained chunks back to back, upload
  // each as soon as it's ready, tagged with whoever is currently selected as
  // "speaking now". ---
  useEffect(() => {
    let stopped = false;
    let stream = null;
    let recorder = null;

    const recordOneChunk = () =>
      new Promise((resolve, reject) => {
        try {
          recorder = new MediaRecorder(stream, {
            mimeType: pickMimeType() || undefined,
          });
        } catch (err) {
          reject(err);
          return;
        }
        const chunks = [];
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };
        recorder.onstop = () => resolve(new Blob(chunks, { type: recorder.mimeType }));
        recorder.onerror = (e) => reject(e.error || new Error("Kayıt hatası"));
        recorder.start();
        setTimeout(() => {
          if (recorder.state !== "inactive") recorder.stop();
        }, CHUNK_MS);
      });

    const loop = async () => {
      while (!stopped) {
        let blob;
        try {
          blob = await recordOneChunk();
        } catch {
          break;
        }
        if (stopped) break;
        try {
          const seg = await uploadAudioChunk(meeting.id, blob, activeSpeakerRef.current);
          if (seg && mountedRef.current) {
            afterIdRef.current = Math.max(afterIdRef.current, seg.id);
            setSegments((prev) =>
              prev.some((s) => s.id === seg.id) ? prev : [...prev, seg]
            );
          }
        } catch {
          /* one bad chunk shouldn't stop the meeting — keep recording */
        }
      }
    };

    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMicError("Bu tarayıcıda mikrofon erişimi desteklenmiyor.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (stopped) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        loop();
      } catch {
        setMicError("Mikrofona erişilemedi. Lütfen tarayıcı izinlerini kontrol edin.");
      }
    })();

    return () => {
      stopped = true;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting.id]);

  const startEdit = (seg) => {
    setEditingId(seg.id);
    setEditDraft({ participant_id: seg.participant_id ?? "", text: seg.text });
  };

  const saveEdit = async () => {
    const seg = segments.find((s) => s.id === editingId);
    if (!seg) return;
    const payload = {};
    if (editDraft.text !== seg.text) payload.text = editDraft.text;
    const newParticipantId = editDraft.participant_id === "" ? null : Number(editDraft.participant_id);
    if (newParticipantId !== seg.participant_id) {
      if (newParticipantId === null) payload.clear_participant = true;
      else payload.participant_id = newParticipantId;
    }
    if (Object.keys(payload).length === 0) {
      setEditingId(null);
      return;
    }
    try {
      const updated = await patchSegment(meeting.id, seg.id, payload);
      setSegments((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (err) {
      alert(err.message || "Satır güncellenemedi.");
    }
    setEditingId(null);
  };

  const onEndMeeting = async () => {
    setEnding(true);
    try {
      await endMeeting(meeting.id);
      // after_id=0 returns every segment — the authoritative final transcript.
      const final = await getSegments(meeting.id, 0).catch(() => null);
      onEnded({ ...meeting, status: "ended", segments: final || segments });
    } catch (err) {
      alert(err.message || "Toplantı bitirilemedi.");
      setEnding(false);
    }
  };

  return (
    <div className="screen mtg">
      <header className="scanner__header">
        <span className="scanner__name">{meeting.title}</span>
        <span className="mtg-rec-pill">● Kayıtta</span>
      </header>

      <div className="mtg-body">
        {meeting.agenda_items.length > 0 && (
          <div className="mtg-agenda-strip">
            {meeting.agenda_items.map((item, i) => (
              <div
                key={item.id}
                className={`mtg-agenda-chip${i === currentAgendaIdx ? " current" : ""}`}
                onClick={() => setCurrentAgendaIdx(i)}
              >
                {String(i + 1).padStart(2, "0")} · {item.title}
              </div>
            ))}
          </div>
        )}

        <div className="mtg-field-label">Şu An Konuşan</div>
        <div className="mtg-speaker-strip">
          <div
            className={`mtg-speaker-chip${activeSpeakerId === null ? " current" : ""}`}
            onClick={() => setActiveSpeakerId(null)}
          >
            Bilinmiyor
          </div>
          {meeting.participants.map((p) => (
            <div
              key={p.id}
              className={`mtg-speaker-chip${activeSpeakerId === p.id ? " current" : ""}`}
              onClick={() => setActiveSpeakerId(p.id)}
            >
              {p.display_name}
            </div>
          ))}
        </div>

        {micError && <p className="error">{micError}</p>}

        <div className="mtg-ledger">
          {segments.length === 0 && (
            <p className="muted mtg-hint">Konuşmalar burada belirecek…</p>
          )}
          {segments.map((seg) => (
            <div className="mtg-line" key={seg.id}>
              {editingId === seg.id ? (
                <div className="mtg-edit">
                  <select
                    className="input mtg-input"
                    value={editDraft.participant_id}
                    onChange={(e) => setEditDraft({ ...editDraft, participant_id: e.target.value })}
                  >
                    <option value="">Bilinmiyor</option>
                    {meeting.participants.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.display_name}
                      </option>
                    ))}
                  </select>
                  <textarea
                    className="input mtg-input mtg-edit-text"
                    value={editDraft.text}
                    onChange={(e) => setEditDraft({ ...editDraft, text: e.target.value })}
                  />
                  <div className="mtg-edit-actions">
                    <button className="btn btn--primary" onClick={saveEdit}>
                      Kaydet
                    </button>
                    <button className="btn" onClick={() => setEditingId(null)}>
                      İptal
                    </button>
                  </div>
                </div>
              ) : (
                <div onClick={() => startEdit(seg)}>
                  <span className={`mtg-speaker-tag${seg.participant_id ? "" : " unmatched"}`}>
                    {seg.participant_name || participantName(seg.participant_id) || "Konuşmacı belirsiz"}
                  </span>
                  <div className="mtg-utterance">{seg.text}</div>
                  {!seg.participant_id && <span className="mtg-flag">İsim onayı bekliyor</span>}
                </div>
              )}
            </div>
          ))}
        </div>

        <button
          className="btn mtg-stop-btn"
          onClick={onEndMeeting}
          disabled={ending}
        >
          {ending ? "Bitiriliyor…" : "Toplantıyı Bitir"}
        </button>
      </div>
    </div>
  );
}
