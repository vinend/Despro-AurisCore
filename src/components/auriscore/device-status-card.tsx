import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import {
  Activity,
  BatteryFull,
  HeartPulse,
  Stethoscope,
} from "lucide-react";

import { ORGAN_MODE_LABELS, QUALITY_LABELS } from "@/lib/auriscore/format";
import type {
  DeviceStatusMsg,
  OrganMode,
  QualityFlag,
} from "@/lib/auriscore/protocol";
import { cn } from "@/lib/utils";

const qualityTextStyles: Record<QualityFlag, string> = {
  good: "text-emerald-600",
  fair: "text-amber-600",
  poor: "text-red-600",
};

const qualityDotStyles: Record<QualityFlag, string> = {
  good: "bg-emerald-500",
  fair: "bg-amber-500",
  poor: "bg-red-500",
};

interface DeviceStatusCardProps {
  /** device_status terakhir; null saat belum ada (menyambung). */
  status: DeviceStatusMsg | null;
  organMode: OrganMode;
  connected: boolean;
}

/**
 * Kartu status perangkat (seksi 9): BPM, baterai, kualitas sinyal, dan mode
 * organ aktif — dari device_status terakhir. Saat terputus, nilai terakhir
 * yang diketahui tetap ditampilkan (dicatat di DECISIONS.md).
 */
export function DeviceStatusCard({
  status,
  organMode,
  connected,
}: DeviceStatusCardProps) {
  const bpmText = status ? String(Math.round(status.bpm)) : "—";
  const batteryText = status ? `${Math.round(status.batteryPercent)}%` : "—";
  const quality = status?.signalQuality ?? null;

  return (
    <Card className="py-4 sm:py-5">
      <CardContent className="grid grid-cols-2 gap-2.5 px-4 sm:grid-cols-4 sm:gap-3 sm:px-5">
        <StatCell
          label="BPM"
          icon={
            <HeartPulse
              className={cn(
                "size-3.5 text-teal-600",
                connected && "animate-pulse"
              )}
            />
          }
          value={<span className="tabular-nums">{bpmText}</span>}
        />
        <StatCell
          label="Baterai"
          icon={<BatteryFull className="size-3.5 text-teal-600" />}
          value={<span className="tabular-nums">{batteryText}</span>}
        />
        <StatCell
          label="Kualitas sinyal"
          icon={<Activity className="size-3.5 text-teal-600" />}
          value={
            quality ? (
              <span
                className={cn(
                  "flex items-center gap-1.5",
                  qualityTextStyles[quality]
                )}
              >
                <span
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    qualityDotStyles[quality]
                  )}
                />
                {QUALITY_LABELS[quality]}
              </span>
            ) : (
              "—"
            )
          }
        />
        <StatCell
          label="Mode organ"
          icon={<Stethoscope className="size-3.5 text-teal-600" />}
          value={ORGAN_MODE_LABELS[organMode]}
        />
      </CardContent>
    </Card>
  );
}

function StatCell({
  label,
  icon,
  value,
}: {
  label: string;
  icon: ReactNode;
  value: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 rounded-lg border bg-muted/40 p-3">
      <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="truncate text-base font-semibold leading-none sm:text-lg">
        {value}
      </span>
    </div>
  );
}
