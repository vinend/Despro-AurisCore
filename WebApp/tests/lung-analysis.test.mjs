import assert from "node:assert/strict";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseOrganAnalysisResult, analysisNotice } from "../src/lib/auriscore/analysis-result.ts";
import { createAnalysisHandler } from "../src/lib/auriscore/analysis-route.server.ts";
import { LungResultView } from "../src/components/auriscore/lung-result-view.tsx";
import { RecordingSession, recordingDurationMs } from "../src/lib/auriscore/recording-session.ts";
import { AnalysisPythonWorker } from "../src/lib/auriscore/analysis-python.server.ts";
import path from "node:path";

function unavailable() { return { schema_version: "organ-analysis-v1", request_id: null, source: "wav", mode: "lung", status: "unavailable",
  quality: { valid: true, reason: null }, backend_version: null, model_version: null, analysis: null,
  errors: [{ code: "MODEL_UNAVAILABLE", message: "No model", component: "lung", retryable: false }] }; }
function analysis() { return { schema_version: "lung-analysis-v1", mode: "lung", quality: { valid: true, reason: null }, model_version: "fictional-fixture",
  supported_classes: ["inhalation", "exhalation", "wheeze"], analyzed_duration_s: 10,
  phase_intervals: [{ label: "inhalation", start_s: .5, end_s: 1.5 }], sound_events: [{ label: "wheeze", start_s: .6, end_s: .9 }],
  class_scores: ["inhalation", "exhalation", "wheeze"].map(label => ({ label, maximum_frame_score: .7, threshold: .5 })),
  respiratory: { respiratory_rate_per_minute: null, inhalation_duration_s: null, exhalation_duration_s: null, ie_ratio: null, complete_cycle_count: 0, reason: "insufficient_complete_cycles" },
  limitations: ["Synthetic engineering fixture"] }; }

test("Lung unavailable and partial contracts never invent unsupported metrics", () => {
  assert.match(analysisNotice(parseOrganAnalysisResult(unavailable(), "lung")), /Model Lung/);
  const value = { ...unavailable(), status: "partial", model_version: "fictional-fixture", analysis: analysis() };
  parseOrganAnalysisResult(value, "lung");
  assert.throws(() => parseOrganAnalysisResult({ ...value, analysis: { ...analysis(), respiratory: { ...analysis().respiratory, ie_ratio: 1 } } }));
  assert.throws(() => parseOrganAnalysisResult({ ...value, analysis: { ...analysis(), sound_events: [{ label: "rhonchi", start_s: 0, end_s: 1 }] } }));
  assert.throws(() => parseOrganAnalysisResult({ ...value, status: "completed", errors: [] }));
  const html = renderToStaticMarkup(createElement(LungResultView, { result: analysis() }));
  assert.match(html, /Belum tersedia/); assert.match(html, /Model belum mendukung/); assert.match(html, /Linimasa/);
});

test("shared and fixed Lung HTTP handlers retain structured unavailable responses", async () => {
  const wav = Buffer.alloc(44); wav.write("RIFF"); wav.write("WAVE", 8);
  for (const fixed of [undefined, "lung"]) {
    const form = new FormData(); form.set("mode", "lung"); form.set("audio", new File([wav], "test.wav"));
    const response = await createAnalysisHandler(fixed, false, async (_bytes, mode) => { assert.equal(mode, "lung"); return unavailable(); })(new Request("http://localhost/api/analysis", { method: "POST", body: form }));
    assert.equal(response.status, 503); parseOrganAnalysisResult(await response.json(), "lung");
  }
});

test("Lung capture uses 30 seconds of samples while Heart remains 10 seconds", async () => {
  assert.equal(recordingDurationMs("lung"), 30000); assert.equal(recordingDurationMs("heart"), 10000);
  let calls = 0;
  const session = new RecordingSession({ async analyze(file, mode) { calls++; assert.equal(mode, "lung"); assert.equal(file.size, 480044); return unavailable(); } });
  session.start("lung", "mock");
  for (let seq = 0; seq < 600; seq++) {
    session.accept({ type: "pcg_packet", seq, ts: seq * 50, samplingRate: 8000, channels: 1, organMode: "mitral", qualityFlag: "good", samples: Array(400).fill(seq % 2 ? 100 : -100) });
    if (seq === 199) assert.equal(session.getSnapshot().phase, "recording");
  }
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(calls, 1); assert.equal(session.getSnapshot().history[0].mode, "lung"); session.dispose();
});

test("real retained Python worker routes Lung without a model and preserves Heart", async () => {
  assert.ok(process.env.AURISCORE_PYTHON, "Configure Python; no skipped backend checks");
  const worker = new AnalysisPythonWorker(process.env.AURISCORE_PYTHON, path.resolve("../AI-Pipeline/scripts/analyze_recording.py"), { ...process.env, AURISCORE_LUNG_PACKAGE: "" });
  const rate = 8000, samples = rate * 6, wav = Buffer.alloc(44 + samples * 2);
  wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8); wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22); wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write("data", 36); wav.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++) wav.writeInt16LE(Math.round(3000 * Math.sin(i * .1)), 44 + i * 2);
  try {
    const lung = await worker.analyze(wav, "lung"); assert.equal(lung.status, "unavailable"); assert.equal(lung.mode, "lung");
    const heart = await worker.analyze(wav, "heart"); assert.equal(heart.mode, "heart");
  } finally { await worker.dispose(); }
});
