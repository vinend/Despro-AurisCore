import { Clock, History, Activity, Calendar } from "lucide-react";
import type { HistoryEntry } from "@/hooks/use-recording";
import { formatDurationMs, formatTimestamp } from "@/lib/auriscore/format";

export function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  const organNames = { heart: "Heart", abdomen: "Abdomen", lung: "Lung" } as const;
  const statusLabels = {
    completed: "Selesai",
    partial: "Sebagian tersedia",
    unavailable: "Belum tersedia",
    error: "Audio tidak valid",
  } as const;

  return (
    <section className="auris-history" aria-labelledby="history-heading">
      <div className="auris-history-heading">
        <h2 id="history-heading">
          <History className="w-4 h-4 text-emerald-600" />
          <span>Catatan sesi</span>
          <span>{entries.length.toString().padStart(2, "0")}</span>
        </h2>
        <p>Metadata 50 sesi terakhir selama halaman ini terbuka. Rekaman tidak disimpan.</p>
      </div>

      {entries.length === 0 ? (
        <div className="auris-history-empty flex flex-col items-center justify-center gap-2 py-8 text-center">
          <History className="w-8 h-8 text-muted-foreground/50" />
          <p className="text-xs text-muted-foreground">Belum ada sesi yang dianalisis.</p>
        </div>
      ) : (
        <>
          {/* Mobile Card View (visible on small screens) */}
          <div className="grid gap-2.5 pt-3 sm:hidden">
            {entries.map((entry) => {
              const organ = organNames[entry.mode];
              const statusText = statusLabels[entry.result.status];
              const isSuccess = entry.result.status === "completed";
              const isError = entry.result.status === "error";

              return (
                <div
                  key={entry.id}
                  className="p-3 bg-muted/30 rounded-xl border border-border/70 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[11px] font-semibold text-emerald-950 bg-white px-2 py-0.5 rounded border border-border/80">
                      #{entry.id}
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                      {organ}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-muted-foreground text-[11px]">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3 text-muted-foreground/70" />
                      {formatTimestamp(entry.ts)}
                    </span>
                    <span className="flex items-center gap-1 font-mono">
                      <Clock className="w-3 h-3 text-muted-foreground/70" />
                      {formatDurationMs(entry.durationMs)}
                    </span>
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-border/40 text-[11px]">
                    <span className="text-muted-foreground">
                      {entry.source === "mock" ? "Simulator" : "Perangkat"}
                    </span>
                    <span
                      className={`font-medium px-2 py-0.5 rounded ${
                        isSuccess
                          ? "bg-emerald-100/70 text-emerald-800"
                          : isError
                          ? "bg-rose-100 text-rose-800"
                          : "bg-amber-100/70 text-amber-800"
                      }`}
                    >
                      {statusText}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Desktop/Tablet Table View (hidden on mobile) */}
          <div className="hidden sm:block auris-history-scroll pretty-scrollbar">
            <table>
              <caption className="sr-only">Riwayat analisis rekaman</caption>
              <thead>
                <tr>
                  <th scope="col">Sesi</th>
                  <th scope="col">Waktu · WIB</th>
                  <th scope="col">Organ</th>
                  <th scope="col">Sumber</th>
                  <th scope="col">Durasi</th>
                  <th scope="col">Status analisis</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="font-mono text-xs">{entry.id}</td>
                    <td>{formatTimestamp(entry.ts)}</td>
                    <td>
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                        {organNames[entry.mode]}
                      </span>
                    </td>
                    <td>{entry.source === "mock" ? "Simulator" : "Perangkat"}</td>
                    <td className="font-mono">{formatDurationMs(entry.durationMs)}</td>
                    <td>
                      <span
                        className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          entry.result.status === "completed"
                            ? "bg-emerald-100/70 text-emerald-800"
                            : entry.result.status === "error"
                            ? "bg-rose-100 text-rose-800"
                            : "bg-amber-100/70 text-amber-800"
                        }`}
                      >
                        {statusLabels[entry.result.status]}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
