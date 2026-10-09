/** Presentation labels for screening output; missing values stay explicit. */
import type { HeartAnalysisResult } from "./heart-result.ts";

export const HEART_SCREENING_NOTICE = "Keluaran skrining prototipe — bukan diagnosis.";

const reasons: Record<string, string> = {
  empty_signal: "Rekaman kosong.",
  nonfinite_signal: "Sampel audio tidak valid.",
  invalid_samples: "Sampel audio tidak valid.",
  signal_too_short: "Rekaman terlalu singkat untuk dianalisis.",
  silent_signal: "Sinyal hening atau terlalu lemah.",
  mono_waveform_required: "Gunakan WAV mono.",
  invalid_sample_rate: "Laju sampel audio tidak didukung.",
};

export function heartDisplay(result: HeartAnalysisResult) {
  if (!result.quality.valid) {
    return {
      quality: "Tidak valid",
      reason: reasons[result.quality.reason ?? ""] ?? "Audio tidak dapat dianalisis; coba rekam ulang.",
      bpm: "Belum tersedia",
      rate: "Belum tersedia",
      irregular: "Belum tersedia",
      s1: "Belum tersedia",
      s2: "Belum tersedia",
      systole: "Belum tersedia",
      diastole: "Belum tersedia",
      s3: "Belum tersedia",
      s4: "Belum tersedia",
      murmur: "Belum tersedia karena audio tidak valid",
      algorithmVersion: null,
    };
  }
  const rhythm = result.rhythm!;
  const events = result.cardiac_events!;
  const rateLabels = {
    normal: "Normal (aturan laju prototipe)",
    tachycardia: "Laju cepat (aturan prototipe)",
    bradycardia: "Laju lambat (aturan prototipe)",
    unknown: "Belum cukup data",
  };
  return {
    quality: "Valid untuk analisis prototipe",
    reason: null,
    bpm: rhythm.heart_rate_bpm === null ? "Belum cukup data" : rhythm.heart_rate_bpm.toFixed(1),
    rate: rateLabels[rhythm.label],
    irregular: rhythm.irregular === null ? "Belum cukup interval" : rhythm.irregular ? "Indikasi interval tidak teratur" : "Tidak terindikasi",
    s1: events.status === "paired_candidates" ? `${events.s1_times_s.length} kandidat` : "Belum cukup bukti",
    s2: events.status === "paired_candidates" ? `${events.s2_times_s.length} kandidat` : "Belum cukup bukti",
    systole: events.systolic_interval_ms === null ? "Belum tersedia" : `${events.systolic_interval_ms.toFixed(0)} ms`,
    diastole: events.diastolic_interval_ms === null ? "Belum tersedia" : `${events.diastolic_interval_ms.toFixed(0)} ms`,
    s3: events.status === "paired_candidates" ? `${events.s3_candidates_s.length} kandidat eksperimental` : "Belum cukup bukti",
    s4: events.status === "paired_candidates" ? `${events.s4_candidates_s.length} kandidat eksperimental` : "Belum cukup bukti",
    murmur: result.murmur?.status === "available"
      ? result.murmur.label === "present" ? "Murmur diduga" : "Murmur tidak terdeteksi"
      : "Analisis Murmur belum tersedia",
    algorithmVersion: rhythm.algorithm_version,
  };
}
