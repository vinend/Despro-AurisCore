import type { RecordingPhase } from "@/hooks/use-recording";
import type { OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { OrganResultView } from "./organ-result-view";
import { RecordingPlayback } from "./recording-playback";
export function ResultCard({ phase, result, error, file }: {
  phase: RecordingPhase; result: OrganAnalysisResult | null; error: string | null; file: File | null;
}) {
  return <section className="auris-result" aria-labelledby="result-heading" aria-live="polite">
    <div className="auris-section-heading"><h2 id="result-heading">Hasil sesi</h2><span>Analisis audio</span></div>
    {phase === "idle" && <p>Mulai rekaman untuk menganalisis audio yang diterima.</p>}
    {phase === "recording" && <p role="status">Rekaman berjalan…</p>}
    {phase === "processing" && <p role="status">Rekaman sedang dianalisis…</p>}
    {error && <p className="auris-heart-warning" role="alert">{error}</p>}
    {file && <RecordingPlayback file={file} />}
    {result && <OrganResultView result={result} />}
  </section>;
}
