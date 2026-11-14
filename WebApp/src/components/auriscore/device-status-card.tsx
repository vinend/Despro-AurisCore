import { HeartPulse, Radio, Battery, MapPin } from "lucide-react";
import { ORGAN_MODE_LABELS, QUALITY_LABELS } from "@/lib/auriscore/format";
import type { DeviceStatusMsg, OrganMode } from "@/lib/auriscore/protocol";
import type { SignalMetrics } from "@/lib/auriscore/signal-meter";

export function DeviceStatusCard({
  status,
  organMode,
  connected,
  analysisMode = "heart",
  hardware = false,
  signalMetrics = null,
  gatewayRttMs = null,
  analysisLatencyMs = null,
}: {
  status: DeviceStatusMsg | null;
  organMode: OrganMode;
  connected: boolean;
  analysisMode?: "heart" | "abdomen" | "lung";
  hardware?: boolean;
  signalMetrics?: SignalMetrics | null;
  gatewayRttMs?: number | null;
  analysisLatencyMs?: number | null;
}) {
  const bpmValue = connected && status ? Math.round(status.bpm) : null;
  const quality = connected && status ? status.signalQuality : null;
  const battery = connected && status ? Math.round(status.batteryPercent) : null;

  return (
    <dl className="auris-status-strip" aria-label="Status perangkat">
      {analysisMode === "heart" && (
        <div className="auris-status-card">
          <dt>
            <HeartPulse className="w-3.5 h-3.5 text-emerald-600 animate-pulse" />
            <span>Denyut perangkat</span>
          </dt>
          <dd>
            <span>{bpmValue != null ? bpmValue : "—"}</span>
            <small> BPM</small>
          </dd>
        </div>
      )}

      <div className="auris-status-card">
        <dt>
          <Radio className="w-3.5 h-3.5 text-emerald-600" />
          <span>Kualitas sinyal</span>
        </dt>
        <dd
          className="auris-quality"
          data-quality={quality ?? undefined}
        >
          <span className="text-base">{hardware
            ? connected && signalMetrics
              ? signalMetrics.rmsDbfs === null ? "Sinyal nol" : "Audio masuk"
              : "Menunggu audio"
            : quality ? QUALITY_LABELS[quality] : "—"}</span>
        </dd>
        {hardware && connected && signalMetrics && <p className="text-xs text-muted-foreground mt-1">
          RMS {signalMetrics.rmsDbfs === null ? "−∞" : signalMetrics.rmsDbfs.toFixed(1)} dBFS
          {" · "}Saturasi {(signalMetrics.clippedFraction * 100).toFixed(2)}%
          <span className="block">PCM diterima · jendela ≤1 detik; bukan ukuran SNR.</span>
        </p>}
      </div>

      <div className="auris-status-card">
        <dt>
          <Battery className="w-3.5 h-3.5 text-emerald-600" />
          <span>Baterai</span>
        </dt>
        <dd>
          <span>{battery != null ? `${battery}%` : "—"}</span>
        </dd>
      </div>

      {analysisMode === "heart" && !hardware && (
        <div className="auris-status-card">
          <dt>
            <MapPin className="w-3.5 h-3.5 text-emerald-600" />
            <span>Lokasi aktif</span>
          </dt>
          <dd>
            <span className="truncate text-base sm:text-lg">{ORGAN_MODE_LABELS[organMode]}</span>
          </dd>
        </div>
      )}
      {hardware && <>
        <div className="auris-status-card">
          <dt>Respons gateway</dt>
          <dd><span>{gatewayRttMs === null ? "—" : gatewayRttMs.toFixed(1)}</span><small>ms</small></dd>
          <p className="text-xs text-muted-foreground mt-1">Pulang-pergi browser ↔ gateway. Bukan latensi mic.</p>
        </div>
        <div className="auris-status-card">
          <dt>Waktu analisis</dt>
          <dd><span>{analysisLatencyMs === null ? "—" : analysisLatencyMs}</span><small>ms</small></dd>
          <p className="text-xs text-muted-foreground mt-1">{analysisLatencyMs === null
            ? "Mulai prediksi langsung untuk mengukur."
            : "Kirim jendela → hasil diterima; waktu pengumpulan audio terpisah."}</p>
        </div>
      </>}
    </dl>
  );
}
