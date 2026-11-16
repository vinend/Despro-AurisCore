import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { runInNewContext } from "node:vm";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { parseHeartAnalysisResult } from "../src/lib/auriscore/heart-result.ts";
import { heartDisplay, HEART_SCREENING_NOTICE } from "../src/lib/auriscore/heart-display.ts";
import { HttpHeartAnalysisService, validateHeartFile } from "../src/lib/auriscore/heart-analysis-service.ts";

import { EvidenceTimeline } from "../src/components/auriscore/evidence-timeline.tsx";
const nodeRequire = createRequire(import.meta.url);
const componentSource = readFileSync(new URL("../src/components/auriscore/heart-result-view.tsx", import.meta.url), "utf8");
const componentJs = ts.transpileModule(componentSource, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS,
} }).outputText;
const componentModule = { exports: {} };
runInNewContext(componentJs, {
  module: componentModule,
  exports: componentModule.exports,
  require: (name) => name === "@/lib/auriscore/heart-display"
    ? { heartDisplay, HEART_SCREENING_NOTICE } : name === "./evidence-timeline" ? { EvidenceTimeline } : nodeRequire(name),
});
const { HeartResultView } = componentModule.exports;

function validResult() {
  return {
    schema_version: "heart-analysis-v1", mode: "heart",
    quality: { valid: true, score: null, reason: null },
    rhythm: { algorithm_version: "heart-dsp-prototype-0.1.0", heart_rate_bpm: 75,
      label: "normal", irregular: false, interval_std_ms: 0, beat_intervals_ms: [800, 800], usable_intervals: 2 },
    cardiac_events: { algorithm_version: "heart-dsp-prototype-0.1.0", status: "paired_candidates",
      candidate_times_s: [0.4, 0.7, 1.2], s1_times_s: [0.4, 1.2, 2], s2_times_s: [0.7, 1.5],
      s3_candidates_s: [], s4_candidates_s: [], systolic_intervals: [], diastolic_intervals: [],
      systolic_interval_ms: 300, diastolic_interval_ms: 500 },
    murmur: { status: "unavailable", model_version: null, preprocessing_version: null,
      threshold_version: null, probability: null, threshold: null, label: null },
    visualization: { waveform_available: true, spectrogram_available: false,
      event_annotations_available: true },
  };
}

test("heart-analysis-v1 valid result preserves DSP fields and unavailable Murmur", () => {
  const result = parseHeartAnalysisResult(validResult());
  const display = heartDisplay(result);
  assert.equal(display.bpm, "75.0");
  assert.equal(display.s1, "3 kandidat");
  assert.equal(display.systole, "300 ms");
  assert.equal(display.murmur, "Analisis Murmur belum tersedia");
  assert.match(HEART_SCREENING_NOTICE, /bukan diagnosis/);
});

test("result component renders real fields, unavailable Murmur, and screening notice", () => {
  const html = renderToStaticMarkup(createElement(HeartResultView, {
    result: parseHeartAnalysisResult(validResult()),
  }));
  assert.match(html, /75\.0 BPM/);
  assert.match(html, /300 ms/);
  assert.match(html, /Analisis Murmur belum tersedia/);
  assert.match(html, /bukan diagnosis/);
});

test("invalid audio stays branchless and shows the quality reason", () => {
  const input = validResult();
  input.quality = { valid: false, score: null, reason: "silent_signal" };
  input.rhythm = null;
  input.cardiac_events = null;
  input.murmur = null;
  const display = heartDisplay(parseHeartAnalysisResult(input));
  assert.equal(display.reason, "Sinyal hening atau terlalu lemah.");
  assert.equal(display.bpm, "Belum tersedia");
  const html = renderToStaticMarkup(createElement(HeartResultView, {
    result: parseHeartAnalysisResult(input),
  }));
  assert.match(html, /Sinyal hening atau terlalu lemah/);
  assert.doesNotMatch(html, /Denyut jantung/);
  input.rhythm = validResult().rhythm;
  assert.throws(() => parseHeartAnalysisResult(input), /heart-analysis-v1/);
});

test("missing BPM and insufficient events never invent a rate", () => {
  const input = validResult();
  input.rhythm.heart_rate_bpm = null;
  input.rhythm.label = "unknown";
  input.rhythm.irregular = null;
  input.cardiac_events.status = "insufficient_evidence";
  input.cardiac_events.s1_times_s = [];
  input.cardiac_events.s2_times_s = [];
  input.cardiac_events.systolic_interval_ms = null;
  input.cardiac_events.diastolic_interval_ms = null;
  const display = heartDisplay(parseHeartAnalysisResult(input));
  assert.equal(display.bpm, "Belum cukup data");
  assert.equal(display.s1, "Belum cukup bukti");
  assert.equal(display.s3, "Belum cukup bukti");
  assert.equal(display.irregular, "Belum dievaluasi");
});

test("interval descriptors render without promoting legacy irregular flags", () => {
  const input = validResult();
  input.rhythm.irregular = true;
  input.rhythm.interval_std_ms = 40;
  input.rhythm.interval_cv = 0.05;
  const result = parseHeartAnalysisResult(input);
  const display = heartDisplay(result);
  assert.equal(display.intervalSd, "40.0 ms");
  assert.equal(display.intervalCv, "0.050");
  const html = renderToStaticMarkup(createElement(HeartResultView, { result }));
  assert.match(html, /Belum dievaluasi/);
  assert.doesNotMatch(html, /Indikasi interval tidak teratur/);
  delete input.rhythm.interval_cv;
  assert.equal(heartDisplay(parseHeartAnalysisResult(input)).intervalCv, "Belum tersedia");
});

test("available Murmur shows generic model version and refuses conflicting label", () => {
  const input = validResult();
  input.murmur = { status: "available", model_version: "frozen-model-vX",
    preprocessing_version: "prep-v1", threshold_version: "threshold-v1",
    probability: 0.82, threshold: 0.3, label: "present" };
  const result = parseHeartAnalysisResult(input);
  assert.equal(heartDisplay(result).murmur, "Murmur diduga");
  assert.equal(result.murmur.model_version, "frozen-model-vX");
  input.murmur.label = "absent";
  assert.throws(() => parseHeartAnalysisResult(input), /heart-analysis-v1/);
});

test("malformed response or unsupported schema fails closed", () => {
  assert.throws(() => parseHeartAnalysisResult({}), /heart-analysis-v1/);
  const input = validResult();
  input.schema_version = "legacy";
  assert.throws(() => parseHeartAnalysisResult(input), /heart-analysis-v1/);
});

test("file-simulator service posts WAV and parses the returned contract", async () => {
  const file = new File(["RIFF....WAVE"], "sample.wav", { type: "audio/wav" });
  const service = new HttpHeartAnalysisService(async (url, options) => {
    assert.equal(url, "/api/heart/analyze");
    assert.equal(options.method, "POST");
    assert.equal(options.body.get("audio"), file);
    return Response.json(validResult());
  });
  assert.equal((await service.analyze(file)).rhythm.heart_rate_bpm, 75);
});

test("file-simulator errors are explicit", async () => {
  assert.match(validateHeartFile(null), /Pilih/);
  assert.match(validateHeartFile(new File([], "empty.wav")), /kosong/);
  assert.match(validateHeartFile(new File(["data"], "wrong.mp3")), /\.wav/);
  const file = new File(["RIFF....WAVE"], "sample.wav");
  await assert.rejects(() => new HttpHeartAnalysisService(async () => Response.json({ error: "WAV rusak" }, { status: 422 })).analyze(file), /WAV rusak/);
  await assert.rejects(() => new HttpHeartAnalysisService(async () => Response.json({ bogus: true })).analyze(file), /heart-analysis-v1/);
  await assert.rejects(() => new HttpHeartAnalysisService(async () => { throw new Error("offline"); }).analyze(file), /tidak dapat dihubungi/);
});

test("Heart evidence retains overlapping windows, marks reference scores and rejects bad times", () => {
  const input = validResult();
  input.murmur = {status: "available", model_version: "fixture", preprocessing_version: "fixture",
    threshold_version: "fixture", probability: .6, threshold: .5, label: "present", window_count: 2,
    temporal_evidence: {version: "heart-window-evidence-v1", kind: "exploratory_window_scores",
      threshold_scope: "recording_reference_only", duration_s: 8, discarded_tail_s: .5,
      windows: [{start_s: 0, end_s: 5, score: .8}, {start_s: 2.5, end_s: 7.5, score: .4}]}};
  const output = parseHeartAnalysisResult(input);
  const html = renderToStaticMarkup(createElement(HeartResultView, {result: output}));
  assert.match(html, /0.00–5.00 detik/);
  assert.match(html, /skor 0.800/);
  assert.doesNotMatch(html, /2.50–7.50 detik/);
  assert.match(html, /belum tervalidasi/);
  assert.match(html, /0.50 detik tidak dianalisis/);
  input.murmur.temporal_evidence.windows[0].end_s = 9;
  assert.throws(() => parseHeartAnalysisResult(input));
});

test("empty Heart temporal evidence flags cannot imply a confirmed negative result", () => {
  const html = renderToStaticMarkup(createElement(EvidenceTimeline, {
    title:"Uji rentang", duration:10, intervals:[], explanation:"Skor eksploratif",
    emptyMessage:"Tidak ada jendela yang mencapai ambang."
  }));
  assert.match(html,/Tidak ada jendela/);
  assert.doesNotMatch(html,/bg-amber-600/);
});

test("live evidence uses stream seconds after a nonzero window offset", () => {
  const html = renderToStaticMarkup(createElement(EvidenceTimeline, {
    title: "Live candidates", duration: 10, timeOffset: 30,
    intervals: [{start_s: 2, end_s: 7, label: "Kandidat", score: .8}],
    explanation: "Uji", emptyMessage: "Kosong",
  }));
  assert.match(html, /32\.00–37\.00 detik/);
  assert.match(html, /30\.00 detik/);
  assert.match(html, /40\.00 detik/);
});
