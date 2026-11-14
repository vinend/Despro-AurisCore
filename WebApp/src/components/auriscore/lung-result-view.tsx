import type { LungAnalysisResult } from "@/lib/auriscore/lung-result";
import { EvidenceTimeline } from "./evidence-timeline";
const names: Record<string, string> = { inhalation: "Inspirasi", exhalation: "Ekspirasi", wheeze: "Wheeze", rhonchi: "Rhonchi", stridor: "Stridor", crackle: "Crackle", cas: "Suara kontinu tambahan" };
export function LungResultView({ result, timeOffset = 0 }: { result: LungAnalysisResult; timeOffset?: number }) {
  const r = result.respiratory;
  return <section className="auris-heart-result" aria-label="Hasil analisis Lung">
    <h3>Hasil Lung</h3>
    <dl className="auris-heart-result-grid">
      <div><dt>Laju napas</dt><dd>{r.respiratory_rate_per_minute === null ? "Belum tersedia" : `${r.respiratory_rate_per_minute.toFixed(1)} / menit`}</dd></div>
      <div><dt>Durasi inspirasi / ekspirasi</dt><dd>{r.inhalation_duration_s === null || r.exhalation_duration_s === null ? "Belum tersedia" : `${r.inhalation_duration_s.toFixed(2)} / ${r.exhalation_duration_s.toFixed(2)} dtk`}</dd></div>
      <div><dt>Rasio I:E</dt><dd>{r.ie_ratio === null ? "Belum tersedia" : `${r.ie_ratio.toFixed(2)}:1`}</dd></div>
      <div><dt>Siklus lengkap</dt><dd>{r.complete_cycle_count}</dd></div>
      {(["wheeze", "crackle", "rhonchi"] as const).map(label => <div key={label}><dt>{names[label]}</dt><dd>{!result.supported_classes.includes(label) ? "Model belum mendukung" : `${result.sound_events.filter(e => e.label === label).length} kandidat akustik`}</dd></div>)}
    </dl>
    {r.reason && <p role="status">Siklus lengkap belum cukup atau fase ambigu; metrik napas belum tersedia.</p>}
    <EvidenceTimeline timeOffset={timeOffset} title="Linimasa kandidat suara dan fase Lung" duration={result.analyzed_duration_s}
      intervals={[...result.sound_events, ...result.phase_intervals].sort((a,b) => a.start_s - b.start_s)
        .map(e => ({...e, label: names[e.label] ?? e.label}))}
      explanation="Rentang mengikuti skor frame dan ambang dari paket model. Penanda merupakan kandidat akustik. Ketelitian waktu perlu dievaluasi pada rekaman berlabel."
      emptyMessage="Model tidak menandai interval suara atau fase pada rentang yang dianalisis." />
    <p>Versi model: {result.model_version}</p><p>Kandidat akustik untuk skrining prototipe — bukan diagnosis.</p>
  </section>;
}
