"use client";

import { useState } from "react";
import { Clock, Sliders, Play, Square, Loader2 } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { RECORD_DURATION_MS, type RecordingPhase } from "@/hooks/use-recording";
import { formatElapsedMs } from "@/lib/auriscore/format";

interface RecordingControlsProps {
  phase: RecordingPhase;
  elapsedMs: number;
  durationMs?: number;
  bpm: number | null;
  isMock: boolean;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
  onCommitBpm: (bpm: number) => void;
}

export function RecordingControls({
  phase,
  elapsedMs,
  durationMs = RECORD_DURATION_MS,
  bpm,
  isMock,
  disabled,
  onStart,
  onStop,
  onCommitBpm,
}: RecordingControlsProps) {
  const [localBpm, setLocalBpm] = useState<number | null>(null);
  const displayBpm = Math.min(100, Math.max(60, Math.round(localBpm ?? bpm ?? 75)));
  const recording = phase === "recording";
  const processing = phase === "processing";
  const progress = Math.min(100, (elapsedMs / durationMs) * 100);

  return (
    <section className="auris-controls border-b border-border/60" aria-labelledby="record-heading">
      <div className="auris-section-heading">
        <h2 id="record-heading" className="flex items-center gap-1.5">
          <Clock className="w-4 h-4 text-emerald-600" />
          <span>Sesi Rekaman</span>
        </h2>
        <span>{durationMs / 1000} detik</span>
      </div>

      <div className="flex items-baseline justify-between">
        <p className="auris-timer">
          {formatElapsedMs(elapsedMs)}
          <small> / {formatElapsedMs(durationMs)}</small>
        </p>
        {recording && (
          <span className="flex items-center gap-1.5 text-xs font-semibold text-rose-600 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
            Merekam
          </span>
        )}
      </div>

      <progress
        className="auris-progress"
        value={progress}
        max={100}
        aria-label="Progres rekaman"
      />

      <button
        type="button"
        className="auris-record-button"
        data-recording={recording}
        onClick={recording ? onStop : onStart}
        disabled={!recording && (disabled || processing)}
      >
        {processing ? (
          <Loader2 className="w-4 h-4 animate-spin text-white" />
        ) : recording ? (
          <Square className="w-4 h-4 fill-white text-white" />
        ) : (
          <Play className="w-4 h-4 fill-white text-white" />
        )}
        <span>
          {recording
            ? "Hentikan Rekaman"
            : processing
            ? "Menyiapkan Hasil…"
            : "Mulai Rekaman"}
        </span>
      </button>

      <p className="auris-control-note">
        {disabled
          ? "Hubungkan perangkat untuk memulai."
          : `Sesi berhenti otomatis setelah ${durationMs / 1000} detik.`}
      </p>

      {isMock && (
        <div className="auris-simulator-control">
          <div className="auris-section-heading">
            <label htmlFor="bpm-slider" className="flex items-center gap-1.5 cursor-pointer">
              <Sliders className="w-3.5 h-3.5 text-emerald-600" />
              <span>Denyut simulator</span>
            </label>
            <span className="font-semibold text-emerald-950">{displayBpm} BPM</span>
          </div>
          <Slider
            id="bpm-slider"
            min={60}
            max={100}
            step={1}
            value={[displayBpm]}
            onValueChange={(values) => setLocalBpm(values[0])}
            onValueCommit={(values) => {
              onCommitBpm(values[0]);
              setLocalBpm(null);
            }}
            disabled={disabled || recording || processing}
            aria-label="Atur BPM simulator"
          />
          <div className="auris-slider-range">
            <span>60 BPM</span>
            <span>100 BPM</span>
          </div>
        </div>
      )}
    </section>
  );
}
