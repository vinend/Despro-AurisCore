import { ORGAN_MODE_LABELS, QUALITY_LABELS } from "@/lib/auriscore/format";
import type { DeviceStatusMsg, OrganMode } from "@/lib/auriscore/protocol";

export function DeviceStatusCard({ status, organMode, connected, analysisMode = "heart" }: {
  status: DeviceStatusMsg | null; organMode: OrganMode; connected: boolean; analysisMode?: "heart" | "abdomen";
}) {
  return (
    <dl className="auris-status-strip" aria-label="Status perangkat">
      {analysisMode === "heart" && <div><dt>Denyut perangkat</dt><dd>{connected && status ? Math.round(status.bpm) : "—"}<small> BPM</small></dd></div>}
      <div><dt>Kualitas sinyal</dt><dd className="auris-quality" data-quality={connected ? status?.signalQuality : undefined}>
        {connected && status ? QUALITY_LABELS[status.signalQuality] : "—"}</dd></div>
      <div><dt>Baterai</dt><dd>{connected && status ? `${Math.round(status.batteryPercent)}%` : "—"}</dd></div>
      {analysisMode === "heart" && <div><dt>Lokasi aktif</dt><dd>{ORGAN_MODE_LABELS[organMode]}</dd></div>}
    </dl>
  );
}
