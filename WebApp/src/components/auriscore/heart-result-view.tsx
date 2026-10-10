import { heartDisplay, HEART_SCREENING_NOTICE } from "@/lib/auriscore/heart-display";
import type { HeartAnalysisResult } from "@/lib/auriscore/heart-result";

export function HeartResultView({ result }: { result: HeartAnalysisResult }) {
  const display = heartDisplay(result);
  const murmur = result.murmur;
  return (
    <div className="auris-heart-result" aria-label="Hasil analisis Heart">
      <div className="auris-section-heading">
        <h3>Hasil Heart</h3><span>{result.schema_version}</span>
      </div>
      <dl className="auris-heart-result-grid">
        <div><dt>Kualitas sinyal</dt><dd>{display.quality}</dd></div>
        {result.quality.valid && <>
          <div><dt>Denyut jantung</dt><dd>{display.bpm}{result.rhythm?.heart_rate_bpm != null ? " BPM" : ""}</dd></div>
          <div><dt>Aturan laju</dt><dd>{display.rate}</dd></div>
          <div><dt>Interval tidak teratur</dt><dd>{display.irregular}</dd></div>
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
      {murmur?.status === "available" && murmur.probability_is_calibrated === false &&
        <p>Skor model belum dikalibrasi sebagai probabilitas.</p>}
      {display.reason && <p className="auris-heart-warning" role="alert">{display.reason}</p>}
      {result.quality.valid && result.cardiac_events?.status === "insufficient_evidence" &&
        <p className="auris-heart-warning">Kandidat S1/S2 belum cukup untuk menghitung BPM atau interval.</p>}
      <p className="auris-heart-disclaimer">{HEART_SCREENING_NOTICE} S1/S2 dan S3/S4 adalah kandidat akustik; hasil ini memerlukan validasi lebih lanjut.</p>
    </div>
  );
}
