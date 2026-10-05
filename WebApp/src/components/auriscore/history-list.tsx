import type { HistoryEntry } from "@/hooks/use-recording";
import { formatDurationMs, formatTimestamp, ORGAN_MODE_LABELS } from "@/lib/auriscore/format";

export function HistoryList({ entries }: { entries: HistoryEntry[] }) {
  return (
    <section className="auris-history" aria-labelledby="history-heading">
      <div className="auris-history-heading"><h2 id="history-heading">Catatan sesi <span>{entries.length.toString().padStart(2, "0")}</span></h2>
        <p>Tersimpan selama halaman ini terbuka.</p></div>
      {entries.length === 0 ? <div className="auris-history-empty"><span>—</span><p>Sesi pertama akan tercatat di sini setelah rekaman selesai.</p></div> :
        <div className="auris-history-scroll pretty-scrollbar">
          <table><caption className="sr-only">Riwayat sesi rekaman simulasi</caption>
            <thead><tr><th scope="col">Sesi</th><th scope="col">Waktu · WIB</th><th scope="col">Lokasi</th><th scope="col">Durasi</th><th scope="col">Hasil simulasi</th></tr></thead>
            <tbody>{entries.map((entry) => <tr key={entry.id}>
              <td className="auris-small-mono">{entry.id.toString().padStart(2, "0")}</td><td>{formatTimestamp(entry.ts)}</td>
              <td>{ORGAN_MODE_LABELS[entry.organMode]}</td><td>{formatDurationMs(entry.durationMs)}</td><td>{entry.label} / demo</td>
            </tr>)}</tbody>
          </table>
        </div>}
    </section>
  );
}
