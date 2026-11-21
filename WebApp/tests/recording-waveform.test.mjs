import assert from "node:assert/strict";
import test from "node:test";
import { pcmToWavFile } from "../src/lib/auriscore/heart-audio-source.ts";
import { recordingMarks, recordingWaveform } from "../src/lib/auriscore/recording-waveform.ts";

test("waveform and spectrogram use the captured samples and their time base", async () => {
  const sampleRate = 8000;
  const waveform = Int16Array.from({ length: sampleRate }, (_, i) =>
    i < sampleRate / 2 ? 0 : Math.round(12000 * Math.sin(2 * Math.PI * i / 8)));
  const wav = await pcmToWavFile({ sampleRate, waveform }).arrayBuffer();
  const result = recordingWaveform(wav);
  assert.equal(result.duration, 1);
  assert.equal(result.nyquist, 4000);
  const { pixels, width, height } = result.spectrum;
  const at = (x, bin) => pixels[((height - 1 - bin) * width + x) * 4 + 1];
  assert.equal(at(Math.floor(width / 4), 32), 25);
  assert.ok(at(Math.floor(3 * width / 4), 32) > at(Math.floor(3 * width / 4), 70) + 100);
  assert.throws(() => recordingWaveform(wav.slice(0, -2)), /terpotong/);
});

test("recording markers preserve overlap and never infer Murmur from a DSP-only result", () => {
  const quality = { valid: true };
  const heart = { quality, mode: "heart", analysis: { cardiac_events: {
    s1_times_s: [0.1], s2_times_s: [0.2], s3_candidates_s: [], s4_candidates_s: [],
    systolic_intervals: [{ start_s: 0.1, end_s: 0.2 }], diastolic_intervals: [],
  }, murmur: { status: "unavailable" } } };
  assert.deepEqual(recordingMarks(heart, 1).map(mark => mark.label), ["s1", "systole", "s2"]);
  heart.analysis.murmur = { status: "available", threshold: 0.5, temporal_evidence: { windows: [
    { start_s: 0.1, end_s: 0.5, score: 0.4 },
    { start_s: 0.2, end_s: 1.2, score: 0.7 },
  ] } };
  assert.deepEqual(recordingMarks(heart, 1).filter(mark => mark.label === "murmur"),
    [{ label: "murmur", start_s: 0.2, end_s: 1, score: 0.7 }]);

  const lung = { quality, mode: "lung", analysis: {
    sound_events: [{ label: "wheeze", start_s: 0, end_s: 0.7 },
      { label: "crackle", start_s: 0.3, end_s: 0.9 }], phase_intervals: [],
  } };
  assert.deepEqual(recordingMarks(lung, 1), lung.analysis.sound_events);
  const abdomen = { quality, mode: "abdomen", analysis: {
    bowel_events: [{ start_s: 0.2, end_s: 0.3, score: 0.6 }], activity: null,
  } };
  assert.deepEqual(recordingMarks(abdomen, 1), [{ label: "bowel", start_s: 0.2, end_s: 0.3, score: 0.6 }]);
  assert.deepEqual(recordingMarks({ ...abdomen, quality: { valid: false } }, 1), []);
});
