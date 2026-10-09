"use client";

import { useState } from "react";
import { Slider } from "@/components/ui/slider";
import { RECORD_DURATION_MS, type RecordingPhase } from "@/hooks/use-recording";
import { formatElapsedMs } from "@/lib/auriscore/format";

interface RecordingControlsProps {
  phase: RecordingPhase;
  elapsedMs: number;
  bpm: number | null;
  isMock: boolean;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
  onCommitBpm: (bpm: number) => void;
}

export function RecordingControls({ phase, elapsedMs, bpm, isMock, disabled, onStart, onStop, onCommitBpm }: RecordingControlsProps) {
  const [localBpm, setLocalBpm] = useState<number | null>(null);
  const displayBpm = Math.min(100, Math.max(60, Math.round(localBpm ?? bpm ?? 75)));
  const recording = phase === "recording";
  const processing = phase === "processing";
  const progress = Math.min(100, elapsedMs / RECORD_DURATION_MS * 100);

  return (
    <section className="auris-controls" aria-labelledby="record-heading">
      <div className="auris-section-heading"><h2 id="record-heading">Sesi rekaman</h2><span>10 detik</span></div>
      <p className="auris-timer">{formatElapsedMs(elapsedMs)}<small> / 0:10,0</small></p>
      <progress className="auris-progress" value={progress} max={100} aria-label="Progres rekaman" />
      <button type="button" className="auris-record-button" data-recording={recording}
        onClick={recording ? onStop : onStart} disabled={!recording && (disabled || processing)}>
        <span className={recording ? "auris-stop-icon" : "auris-record-icon"} aria-hidden="true" />
        {recording ? "Hentikan rekaman" : processing ? "Menyiapkan hasil…" : "Mulai rekaman"}
      </button>
      <p className="auris-control-note">{disabled ? "Hubungkan perangkat untuk memulai." : "Sesi berhenti otomatis setelah 10 detik."}</p>
      {isMock && <div className="auris-simulator-control">
        <div className="auris-section-heading"><label htmlFor="bpm-slider">Denyut simulator</label><span>{displayBpm} BPM</span></div>
        <Slider id="bpm-slider" min={60} max={100} step={1} value={[displayBpm]}
          onValueChange={(values) => setLocalBpm(values[0])}
          onValueCommit={(values) => { onCommitBpm(values[0]); setLocalBpm(null); }}
          disabled={disabled || recording || processing} aria-label="Atur BPM simulator" />
        <div className="auris-slider-range"><span>60</span><span>100</span></div>
      </div>}
    </section>
  );
}
