"use client";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { ORGAN_MODE_LABELS } from "@/lib/auriscore/format";
import { ORGAN_MODES, type OrganMode } from "@/lib/auriscore/protocol";

interface OrganModeSelectorProps {
  value: OrganMode;
  onChange: (mode: OrganMode) => void;
  disabled?: boolean;
}

/**
 * Segmented control empat mode organ (seksi 9). Perubahan mengirim set_mode;
 * label diperbarui setelah mode_ack (atau paket berikutnya) diterima.
 */
export function OrganModeSelector({
  value,
  onChange,
  disabled,
}: OrganModeSelectorProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">Mode organ auskultasi</span>
        <span className="text-xs text-muted-foreground">
          buffer gelombang direset setelah mode_ack
        </span>
      </div>
      <ToggleGroup
        type="single"
        value={value}
        onValueChange={(next) => {
          // Klik item yang sedang aktif menghasilkan nilai "" → abaikan
          // (selalu harus ada satu mode aktif).
          if (next) onChange(next as OrganMode);
        }}
        disabled={disabled}
        aria-label="Mode organ auskultasi"
        className="grid w-full grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {ORGAN_MODES.map((mode) => (
          <ToggleGroupItem
            key={mode}
            value={mode}
            aria-label={`Mode ${ORGAN_MODE_LABELS[mode]}`}
            className="h-9 rounded-md border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground data-[state=on]:border-teal-400/70 data-[state=on]:bg-teal-600/10 data-[state=on]:text-teal-700 data-[state=on]:hover:bg-teal-600/15"
          >
            {ORGAN_MODE_LABELS[mode]}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}
