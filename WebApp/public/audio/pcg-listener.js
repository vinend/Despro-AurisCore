/* Bounded 8 kHz listening buffer; linear output resampling, no recording mutation. */
class PcgListener extends AudioWorkletProcessor {
  constructor() {
    super(); this.samples = new Float32Array(8000); this.read = 0; this.write = 0; this.count = 0; this.phase = 0; this.started = false;
    this.port.onmessage = ({ data }) => {
      if (data.type === "reset") { this.count = 0; this.read = 0; this.write = 0; this.phase = 0; this.started = false; return; }
      if (data.type !== "samples" || !(data.samples instanceof Float32Array) || data.samples.length !== 400) return;
      // Drop old listening backlog after a stall. Original recording remains separate.
      if (this.count + data.samples.length > 2400) { this.count = 0; this.read = this.write; this.phase = 0; this.started = false; }
      for (const sample of data.samples) { this.samples[this.write] = sample; this.write = (this.write + 1) % 8000; this.count++; }
    };
  }
  process(_inputs, outputs) {
    const output = outputs[0][0];
    if (!this.started && this.count >= 800) this.started = true;
    // Small occupancy correction limits source/output clock drift. Listening only.
    const ratio = 8000 / sampleRate * (1 + Math.max(-.01, Math.min(.01, (this.count - 800) / 80000)));
    for (let i = 0; i < output.length; i++) {
      if (!this.started || this.count < 2) { output[i] = 0; this.started = false; continue; }
      const a = this.samples[this.read], b = this.samples[(this.read + 1) % 8000];
      output[i] = a + (b - a) * this.phase; this.phase += ratio;
      while (this.phase >= 1 && this.count > 0) { this.phase--; this.read = (this.read + 1) % 8000; this.count--; }
    }
    return true;
  }
}
registerProcessor("pcg-listener", PcgListener);
