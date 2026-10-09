import type { RecordingPhase } from "@/hooks/use-recording";
import type { ClassificationResult } from "@/lib/auriscore/fake-classifier";
import { formatDurationMs, ORGAN_MODE_LABELS } from "@/lib/auriscore/format";

export function ResultCard({ phase, result }: { phase: RecordingPhase; result: ClassificationResult | null }) {
  return (
    <section className="auris-result" aria-labelledby="result-heading" aria-live="polite">
      <div className="auris-section-heading"><h2 id="result-heading">Hasil sesi</h2><span>Simulasi</span></div>
      {phase === "idle" && <><p className="auris-result-title">Belum ada hasil</p><p>Mulai rekaman untuk melihat contoh hasil sesi.</p></>}
      {phase === "recording" && <><p className="auris-result-title">Rekaman berjalan</p><p>Hasil akan tampil setelah sesi selesai.</p></>}
      {phase === "processing" && <><p className="auris-result-title">Menyiapkan hasil…</p><p>Membuat contoh keluaran simulator.</p></>}
      {phase === "done" && result && <>
        <p className="auris-result-title">{result.label} <small>/ demo</small></p>
        <dl className="auris-result-details">
          <div><dt>Lokasi</dt><dd>{ORGAN_MODE_LABELS[result.organMode]}</dd></div>
          <div><dt>Durasi sesi</dt><dd>{formatDurationMs(result.durationMs)}</dd></div>
        </dl>
        <p>Label contoh ini dihasilkan simulator. Model SVM/CNN belum terhubung.</p>
      </>}
    </section>
  );
}
