import { HeartPulse, Radio, Battery, MapPin } from "lucide-react";
import { ORGAN_MODE_LABELS, QUALITY_LABELS } from "@/lib/auriscore/format";
import type { DeviceStatusMsg, OrganMode } from "@/lib/auriscore/protocol";

export function DeviceStatusCard({
  status,
  organMode,
  connected,
  analysisMode = "heart",
  hardware = false,
}: {
  status: DeviceStatusMsg | null;
  organMode: OrganMode;
  connected: boolean;
  analysisMode?: "heart" | "abdomen" | "lung";
  hardware?: boolean;
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
          {quality ? QUALITY_LABELS[quality] : "—"}
        </dd>
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
    </dl>
  );
}
