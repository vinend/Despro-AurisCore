"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Slider } from "@/components/ui/slider";
import { Circle, Loader2, Square } from "lucide-react";

import { RECORD_DURATION_MS, type RecordingPhase } from "@/hooks/use-recording";
import { formatElapsedMs } from "@/lib/auriscore/format";

interface RecordingControlsProps {
  phase: RecordingPhase;
  elapsedMs: number;
  bpm: number | null;
  /** true saat koneksi terputus → kontrol dimatikan (dicatat di DECISIONS.md). */
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
  onCommitBpm: (bpm: number) => void;
}

function clampBpm(v: number): number {
  return Math.min(100, Math.max(60, Math.round(v)));
}

/**
 * Kontrol (seksi 9): tombol Rekam/Berhenti + timer durasi + slider BPM 60–100.
 * Slider mengirim set_bpm saat commit (bukan tiap geseran) — dicatat di
 * DECISIONS.md.
 */
export function RecordingControls({
  phase,
  elapsedMs,
  bpm,
  disabled,
  onStart,
  onStop,
  onCommitBpm,
}: RecordingControlsProps) {
  const [localBpm, setLocalBpm] = useState<number | null>(null);
  const displayBpm = clampBpm(localBpm ?? bpm ?? 75);

  // localBpm hanya hidup selama geseran slider berlangsung (onValueChange →
  // onValueCommit). Setelah commit, nilai tampil mengikuti bpmDraft di hook
  // (langsung diset oleh commitBpm) — tanpa efek sinkron tambahan.

  const recording = phase === "recording";
  const processing = phase === "processing";
  const progressValue = recording
    ? Math.min(100, (elapsedMs / RECORD_DURATION_MS) * 100)
    : phase === "idle"
      ? 0
      : 100;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Rekam & kontrol simulasi</CardTitle>
        <CardDescription>
          Sesi rekaman 10 detik berhenti otomatis, lalu diproses 1,5 detik.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            {recording ? (
              <Button
                size="lg"
                onClick={onStop}
                className="bg-rose-600 text-white shadow-xs hover:bg-rose-700"
                aria-label="Berhenti merekam sekarang"
              >
                <Square className="fill-current" />
                Berhenti
              </Button>
            ) : (
              <Button
                size="lg"
                onClick={onStart}
                disabled={disabled || processing}
                aria-label="Mulai merekam selama 10 detik"
              >
                <Circle className="fill-current text-rose-500" />
                Rekam 10 dtk
              </Button>
            )}
            <div className="flex min-w-0 flex-1 items-center gap-2 text-sm text-muted-foreground">
              {processing ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="size-4 animate-spin" />
                  Memproses…
                </span>
              ) : (
                <span className="font-mono tabular-nums">
                  {formatElapsedMs(elapsedMs)}
                  <span className="text-muted-foreground/70">
                    {" / "}
                    {formatElapsedMs(RECORD_DURATION_MS)}
                  </span>
                </span>
              )}
            </div>
            {recording && (
              <Badge className="gap-1.5 border-rose-200 bg-rose-100 text-rose-700 hover:bg-rose-100">
                <span className="size-1.5 animate-pulse rounded-full bg-rose-500" />
                merekam
              </Badge>
            )}
          </div>
          <Progress value={progressValue} aria-label="Progres rekaman" />
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <Label htmlFor="bpm-slider" className="text-sm font-medium">
              BPM{" "}
              <span className="font-normal text-muted-foreground">
                (kontrol simulasi)
              </span>
            </Label>
            <Badge variant="secondary" className="tabular-nums">
              {displayBpm} BPM
            </Badge>
          </div>
          <Slider
            id="bpm-slider"
            min={60}
            max={100}
            step={1}
            value={[displayBpm]}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === "number") setLocalBpm(next);
            }}
            onValueCommit={(values) => {
              const next = values[0];
              if (typeof next === "number") {
                onCommitBpm(next);
                setLocalBpm(null);
              }
            }}
            disabled={disabled}
            aria-label="Atur BPM perangkat"
          />
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="tabular-nums">60</span>
            <span className="hidden sm:inline">
              rentang 60–100 · berlaku mulai beat berikutnya
            </span>
            <span className="tabular-nums">100</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
