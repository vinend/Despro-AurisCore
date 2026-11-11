"use client";

import { useState, type ReactNode } from "react";
import { HeartPulse, Wind, Activity, Stethoscope, Radio, AlertCircle } from "lucide-react";
import { ConnectionBadge } from "./connection-badge";
import { DeviceStatusCard } from "./device-status-card";
import { HistoryList } from "./history-list";
import { OrganModeSelector } from "./organ-mode-selector";
import { PcgWaveform } from "./pcg-waveform";
import { RecordingControls } from "./recording-controls";
import { ResultCard } from "./result-card";
import { DeviceConnect, type StreamSettings } from "./device-connect";
import { LiveListening } from "./live-listening";
import { OrganFileAnalysis } from "./organ-file-analysis";
import type { AnalysisMode } from "@/lib/auriscore/analysis-result";
import { usePcgStream } from "@/hooks/use-pcg-stream";
import { useRecording } from "@/hooks/use-recording";
import { ORGAN_MODE_LABELS } from "@/lib/auriscore/format";
import { EXPECTED_SAMPLING_RATE } from "@/lib/auriscore/protocol";

/**
 * Layar utama responsif untuk ponsel & desktop:
 * header + badge koneksi → kartu status perangkat → pemilih mode organ →
 * area gelombang → kontrol (rekam, timer, slider BPM) → kartu hasil →
 * riwayat → footer.
 */
export function MainScreen({
  trainingMetricsCard,
}: {
  trainingMetricsCard: ReactNode;
}) {
  const [settings, setSettings] = useState<StreamSettings>({
    source: "mock",
    url: "",
    token: "",
  });
  const stream = usePcgStream(settings);
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>("heart");
  const [uploadBusy, setUploadBusy] = useState(false);
  const recording = useRecording(stream, analysisMode);
  const recordingBusy =
    recording.phase === "recording" || recording.phase === "processing";
  const busy = recordingBusy || uploadBusy;

  const organModes: { id: AnalysisMode; label: string; icon: typeof HeartPulse; desc: string }[] = [
    { id: "heart", label: "Heart", icon: HeartPulse, desc: "Jantung & PCG" },
    { id: "lung", label: "Lung", icon: Wind, desc: "Suara Paru" },
    { id: "abdomen", label: "Abdomen", icon: Activity, desc: "Suara Perut" },
  ];

  return (
    <div className="auris-workspace">
      {/* App Bar / Header */}
      <header className="auris-header">
        <div className="auris-header-inner">
          <a href="/" className="auris-wordmark" aria-label="AurisCore beranda">
            <div className="auris-wordmark-icon-wrap" aria-hidden="true">
              <svg viewBox="0 0 32 32" fill="none" className="stroke-current">
                <path
                  d="M3 17h4l3-8 5 15 5-18 4 11h5"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <span className="text-base sm:text-lg tracking-tight">AurisCore</span>
            <span className="auris-wordmark-divider" />
            <span className="auris-product-label">Stetoskop Digital</span>
          </a>

          <ConnectionBadge state={stream.state} isMock={stream.isMock} />
        </div>
      </header>

      {/* Main Container */}
      <main className="auris-main">
        {/* Page Heading */}
        <div className="auris-page-heading">
          <div>
            <p className="auris-eyebrow">
              <Stethoscope className="w-3.5 h-3.5" />
              Ruang Auskultasi
            </p>
            <h1>Pantau suara tubuh.</h1>
            <p>Pilih organ, amati sinyal real-time, lalu rekam atau unggah audio.</p>
          </div>
          <span className="auris-session-label">
            AUDIO / {stream.isMock ? "SIMULATOR" : stream.isConnected ? "PERANGKAT" : "TERPUTUS"}
          </span>
        </div>

        {/* Device Connection Settings Card */}
        <DeviceConnect
          disabled={busy}
          onConnect={(next) => {
            recording.reset();
            setSettings(next);
          }}
        />

        {stream.error && (
          <div role="alert" className="flex items-center gap-2 p-3 bg-rose-50 text-rose-800 text-xs rounded-xl border border-rose-200">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{stream.error}</span>
          </div>
        )}

        {/* Organ Mode Switcher (Modern Segmented Control) */}
        <div className="space-y-2">
          {/* Accessible label and fallback select */}
          <label htmlFor="analysis-mode" className="sr-only">
            Organ analisis
          </label>
          <select
            id="analysis-mode"
            value={analysisMode}
            disabled={busy}
            onChange={(event) => {
              recording.reset();
              setAnalysisMode(event.target.value as AnalysisMode);
            }}
            className="sr-only"
          >
            <option value="heart">Heart</option>
            <option value="abdomen">Abdomen</option>
            <option value="lung">Lung</option>
          </select>

          {/* Visual Mobile-First Segmented Pill Tabs */}
          <div className="auris-organ-tabs" role="tablist" aria-label="Pilih organ analisis">
            {organModes.map((item) => {
              const Icon = item.icon;
              const isSelected = analysisMode === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  disabled={busy}
                  onClick={() => {
                    recording.reset();
                    setAnalysisMode(item.id);
                  }}
                  className="auris-organ-tab"
                >
                  <Icon className={`w-4 h-4 ${isSelected ? "text-emerald-700" : "text-muted-foreground"}`} />
                  <div className="flex flex-col text-left leading-tight">
                    <span className="font-semibold">{item.label}</span>
                    <span className="hidden sm:inline text-[10px] text-muted-foreground font-normal">
                      {item.desc}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Device Status Strip (Micro-Cards) */}
        <DeviceStatusCard
          status={stream.status}
          organMode={stream.organMode}
          connected={stream.isConnected}
          analysisMode={analysisMode}
          hardware={stream.isHardware}
        />

        {/* Live Audio Oscilloscope Console & Side Panel */}
        <div className="auris-console">
          {/* Signal Oscilloscope Panel */}
          <section className="auris-signal-panel" aria-labelledby="signal-heading">
            <div className="auris-panel-heading">
              <div>
                <p className="auris-eyebrow">
                  <Radio className="w-3 h-3 text-emerald-600 animate-pulse" />
                  Sinyal Langsung
                </p>
                <h2 id="signal-heading">
                  {analysisMode === "heart"
                    ? "Fonokardiogram (PCG)"
                    : analysisMode === "lung"
                    ? "Audio Paru (Respirasi)"
                    : "Audio Abdomen (Bowel)"}
                </h2>
              </div>
              <span className="auris-small-mono bg-muted/70 px-2 py-0.5 rounded text-[11px]">
                {stream.hello?.samplingRate ?? EXPECTED_SAMPLING_RATE} Hz · mono
              </span>
            </div>

            {analysisMode === "heart" && !stream.isHardware && (
              <OrganModeSelector
                value={stream.organMode}
                onChange={stream.setOrganMode}
                disabled={!stream.isConnected || busy}
              />
            )}

            <div className="auris-scope-heading">
              <span className="truncate">
                {analysisMode === "heart"
                  ? stream.isHardware
                    ? "Heart · audio perangkat fisik"
                    : ORGAN_MODE_LABELS[stream.organMode]
                  : `${analysisMode === "lung" ? "Lung" : "Abdomen"} · gunakan sumber audio yang sesuai`}
              </span>
              <span>
                {stream.isConnected ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping inline-block" />
                    Streaming
                  </>
                ) : (
                  "Menunggu koneksi"
                )}
              </span>
            </div>

            <div className="auris-scope-canvas">
              <PcgWaveform buffer={stream.ring} versionRef={stream.versionRef} />
            </div>

            <div className="auris-time-axis" aria-hidden="true">
              <span>−5 s</span>
              <span>−4 s</span>
              <span>−3 s</span>
              <span>−2 s</span>
              <span>−1 s</span>
              <span>0 s (Kini)</span>
            </div>

            <p className="auris-signal-caption">
              {stream.isMock
                ? "Sinyal sintetis dari simulator perangkat."
                : stream.isConnected
                ? "Sinyal dari perangkat yang terhubung."
                : "Menunggu sumber audio."}{" "}
              Jendela bergulir 5 detik.
            </p>
          </section>

          {/* Controls & Result Dock */}
          <aside className="auris-side-panel" aria-label="Kontrol dan hasil sesi">
            <LiveListening stream={stream} />
            <RecordingControls
              phase={recording.phase}
              elapsedMs={recording.elapsedMs}
              bpm={stream.bpm}
              isMock={!stream.isHardware && stream.isMock && analysisMode === "heart"}
              durationMs={recording.durationMs}
              disabled={!stream.isConnected || uploadBusy}
              onStart={recording.start}
              onStop={recording.stop}
              onCommitBpm={stream.commitBpm}
            />
            <ResultCard
              phase={recording.phase}
              result={recording.result}
              error={recording.error}
              file={recording.file}
            />
          </aside>
        </div>

        {/* WAV File Upload & Offline Analysis */}
        <OrganFileAnalysis
          key={analysisMode}
          mode={analysisMode}
          onBusy={setUploadBusy}
          disabled={recordingBusy}
        />

        {/* Model Training Metrics Card (Shown for Heart mode) */}
        {analysisMode === "heart" && trainingMetricsCard}

        {/* Session History List */}
        <HistoryList entries={recording.history} />
      </main>

      {/* Footer */}
      <footer className="auris-footer">
        <p>
          Prototipe penelitian.{" "}
          {stream.isMock
            ? "Audio simulator untuk uji rekayasa."
            : "Analisis memakai audio yang diterima."}{" "}
          Keluaran skrining bukan diagnosis.
        </p>
        <span className="font-mono text-xs">
          {stream.hello
            ? `${stream.hello.device} · ${stream.hello.fw}`
            : "Perangkat belum terhubung"}
        </span>
      </footer>
    </div>
  );
}
