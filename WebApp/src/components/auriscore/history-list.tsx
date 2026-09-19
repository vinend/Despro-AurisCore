import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { History } from "lucide-react";

import type { HistoryEntry } from "@/hooks/use-recording";
import {
  formatDurationMs,
  formatTimestamp,
  ORGAN_MODE_LABELS,
} from "@/lib/auriscore/format";
import { cn } from "@/lib/utils";

interface HistoryListProps {
  entries: HistoryEntry[];
}

/**
 * Riwayat sesi dalam memori (seksi 9): satu baris per sesi — mode organ,
 * durasi, hasil, waktu. Daftar panjang digulir dengan scrollbar tipis.
 */
export function HistoryList({ entries }: HistoryListProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <History className="size-4 text-teal-600" />
          Riwayat sesi
          <Badge variant="secondary" className="ml-auto tabular-nums">
            {entries.length}
          </Badge>
        </CardTitle>
        <CardDescription>
          Daftar sesi dalam memori — hilang saat halaman dimuat ulang.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="rounded-lg border border-dashed bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
            Belum ada sesi rekaman.
          </p>
        ) : (
          <ul
            className="pretty-scrollbar max-h-72 divide-y overflow-y-auto pr-1"
            aria-label="Riwayat sesi rekaman"
          >
            {entries.map((entry) => (
              <li
                key={entry.id}
                className="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0"
              >
                <Badge
                  className={cn(
                    "shrink-0",
                    entry.label === "Normal"
                      ? "border-emerald-200 bg-emerald-100 text-emerald-700 hover:bg-emerald-100"
                      : "border-red-200 bg-red-100 text-red-700 hover:bg-red-100"
                  )}
                >
                  {entry.label}
                </Badge>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {ORGAN_MODE_LABELS[entry.organMode]}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    keyakinan {entry.confidencePercent}%
                  </p>
                </div>
                <div className="ml-auto shrink-0 text-right text-xs text-muted-foreground tabular-nums">
                  <p>{formatDurationMs(entry.durationMs)}</p>
                  <p>{formatTimestamp(entry.ts)}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
