export interface SignalMetrics {
  sampleCount: number;
  rmsDbfs: number | null;
  clippedFraction: number;
}

/** Exact PCM level/saturation over the latest second; not SNR or clinical quality. */
export class SignalMeter {
  private readonly samples = new Int16Array(8000);
  private count = 0;
  private cursor = 0;
  private squares = 0;
  private clipped = 0;
  private isClipped(sample: number) { return sample <= -32768 || sample >= 32767; }
  accept(values: ArrayLike<number>): void {
    for (let i = 0; i < values.length; i++) {
      if (!Number.isInteger(values[i]) || values[i] < -32768 || values[i] > 32767)
        throw new Error("Expected signed PCM16 samples");
    }
    for (let i = 0; i < values.length; i++) {
      if (this.count === this.samples.length) {
        const old = this.samples[this.cursor];
        this.squares -= old * old;
        this.clipped -= Number(this.isClipped(old));
      } else this.count++;
      const sample = values[i];
      this.samples[this.cursor] = sample;
      this.squares += sample * sample;
      this.clipped += Number(this.isClipped(sample));
      this.cursor = (this.cursor + 1) % this.samples.length;
    }
  }
  read(): SignalMetrics | null {
    if (!this.count) return null;
    const rms = Math.sqrt(this.squares / this.count);
    return { sampleCount: this.count, rmsDbfs: rms > 0 ? 20 * Math.log10(rms / 32768) : null,
      clippedFraction: this.clipped / this.count };
  }
}
