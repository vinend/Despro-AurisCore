import type { HistoryEntry } from "@/hooks/use-recording";
import { formatDurationMs, formatTimestamp } from "@/lib/auriscore/format";
export function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  return <section className="auris-history" aria-labelledby="history-heading">
    <div className="auris-history-heading"><h2 id="history-heading">Catatan sesi <span>{entries.length.toString().padStart(2, "0")}</span></h2>
      <p>Metadata 50 sesi terakhir selama halaman ini terbuka. Rekaman tidak disimpan.</p></div>
    {entries.length === 0 ? <div className="auris-history-empty"><p>Belum ada sesi yang dianalisis.</p></div> :
      <div className="auris-history-scroll pretty-scrollbar"><table><caption className="sr-only">Riwayat analisis rekaman</caption>
        <thead><tr><th scope="col">Sesi</th><th scope="col">Waktu · WIB</th><th scope="col">Organ</th><th scope="col">Sumber</th><th scope="col">Durasi</th><th scope="col">Status analisis</th></tr></thead>
        <tbody>{entries.map(entry => <tr key={entry.id}><td>{entry.id}</td><td>{formatTimestamp(entry.ts)}</td>
          <td>{entry.mode === "heart" ? "Heart" : "Abdomen"}</td><td>{entry.source === "mock" ? "Simulator" : "Perangkat"}</td>
          <td>{formatDurationMs(entry.durationMs)}</td><td>{{ completed: "Selesai", partial: "Sebagian tersedia", unavailable: "Belum tersedia", error: "Audio tidak valid" }[entry.result.status]}</td></tr>)}</tbody>
      </table></div>}
  </section>;
}
