import { analysisNotice, type OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { HeartResultView } from "./heart-result-view";

export function OrganResultView({ result }: { result: OrganAnalysisResult }) {
  const notice = analysisNotice(result);
  if (result.mode === "heart") return <>
    {notice && <p className="auris-heart-warning" role="status">{notice}</p>}
    {result.analysis && <HeartResultView result={result.analysis} />}
  </>;
  const activity = result.analysis?.activity;
  return <div className="auris-heart-result" aria-label="Hasil analisis Abdomen">
    <h3>Hasil Abdomen</h3>
    {notice && <p className="auris-heart-warning" role="status">{notice}</p>}
    {activity && <>
      <dl className="auris-heart-result-grid">
        <div><dt>Jendela dengan aktivitas</dt><dd>{activity.active_window_count} / {activity.window_count}</dd></div>
        <div><dt>Fraksi jendela aktif</dt><dd>{(activity.active_window_fraction * 100).toFixed(1)}%</dd></div>
        <div><dt>Durasi dianalisis</dt><dd>{activity.analyzed_duration_s.toFixed(2)} s</dd></div>
        <div><dt>Sisa audio tidak dianalisis</dt><dd>{activity.discarded_tail_s.toFixed(2)} s</dd></div>
        <div><dt>Ambang model</dt><dd>{activity.threshold.toFixed(3)}</dd></div>
        <div><dt>Versi model</dt><dd>{activity.model_version}</dd></div>
      </dl>
      <p>Jendela saling tumpang tindih. Fraksi ini bukan persentase durasi aktif atau jumlah kejadian usus.</p>
      <div className="auris-history-scroll"><table>
        <caption>Aktivitas akustik per jendela — skor model belum dikalibrasi sebagai probabilitas</caption>
        <thead><tr><th scope="col">Waktu</th><th scope="col">Skor</th><th scope="col">Temuan akustik</th></tr></thead>
        <tbody>{activity.windows.map(w => <tr key={w.start_s}><td>{w.start_s.toFixed(2)}–{w.end_s.toFixed(2)} s</td>
          <td>{w.score.toFixed(3)}</td><td>{w.label === "present" ? "Aktivitas terdeteksi" : "Aktivitas tidak terdeteksi"}</td></tr>)}</tbody>
      </table></div>
    </>}
    <p>Laju kejadian, variasi interval, dan kategori SB/MB/CRS/HS belum tersedia.</p>
    <p className="auris-heart-disclaimer">Keluaran skrining prototipe — bukan diagnosis.</p>
  </div>;
}
