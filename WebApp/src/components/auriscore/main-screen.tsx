"use client";

import { useState, type ReactNode } from "react";
import { ConnectionBadge } from "./connection-badge";
import { DeviceStatusCard } from "./device-status-card";
import { HistoryList } from "./history-list";
import { OrganModeSelector } from "./organ-mode-selector";
import { PcgWaveform } from "./pcg-waveform";
import { RecordingControls } from "./recording-controls";
import { ResultCard } from "./result-card";
import { OrganFileAnalysis } from "./organ-file-analysis";
import type { AnalysisMode } from "@/lib/auriscore/analysis-result";
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
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("heart");
  const [uploadBusy, setUploadBusy] = useState(false);
  const recording = useRecording(stream, analysisMode);
  const recordingBusy = recording.phase === "recording" || recording.phase === "processing";
  const busy = recordingBusy || uploadBusy;

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
            <h1>Pantau suara tubuh.</h1>
            <p>Pilih organ, amati sinyal, lalu rekam atau unggah audio.</p>
          </div>
          <span className="auris-session-label">AUDIO / {stream.isMock ? "SIMULATOR" : stream.isConnected ? "PERANGKAT" : "TERPUTUS"}</span>
        </div>
        <label htmlFor="analysis-mode">Organ analisis </label>
        <select id="analysis-mode" value={analysisMode} disabled={busy} onChange={event => {
          recording.reset(); setAnalysisMode(event.target.value as AnalysisMode);
        }}><option value="heart">Heart</option><option value="abdomen">Abdomen</option></select>
        <DeviceStatusCard status={stream.status} organMode={stream.organMode} connected={stream.isConnected} analysisMode={analysisMode} />
        <div className="auris-console">
          <section className="auris-signal-panel" aria-labelledby="signal-heading">
            <div className="auris-panel-heading">
              <div><p className="auris-eyebrow">SINYAL LANGSUNG</p><h2 id="signal-heading">{analysisMode === "heart" ? "Fonokardiogram" : "Audio abdomen"}</h2></div>
              <span className="auris-small-mono">{stream.hello?.samplingRate ?? EXPECTED_SAMPLING_RATE} Hz · mono</span>
            </div>
            {analysisMode === "heart" && <OrganModeSelector value={stream.organMode} onChange={stream.setOrganMode} disabled={!stream.isConnected || busy} />}
            <div className="auris-scope-heading">
              <span>{analysisMode === "heart" ? ORGAN_MODE_LABELS[stream.organMode] : "Abdomen · gunakan sumber audio yang sesuai"}</span>
              <span>{stream.isConnected ? "Streaming" : "Menunggu koneksi"}</span>
            </div>
            <div className="auris-scope-canvas"><PcgWaveform buffer={stream.ring} versionRef={stream.versionRef} /></div>
            <div className="auris-time-axis" aria-hidden="true">
              <span>−5 s</span><span>−4</span><span>−3</span><span>−2</span><span>−1</span><span>0 s</span>
            </div>
            <p className="auris-signal-caption">{stream.isMock ? "Sinyal sintetis dari simulator perangkat." : stream.isConnected ? "Sinyal dari perangkat yang terhubung." : "Menunggu sumber audio."} Jendela bergulir 5 detik.</p>
          </section>
          <aside className="auris-side-panel" aria-label="Kontrol dan hasil sesi">
            <RecordingControls phase={recording.phase} elapsedMs={recording.elapsedMs} bpm={stream.bpm} isMock={stream.isMock && analysisMode === "heart"}
              disabled={!stream.isConnected || uploadBusy} onStart={recording.start}
              onStop={recording.stop} onCommitBpm={stream.commitBpm} />
            <ResultCard phase={recording.phase} result={recording.result} error={recording.error} file={recording.file} />
          </aside>
        </div>
        <OrganFileAnalysis key={analysisMode} mode={analysisMode} onBusy={setUploadBusy} disabled={recordingBusy} />
        {analysisMode === "heart" && trainingMetricsCard}
        <HistoryList entries={recording.history} />
      </main>
      <footer className="auris-footer">
        <p>Prototipe penelitian. {stream.isMock ? "Audio simulator untuk uji rekayasa." : "Analisis memakai audio yang diterima."} Keluaran skrining bukan diagnosis.</p>
        <span>{stream.hello ? `${stream.hello.device} · ${stream.hello.fw}` : "Perangkat belum terhubung"}</span>
      </footer>
    </div>
  );
}
