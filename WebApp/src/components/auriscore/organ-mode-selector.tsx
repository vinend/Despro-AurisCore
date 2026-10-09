"use client";

import { ORGAN_MODE_LABELS } from "@/lib/auriscore/format";
import { ORGAN_MODES, type OrganMode } from "@/lib/auriscore/protocol";

export function OrganModeSelector({ value, onChange, disabled }: {
  value: OrganMode; onChange: (mode: OrganMode) => void; disabled?: boolean;
}) {
  return (
    <div className="auris-locations" role="group" aria-label="Lokasi auskultasi">
      {ORGAN_MODES.map((mode, index) => (
        <button key={mode} type="button" disabled={disabled} aria-pressed={value === mode} onClick={() => onChange(mode)}>
          <span className="auris-small-mono">0{index + 1}</span>{ORGAN_MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  );
}
