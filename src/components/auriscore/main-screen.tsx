"use client";

import { Card } from "@/components/ui/card";
import { Stethoscope, Waves } from "lucide-react";

import { ConnectionBadge } from "./connection-badge";
import { DeviceStatusCard } from "./device-status-card";
import { HistoryList } from "./history-list";
import { OrganModeSelector } from "./organ-mode-selector";
import { PcgWaveform } from "./pcg-waveform";
import { RecordingControls } from "./recording-controls";
import { ResultCard } from "./result-card";
import { usePcgStream } from "@/hooks/use-pcg-stream";
import { useRecording } from "@/hooks/use-recording";
import { ORGAN_MODE_LABELS } from "@/lib/auriscore/format";

/**
 * Layar utama (seksi 9), atas ke bawah dan responsif untuk ponsel:
 * header + badge koneksi → kartu status perangkat → pemilih mode organ →
 * area gelombang → kontrol (rekam, timer, slider BPM) → kartu hasil →
 * riwayat → footer.
 */
export function MainScreen() {
  const stream = usePcgStream();
  const recording = useRecording();

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-teal-600/10 text-teal-600">
              <Stethoscope className="size-5" />
            </div>
            <div className="min-w-0">
              <h1 className="text-base font-semibold leading-tight">
                AurisCore
              </h1>
              <p className="truncate text-xs text-muted-foreground">
                Stetoskop digital · prototipe data simulasi
              </p>
            </div>
          </div>
          <ConnectionBadge state={stream.state} isMock={stream.isMock} />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 px-4 py-4 pb-8 sm:gap-5 sm:py-6">
        <DeviceStatusCard
          status={stream.status}
          organMode={stream.organMode}
          connected={stream.isConnected}
        />

        <OrganModeSelector
          value={stream.organMode}
          onChange={stream.setOrganMode}
          disabled={!stream.isConnected}
        />

        <Card className="gap-0 overflow-hidden py-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-4 py-2.5">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Waves className="size-4 text-teal-600" />
              Gelombang PCG
              <span className="font-normal text-muted-foreground">
                · {ORGAN_MODE_LABELS[stream.organMode]}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground tabular-nums">
              <span>jendela 5 dtk</span>
              <span className="hidden sm:inline">
                · {stream.hello?.samplingRate ?? 2000} Hz · int16
              </span>
            </div>
          </div>
          <div className="h-[280px] sm:h-[340px] lg:h-[400px]">
            <PcgWaveform buffer={stream.ring} versionRef={stream.versionRef} />
          </div>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <RecordingControls
            phase={recording.phase}
            elapsedMs={recording.elapsedMs}
            bpm={stream.bpm}
            disabled={!stream.isConnected}
            onStart={() => recording.start(stream.organMode)}
            onStop={recording.stop}
            onCommitBpm={stream.commitBpm}
          />
          <ResultCard phase={recording.phase} result={recording.result} />
        </div>

        <HistoryList entries={recording.history} />
      </main>

      <footer className="mt-auto border-t bg-muted/40">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-1 px-4 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:gap-4">
          <span>
            AurisCore · prototipe pekan 3 · seluruh data PCG dan hasil
            klasifikasi adalah{" "}
            <strong className="font-semibold">simulasi</strong> — bukan alat
            medis.
          </span>
          <span className="shrink-0 tabular-nums">
            {stream.hello
              ? `${stream.hello.device} · fw ${stream.hello.fw} · ${stream.hello.samplingRate} Hz · ${stream.hello.channels} kanal`
              : "perangkat tidak terhubung"}
          </span>
        </div>
      </footer>
    </div>
  );
}
