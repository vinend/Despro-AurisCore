"use client";

import type { ReactNode } from "react";
import { ConnectionBadge } from "./connection-badge";
import { DeviceStatusCard } from "./device-status-card";
import { HistoryList } from "./history-list";
import { OrganModeSelector } from "./organ-mode-selector";
import { PcgWaveform } from "./pcg-waveform";
import { RecordingControls } from "./recording-controls";
import { ResultCard } from "./result-card";
import { HeartFileDemo } from "./heart-file-demo";
import { HeartStreamDemo } from "./heart-stream-demo";
import { usePcgStream } from "@/hooks/use-pcg-stream";
import { useRecording } from "@/hooks/use-recording";
import { ORGAN_MODE_LABELS } from "@/lib/auriscore/format";
import { EXPECTED_SAMPLING_RATE } from "@/lib/auriscore/protocol";

/**
 * Layar utama (seksi 9), atas ke bawah dan responsif untuk ponsel:
 * header + badge koneksi → kartu status perangkat → pemilih mode organ →
 * area gelombang → kontrol (rekam, timer, slider BPM) → kartu hasil →
 * riwayat → footer.
 */
export function MainScreen({
  trainingMetricsCard,
}: {
  trainingMetricsCard: ReactNode;
}) {
  const stream = usePcgStream();
  const recording = useRecording();
  const busy = recording.phase === "recording" || recording.phase === "processing";

  return (
    <div className="auris-workspace">
      <header className="auris-header">
        <div className="auris-header-inner">
          <a href="/" className="auris-wordmark" aria-label="AurisCore beranda">
            <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
              <path d="M2 17h5l3-9 5 17 5-20 4 12h6" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            </svg>
            AurisCore<span className="auris-wordmark-divider" />
            <span className="auris-product-label">Stetoskop digital</span>
          </a>
          <ConnectionBadge state={stream.state} isMock={stream.isMock} />
        </div>
      </header>
      <main className="auris-main">
        <div className="auris-page-heading">
          <div>
            <p className="auris-eyebrow">RUANG AUSKULTASI</p>
            <h1>Pantau suara jantung.</h1>
            <p>Pilih lokasi, amati sinyal, lalu mulai sesi rekaman.</p>
          </div>
          <span className="auris-session-label">PCG / {stream.isMock ? "DEMO" : "PERANGKAT"}</span>
        </div>
        <DeviceStatusCard status={stream.status} organMode={stream.organMode} connected={stream.isConnected} />
        <div className="auris-console">
          <section className="auris-signal-panel" aria-labelledby="signal-heading">
            <div className="auris-panel-heading">
              <div><p className="auris-eyebrow">SINYAL LANGSUNG</p><h2 id="signal-heading">Fonokardiogram</h2></div>
              <span className="auris-small-mono">{stream.hello?.samplingRate ?? EXPECTED_SAMPLING_RATE} Hz · mono</span>
            </div>
            <OrganModeSelector value={stream.organMode} onChange={stream.setOrganMode} disabled={!stream.isConnected || busy} />
            <div className="auris-scope-heading">
              <span>{ORGAN_MODE_LABELS[stream.organMode]}</span>
              <span>{stream.isConnected ? "Streaming" : "Menunggu koneksi"}</span>
            </div>
            <div className="auris-scope-canvas"><PcgWaveform buffer={stream.ring} versionRef={stream.versionRef} /></div>
            <div className="auris-time-axis" aria-hidden="true">
              <span>−5 s</span><span>−4</span><span>−3</span><span>−2</span><span>−1</span><span>0 s</span>
            </div>
            <p className="auris-signal-caption">{stream.isMock ? "Sinyal sintetis dari simulator perangkat." : "Sinyal dari perangkat yang terhubung."} Jendela bergulir 5 detik.</p>
          </section>
          <aside className="auris-side-panel" aria-label="Kontrol dan hasil sesi">
            <RecordingControls phase={recording.phase} elapsedMs={recording.elapsedMs} bpm={stream.bpm} isMock={stream.isMock}
              disabled={!stream.isConnected} onStart={() => recording.start(stream.organMode)}
              onStop={recording.stop} onCommitBpm={stream.commitBpm} />
            <ResultCard phase={recording.phase} result={recording.result} />
          </aside>
        </div>
        <HeartFileDemo />
        <HeartStreamDemo stream={stream} disabled={busy} />
        {trainingMetricsCard}
        <HistoryList entries={recording.history} />
      </main>
      <footer className="auris-footer">
        <p>Prototipe penelitian. Stream perangkat simulasi; analisis WAV memakai DSP prototipe.</p>
        <span>{stream.hello ? `${stream.hello.device} · ${stream.hello.fw}` : "Perangkat belum terhubung"}</span>
      </footer>
    </div>
  );
}
