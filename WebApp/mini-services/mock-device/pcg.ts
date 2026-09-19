// pcg.ts -- sintesis PCG (fonokardiogram) sintetis untuk mock-device AurisCore.
// Kelas murni tanpa I/O dan tanpa dependensi WebSocket/timer supaya mudah
// dipindah / diuji terpisah dari server.

// Nilai sintetis ini hanya untuk visual demo, bukan model fisiologis akurat.

/** Pergeseran S2 terhadap S1: tS2 = tS1 + 0.30 detik. */
const S2_OFFSET_SECONDS = 0.30;

/** Level noise ambient (konstanta). Dipakai juga aturan qualityFlag di index.ts. */
export const NOISE_LEVEL = 0.02;

/** Batasi nilai pecahan ke rentang int16, dibulatkan ke bilangan bulat. */
function clampToInt16(value: number): number {
  const rounded = Math.round(value);
  if (rounded < -32768) return -32768;
  if (rounded > 32767) return 32767;
  return rounded;
}

export class PcgSynthesizer {
  private readonly fs: number;
  private bpm: number;
  /** Posisi sampel absolut sejak awal stream. */
  private sampleIndex: number;
  /** Posisi sampel awal beat yang sedang berjalan. */
  private beatStartSample: number;
  /** Panjang beat saat ini dalam sampel: round(RR * fs). */
  private beatLengthSamples: number;

  constructor(fs: number, bpm: number) {
    this.fs = fs;
    this.bpm = bpm;
    this.sampleIndex = 0;
    this.beatStartSample = 0;
    this.beatLengthSamples = this.beatLengthFor(this.bpm);
  }

  /** bpm baru: berlaku mulai beat BERIKUTNYA (panjang beat yang berjalan tetap). */
  setBpm(bpm: number): void {
    this.bpm = bpm;
  }

  /** bpm target yang berlaku saat ini (dipakai untuk device_status). */
  getBpm(): number {
    return this.bpm;
  }

  /** Panjang satu beat (jumlah sampel) untuk bpm tertentu: round(RR * fs). */
  private beatLengthFor(bpm: number): number {
    const rr = 60 / bpm; // durasi satu beat dalam detik
    return Math.round(rr * this.fs);
  }

  /**
   * Mulai beat baru pada batas beat saat ini; panjang beat dihitung ulang dari
   * bpm TERKINI sehingga set_bpm berlaku pada beat berikutnya.
   */
  private advanceBeat(): void {
    this.beatStartSample += this.beatLengthSamples;
    this.beatLengthSamples = this.beatLengthFor(this.bpm);
  }

  /** Hitung satu sampel pada posisi this.sampleIndex (relatif awal beat). */
  private currentSample(): number {
    const t = (this.sampleIndex - this.beatStartSample) / this.fs; // t - tS1
    const tS2 = S2_OFFSET_SECONDS;

    // s1(t) = 0.8 * exp(-((t - tS1) / 0.0175)^2) * sin(2*pi*55*(t - tS1))
    const e1 = (t / 0.0175) ** 2;
    const s1 = 0.8 * Math.exp(-e1) * Math.sin(2 * Math.PI * 55 * t);

    // s2(t) = 0.6 * exp(-((t - tS2) / 0.0125)^2) * sin(2*pi*70*(t - tS2))
    const e2 = ((t - tS2) / 0.0125) ** 2;
    const s2 = 0.6 * Math.exp(-e2) * Math.sin(2 * Math.PI * 70 * (t - tS2));

    // Noise ambient: noiseLevel * (Math.random() - 0.5) * 2
    const noise = NOISE_LEVEL * (Math.random() - 0.5) * 2;

    // Sampel akhir: clampToInt16((s1 + s2 + noise) * 0.8 * 32767)
    return clampToInt16((s1 + s2 + noise) * 0.8 * 32767);
  }

  /** Ambil n sampel berikutnya dan majukan posisi synthesizer sebanyak n. */
  nextSamples(n: number): number[] {
    const samples: number[] = new Array<number>(n);
    for (let i = 0; i < n; i++) {
      // Saat posisi sampel melewati akhir beat, mulai beat baru
      // (panjang beat dihitung ulang dari bpm saat itu).
      while (this.sampleIndex >= this.beatStartSample + this.beatLengthSamples) {
        this.advanceBeat();
      }
      samples[i] = this.currentSample();
      this.sampleIndex += 1;
    }
    return samples;
  }
}
