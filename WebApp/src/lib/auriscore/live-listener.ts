/** Listening only; no resampled/concealed samples enter recording or analysis. */
export class LiveListener {
  private context: AudioContext | null = null;
  private worklet: AudioWorkletNode | null = null;
  private gain: GainNode | null = null;
  async start() {
    if (this.context) return;
    const context = new AudioContext(); this.context = context;
    try {
      await context.audioWorklet.addModule("/audio/pcg-listener.js");
      if (this.context !== context) { await context.close(); return; }
      this.worklet = new AudioWorkletNode(context, "pcg-listener", { outputChannelCount: [1] });
      this.gain = context.createGain(); this.gain.gain.value = .5;
      this.worklet.connect(this.gain).connect(context.destination); await context.resume();
    } catch (error) { await this.stop(); throw error; }
  }
  accept(samples: number[]) {
    if (!this.worklet || this.context?.state !== "running") return;
    const values = Float32Array.from(samples, sample => sample / 32768);
    this.worklet.port.postMessage({ type: "samples", samples: values }, [values.buffer]);
  }
  volume(value: number) { if (this.gain) this.gain.gain.value = Math.max(0, Math.min(1, value)); }
  reset() { this.worklet?.port.postMessage({ type: "reset" }); }
  async stop() { const context = this.context; this.context = null; this.worklet?.disconnect(); this.gain?.disconnect();
    this.worklet = null; this.gain = null; if (context && context.state !== "closed") await context.close(); }
}
