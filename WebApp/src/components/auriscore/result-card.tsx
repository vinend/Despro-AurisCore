import { Activity, Loader2, AlertCircle } from "lucide-react";
import type { RecordingPhase } from "@/hooks/use-recording";
import type { OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { OrganResultView } from "./organ-result-view";
import { RecordingPlayback } from "./recording-playback";

export function ResultCard({
  phase,
  result,
  error,
  file,
}: {
  phase: RecordingPhase;
  result: OrganAnalysisResult | null;
  error: string | null;
  file: File | null;
}) {
  return (
    <section className="auris-result" aria-labelledby="result-heading" aria-live="polite">
      <div className="auris-section-heading">
        <h2 id="result-heading" className="flex items-center gap-1.5">
          <Activity className="w-4 h-4 text-emerald-600" />
          <span>Hasil Sesi</span>
        </h2>
        <span>Analisis audio</span>
      </div>

      {phase === "idle" && (
        <p className="text-xs text-muted-foreground leading-relaxed">
          Mulai rekaman untuk menganalisis audio yang diterima.
        </p>
      )}

      {phase === "recording" && (
        <div className="flex items-center gap-2 text-xs text-rose-600 font-medium py-2">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping" />
          <p role="status">Rekaman berjalan…</p>
        </div>
      )}

      {phase === "processing" && (
        <div className="flex items-center gap-2 text-xs text-emerald-700 font-medium py-2">
          <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
          <p role="status">Rekaman sedang dianalisis…</p>
        </div>
      )}

      {error && (
        <div className="auris-heart-warning flex items-start gap-2" role="alert">
          <AlertCircle className="w-4 h-4 text-orange-600 flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {file && <RecordingPlayback file={file} />}
      {result && <OrganResultView result={result} />}
    </section>
  );
}
