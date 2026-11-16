import { heartDisplay, HEART_SCREENING_NOTICE } from "@/lib/auriscore/heart-display";
import type { HeartAnalysisResult } from "@/lib/auriscore/heart-result";
import { EvidenceTimeline } from "./evidence-timeline";

export function HeartResultView({ result, timeOffset = 0 }: { result: HeartAnalysisResult; timeOffset?: number }) {
  const display = heartDisplay(result);
  const murmur = result.murmur;
  return (
    <div className="auris-heart-result" aria-label="Hasil analisis Heart">
      <div className="auris-section-heading">
        <h3>Hasil Heart</h3><span>{result.schema_version}</span>
      </div>
      {result.usage_scope === "engineering_test_only" && <p role="status">Uji rekayasa lokal. Skor dan waktu kandidat belum divalidasi pada alat ini.</p>}
      <dl className="auris-heart-result-grid">
        <div><dt>Kualitas sinyal</dt><dd>{display.quality}</dd></div>
        {result.quality.valid && <>
          <div><dt>Denyut jantung</dt><dd>{display.bpm}{result.rhythm?.heart_rate_bpm != null ? " BPM" : ""}</dd></div>
          <div><dt>Aturan laju</dt><dd>{display.rate}</dd></div>
          <div><dt>SD interval S1–S1</dt><dd>{display.intervalSd}</dd></div>
          <div><dt>CV interval S1–S1</dt><dd>{display.intervalCv}</dd></div>
          <div><dt>Evaluasi keteraturan irama</dt><dd>{display.irregular}</dd></div>
          <div><dt>S1</dt><dd>{display.s1}</dd></div>
          <div><dt>S2</dt><dd>{display.s2}</dd></div>
          <div><dt>Sistolik</dt><dd>{display.systole}</dd></div>
          <div><dt>Diastolik</dt><dd>{display.diastole}</dd></div>
          <div><dt>S3</dt><dd>{display.s3}</dd></div>
          <div><dt>S4</dt><dd>{display.s4}</dd></div>
          <div><dt>Murmur</dt><dd>{display.murmur}</dd></div>
          {murmur?.status === "available" && <>
            <div><dt>{murmur.probability_is_calibrated === false ? "Skor model Murmur" : "Probabilitas model Murmur"}</dt>
              <dd>{murmur.probability_is_calibrated === false ? murmur.probability.toFixed(3) : `${(murmur.probability * 100).toFixed(1)}%`}</dd></div>
            <div><dt>Ambang model</dt><dd>{murmur.threshold.toFixed(3)}</dd></div>
            <div><dt>Versi model</dt><dd>{murmur.model_version}</dd></div>
          </>}
          <div><dt>Versi DSP</dt><dd>{display.algorithmVersion}</dd></div>
        </>}
      </dl>
      {result.quality.valid && <p>SD menunjukkan variasi interval dalam milidetik. CV membandingkan SD dengan rata-rata interval. Keduanya dihitung dari kandidat S1; batas penilaian keteraturan irama masih memerlukan validasi.</p>}
      {murmur?.status === "available" && murmur.probability_is_calibrated === false &&
        <p>Skor model belum dikalibrasi sebagai probabilitas.</p>}
      {murmur?.status === "available" && murmur.temporal_evidence ?
        <EvidenceTimeline timeOffset={timeOffset} title="Segmen dengan skor Murmur tinggi" duration={murmur.temporal_evidence.duration_s}
          intervals={murmur.temporal_evidence.windows.filter(w => w.score >= murmur.threshold).map(w => ({...w, label: "Kandidat Murmur per jendela"}))}
          explanation={`Rentang menunjukkan seluruh jendela yang mencapai ambang referensi rekaman ${murmur.threshold.toFixed(3)}. Ketepatan awal/akhir murmur belum tervalidasi. Sisa audio ${murmur.temporal_evidence.discarded_tail_s.toFixed(2)} detik tidak dianalisis.`}
          emptyMessage="Tidak ada jendela yang mencapai ambang referensi. Ini belum memastikan murmur absen." /> :
        <p className="mt-3 text-sm">Penanda waktu Murmur belum tersedia dari backend ini.</p>}
      {display.reason && <p className="auris-heart-warning" role="alert">{display.reason}</p>}
      {result.quality.valid && result.cardiac_events?.status === "insufficient_evidence" &&
        <p className="auris-heart-warning">Kandidat S1/S2 belum cukup untuk menghitung BPM atau interval.</p>}
      <p className="auris-heart-disclaimer">{HEART_SCREENING_NOTICE} S1/S2 dan S3/S4 adalah kandidat akustik; hasil ini memerlukan validasi lebih lanjut.</p>
    </div>
  );
}
