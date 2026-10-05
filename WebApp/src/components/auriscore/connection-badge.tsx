import type { PcgConnectionState } from "@/lib/auriscore/pcg-connection";

export function ConnectionBadge({ state, isMock }: { state: PcgConnectionState; isMock: boolean }) {
  const label = state === "connected" ? (isMock ? "Simulator terhubung" : "Perangkat terhubung")
    : state === "connecting" ? "Menyambung…" : "Terputus";
  return <span className="auris-connection" data-state={state} role="status"><span aria-hidden="true" />{label}</span>;
}
