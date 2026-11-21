import type { OrganAnalysisResult } from "./analysis-result.ts";

export const recordingLabels = {
  s1: "S1", s2: "S2", s3: "Kandidat S3", s4: "Kandidat S4",
  systole: "Sistolik", diastole: "Diastolik", murmur: "Kandidat Murmur",
  inhalation: "Inspirasi", exhalation: "Ekspirasi", wheeze: "Wheeze",
  rhonchi: "Rhonchi", stridor: "Stridor", crackle: "Crackle", cas: "Suara kontinu tambahan",
  bowel: "Kandidat bunyi usus", activity: "Jendela aktivitas usus",
} as const;

type Label = keyof typeof recordingLabels;
type Mark = { label: Label; start_s: number; end_s: number; score?: number };

export function recordingMarks(result: OrganAnalysisResult | null | undefined, duration: number): Mark[] {
  if (!result?.quality.valid) return [];
  const marks: Mark[] = [];
  if (result.mode === "heart" && result.analysis) {
    const { cardiac_events: events, murmur } = result.analysis;
    if (events) {
      const points = { s1: events.s1_times_s, s2: events.s2_times_s,
        s3: events.s3_candidates_s, s4: events.s4_candidates_s } as const;
      for (const [label, times] of Object.entries(points)) {
        marks.push(...times.map(time => ({ label: label as keyof typeof points, start_s: time, end_s: time })));
      }
      marks.push(...events.systolic_intervals.map(interval => ({ ...interval, label: "systole" as const })));
      marks.push(...events.diastolic_intervals.map(interval => ({ ...interval, label: "diastole" as const })));
    }
    if (murmur?.status === "available" && murmur.temporal_evidence) {
      marks.push(...murmur.temporal_evidence.windows.filter(window => window.score >= murmur.threshold)
        .map(window => ({ ...window, label: "murmur" as const })));
    }
  } else if (result.mode === "lung" && result.analysis) {
    marks.push(...result.analysis.sound_events, ...result.analysis.phase_intervals);
  } else if (result.mode === "abdomen" && result.analysis) {
    const { activity, bowel_events: events } = result.analysis;
    marks.push(...(events ?? []).map(event => ({ ...event, label: "bowel" as const })));
    marks.push(...(activity?.windows ?? []).filter(window => window.label === "present")
      .map(window => ({ ...window, label: "activity" as const })));
  }
  return marks.filter(mark => Number.isFinite(mark.start_s) && Number.isFinite(mark.end_s)
    && mark.start_s >= 0 && mark.start_s < duration && mark.end_s >= mark.start_s)
    .map(mark => ({ ...mark, end_s: Math.min(mark.end_s, duration) }))
    .sort((a, b) => a.start_s - b.start_s);
}

/** Peak envelope of the actual PCM16 mono WAV produced by device capture. */
export function recordingWaveform(buffer: ArrayBuffer) {
  const view = new DataView(buffer);
  if (view.byteLength < 12 || view.getUint32(0) !== 0x52494646 || view.getUint32(8) !== 0x57415645)
    throw new Error("WAV tidak valid");
  let rate = 0;
  let samples: { offset: number; count: number } | undefined;
  for (let chunk = 12; chunk + 8 <= view.byteLength;) {
    const size = view.getUint32(chunk + 4, true);
    const offset = chunk + 8;
    if (offset + size > view.byteLength) throw new Error("WAV terpotong");
    const tag = view.getUint32(chunk);
    if (tag === 0x666d7420) {
      if (size < 16 || view.getUint16(offset, true) !== 1 || view.getUint16(offset + 2, true) !== 1
          || view.getUint16(offset + 14, true) !== 16) throw new Error("Gunakan WAV PCM16 mono");
      rate = view.getUint32(offset + 4, true);
    } else if (tag === 0x64617461 && size > 0 && size % 2 === 0 && !samples) {
      samples = { offset, count: size / 2 };
    }
    chunk = offset + size + size % 2;
  }
  if (!rate || !samples) throw new Error("WAV tidak memiliki sampel");
  const { offset, count } = samples;
  const columns = Math.min(count, 1200);
  let amplitude = 1;
  const peaks = Array.from({ length: columns }, (_, x) => {
    const start = Math.floor(x * count / columns);
    const end = Math.floor((x + 1) * count / columns);
    let low = 32767;
    let high = -32768;
    for (let sample = start; sample < end; sample += 1) {
      const value = view.getInt16(offset + sample * 2, true);
      low = Math.min(low, value);
      high = Math.max(high, value);
    }
    amplitude = Math.max(amplitude, Math.abs(low), Math.abs(high));
    return { low, high };
  });
  const path = peaks.map(({ low, high }, x) => {
    const top = 50 - 46 * high / amplitude;
    const bottom = Math.max(top + 0.35, 50 - 46 * low / amplitude);
    return `M${x + 0.5} ${top.toFixed(2)}V${bottom.toFixed(2)}`;
  }).join("");
  const spectrum = recordingSpectrum(view, offset, count);
  return { duration: count / rate, columns, path, spectrum, nyquist: rate / 2 };
}

function recordingSpectrum(view: DataView, offset: number, count: number) {
  const size = 256;
  const width = Math.min(600, Math.max(1, Math.ceil(count / 128)));
  const height = size / 2;
  const pixels = new Uint8ClampedArray(width * height * 4);
  const real = new Float64Array(size);
  const imag = new Float64Array(size);
  const window = Array.from({ length: size }, (_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (size - 1)));
  const reversed = Array.from({ length: size }, (_, i) => {
    let index = 0;
    for (let bit = 1; bit < size; bit *= 2) { index = (index << 1) | Number((i & bit) !== 0); }
    return index;
  });
  for (let x = 0; x < width; x += 1) {
    const center = Math.floor((x + 0.5) * count / width);
    for (let i = 0; i < size; i += 1) {
      const sample = center + i - size / 2;
      real[reversed[i]] = sample < 0 || sample >= count ? 0
        : view.getInt16(offset + sample * 2, true) / 32768 * window[i];
    }
    imag.fill(0);
    for (let span = 2; span <= size; span *= 2) {
      const half = span / 2;
      for (let j = 0; j < half; j += 1) {
        const angle = -2 * Math.PI * j / span;
        const cosine = Math.cos(angle);
        const sine = Math.sin(angle);
        for (let left = j; left < size; left += span) {
          const right = left + half;
          const r = real[right] * cosine - imag[right] * sine;
          const i = real[right] * sine + imag[right] * cosine;
          real[right] = real[left] - r;
          imag[right] = imag[left] - i;
          real[left] += r;
          imag[left] += i;
        }
      }
    }
    for (let bin = 0; bin < height; bin += 1) {
      const db = 20 * Math.log10(Math.max(1e-6, Math.hypot(real[bin], imag[bin]) * 4 / size));
      const level = Math.max(0, Math.min(1, (db + 80) / 70));
      const pixel = ((height - 1 - bin) * width + x) * 4;
      pixels[pixel] = 12 + 242 * level ** 2;
      pixels[pixel + 1] = 25 + 208 * level;
      pixels[pixel + 2] = 27 + 140 * level * (1 - level / 2);
      pixels[pixel + 3] = 255;
    }
  }
  return { width, height, pixels };
}
