import type { LungAnalysisResult } from "@/lib/auriscore/lung-result";
const names: Record<string, string> = { inhalation: "Inspirasi", exhalation: "Ekspirasi", wheeze: "Wheeze", rhonchi: "Rhonchi", stridor: "Stridor", crackle: "Crackle", cas: "Suara kontinu tambahan" };
export function LungResultView({ result }: { result: LungAnalysisResult }) {
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
    <figure aria-label="Linimasa suara dan fase napas"><figcaption>Linimasa kandidat · detik</figcaption>
      <svg viewBox="0 0 600 160" role="img" aria-label="Interval fase dan suara Lung" style={{ width: "100%" }}>
        {result.supported_classes.map((label, lane) => <g key={label}><text x="0" y={lane * 20 + 14} fontSize="10">{names[label]}</text>
          {[...result.sound_events, ...result.phase_intervals].filter(e => e.label === label).map((e, i) => <rect key={i} x={130 + e.start_s / result.analyzed_duration_s * 450} y={lane * 20 + 3}
            width={Math.max(1, (e.end_s - e.start_s) / result.analyzed_duration_s * 450)} height="12" fill="currentColor"><title>{`${names[label]} ${e.start_s.toFixed(2)}–${e.end_s.toFixed(2)} dtk`}</title></rect>)}</g>)}
      </svg>
    </figure>
    <details><summary>Interval kandidat</summary><ul>{[...result.phase_intervals, ...result.sound_events].map((e, i) => <li key={i}>{names[e.label]}: {e.start_s.toFixed(2)}–{e.end_s.toFixed(2)} dtk</li>)}</ul></details>
    <p>Versi model: {result.model_version}</p><p>Kandidat akustik untuk skrining prototipe — bukan diagnosis.</p>
  </section>;
}
