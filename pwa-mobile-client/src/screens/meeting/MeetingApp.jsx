import { useState } from "react";
import MeetingSetup from "./MeetingSetup";
import MeetingLive from "./MeetingLive";
import MeetingEnded from "./MeetingEnded";

// Faz 1 flow: Kurulum (setup) -> Canlı (live recording + manual speaker
// tagging) -> a simple read-only transcript. LLM compilation and the
// signature/PDF flow are Faz 3 and not part of this stage.
export default function MeetingApp({ onBack }) {
  const [stage, setStage] = useState("setup"); // setup | live | ended
  const [meeting, setMeeting] = useState(null);

  if (stage === "live" && meeting) {
    return (
      <MeetingLive
        meeting={meeting}
        onEnded={(m) => {
          setMeeting(m);
          setStage("ended");
        }}
      />
    );
  }

  if (stage === "ended" && meeting) {
    return <MeetingEnded meeting={meeting} onBack={onBack} />;
  }

  return (
    <MeetingSetup
      onBack={onBack}
      onStarted={(m) => {
        setMeeting(m);
        setStage("live");
      }}
    />
  );
}
