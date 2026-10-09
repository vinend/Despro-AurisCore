import assert from "node:assert/strict";
import test from "node:test";
import { analyzeHeartAudio, BleAudioSource, PcgCaptureBuffer, pcmToWavFile } from "../src/lib/auriscore/heart-audio-source.ts";

function packet(seq, sample = 120) {
  return { type: "pcg_packet", seq, ts: seq * 50, samplingRate: 8000,
    organMode: "mitral", qualityFlag: "good", channels: 1,
    samples: Array(400).fill(sample) };
}

test("mock packets concatenate deterministically into analysis-ready audio", async () => {
  const capture = new PcgCaptureBuffer();
  capture.start();
  capture.accept(packet(0, -100));
  capture.accept(packet(0, 300)); // duplicate is ignored
  capture.accept(packet(1, 200));
  const audio = capture.stop("mock");
  assert.equal(audio.waveform.length, 800);
  assert.equal(audio.waveform[0], -100);
  assert.equal(audio.waveform[799], 200);
  assert.equal(audio.packetsReceived, 2);
  assert.equal(audio.bytesReceived, 1600);
  assert.equal(audio.durationSeconds, 0.1);
  assert.equal(audio.minimumSample, -100);
  assert.equal(audio.maximumSample, 200);
  const wav = pcmToWavFile(audio);
  const view = new DataView(await wav.arrayBuffer());
  assert.equal(wav.name, "heart-capture.wav");
  assert.equal(view.getUint32(24, true), 8000);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint16(34, true), 16);
  assert.equal(view.getInt16(44, true), -100);
  assert.equal(view.getInt16(44 + 2 * 799, true), 200);
});

test("packet gaps, malformed input, and disconnect fail without fabricated analysis samples", () => {
  for (const bad of [null, { ...packet(0), samples: [1] }]) {
    const capture = new PcgCaptureBuffer(); capture.start(); capture.accept(bad);
    assert.equal(capture.state, "error");
    assert.throws(() => capture.stop("mock"));
  }
  const gap = new PcgCaptureBuffer(); gap.start(); gap.accept(packet(0)); gap.accept(packet(2));
  assert.equal(gap.telemetry().missingPackets, 1);
  assert.throws(() => gap.stop("mock"), /hilang/);
  const disconnected = new PcgCaptureBuffer(); disconnected.start(); disconnected.accept(packet(0));
  disconnected.disconnect();
  assert.throws(() => disconnected.stop("mock"), /terputus/);
});

test("mock stream and file fallback converge on the same HeartAnalysisService", async () => {
  const capture = new PcgCaptureBuffer(); capture.start();
  for (let i = 0; i < 200; i++) capture.accept(packet(i, 0));
  const audio = capture.stop("mock");
  const calls = [];
  const service = { async analyze(file) {
    calls.push(file);
    return { schema_version: "heart-analysis-v1", quality: { valid: false, reason: "silent_signal" },
      rhythm: null, cardiac_events: null, murmur: null };
  } };
  const result = await analyzeHeartAudio({ kind: "pcm", audio }, service);
  assert.equal(result.schema_version, "heart-analysis-v1");
  assert.equal(result.rhythm, null); // invalid signal does not fabricate BPM
  assert.equal(calls[0].name, "heart-capture.wav");
  const file = new File(["RIFF....WAVE"], "fallback.wav");
  await analyzeHeartAudio({ kind: "file", file }, service);
  assert.equal(calls[1], file);
});

test("BLE software adapter requires an injected transport/decoder and handles disconnect", async () => {
  let onBytes;
  let onDisconnect;
  const transport = {
    async connect(bytes, disconnected) { onBytes = bytes; onDisconnect = disconnected; },
    async disconnect() { onDisconnect(); },
    async startCapture() {}, async stopCapture() {},
  };
  const ble = new BleAudioSource(transport, bytes => packet(bytes[0]));
  await ble.connect();
  assert.equal(ble.state, "connected");
  await ble.startCapture();
  onBytes(new Uint8Array([0]));
  onBytes(new Uint8Array([1]));
  const audio = await ble.stopCapture();
  assert.equal(audio.source, "ble");
  assert.equal(audio.waveform.length, 800);
  await ble.disconnect();
  assert.equal(ble.state, "disconnected");
  await ble.connect();
  await ble.startCapture();
  onDisconnect();
  assert.equal(ble.state, "disconnected");
  await assert.rejects(() => ble.stopCapture(), /terputus/);
});
