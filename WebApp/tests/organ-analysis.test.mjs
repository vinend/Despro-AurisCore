import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { parseOrganAnalysisResult, analysisNotice } from "../src/lib/auriscore/analysis-result.ts";
import { HttpOrganAnalysisService, analyzeOrganAudio } from "../src/lib/auriscore/organ-analysis-service.ts";
import { createAnalysisHandler } from "../src/lib/auriscore/analysis-route.server.ts";
import { RecordingSession } from "../src/lib/auriscore/recording-session.ts";
import { PcgCaptureBuffer } from "../src/lib/auriscore/heart-audio-source.ts";

function result(mode = "abdomen", status = "completed") {
  const value = { schema_version: "organ-analysis-v1", request_id: "test", mode, source: "wav", status,
    quality: { valid: true, reason: null }, backend_version: "fixture", model_version: "fixture",
    errors: [], analysis: { schema_version: "abdomen-analysis-v1", mode: "abdomen", quality: { valid: true, reason: null },
      activity: { target: "bowel_sound_activity", inference_unit: "window", aggregation: "none", model_version: "fixture",
        preprocessing_version: "fixture", threshold_version: "fixture", threshold: .5, score_kind: "uncalibrated_sigmoid",
        probability_is_calibrated: false, window_seconds: 5, overlap: .5,
        windows: [{ start_s: 0, end_s: 5, score: .7, label: "present" }, { start_s: 2.5, end_s: 7.5, score: .2, label: "absent" }],
        window_count: 2, active_window_count: 1, active_window_fraction: .5, analyzed_duration_s: 7.5, discarded_tail_s: 0 },
      bowel_events: null, bowel_rate_per_minute: null, bowel_rate_variability: null, pattern_categories: null } };
  if (status === "unavailable" || status === "error") {
    value.analysis = null; value.errors = [{ code: status === "error" ? "LOW_SIGNAL_QUALITY" : "MODEL_UNAVAILABLE",
      message: "Fixture", component: "bowel_activity", retryable: false }];
    value.quality.valid = status !== "error";
  }
  return value;
}
function wavFile() { return new File([Buffer.from("RIFF0000WAVEtest")], "recording.wav", { type: "audio/wav" }); }
function request(mode = "abdomen", file = wavFile()) {
  const form = new FormData(); form.set("mode", mode); form.set("audio", file);
  return new Request("http://localhost/api/analysis", { method: "POST", body: form });
}
function packet(seq, organMode = "mitral") { return { type: "pcg_packet", seq, ts: seq * 50,
  samplingRate: 8000, organMode, qualityFlag: "good", channels: 1, samples: Array(400).fill(120) }; }

test("Abdomen contract keeps window activity separate from event rates", () => {
  const parsed = parseOrganAnalysisResult(result(), "abdomen");
  assert.equal(parsed.analysis.activity.active_window_fraction, .5);
  assert.equal(parsed.analysis.bowel_rate_per_minute, null);
  for (const mutate of [v => v.analysis.activity.windows[0].label = "absent",
    v => v.analysis.activity.active_window_fraction = .9, v => v.analysis.activity.windows[1].start_s = 0,
    v => v.analysis.bowel_rate_per_minute = 12, v => v.mode = "heart", v => v.status = "partial",
    v => v.analysis.activity.windows[0].score = NaN, v => v.quality.valid = false]) {
    const bad = result(); mutate(bad); assert.throws(() => parseOrganAnalysisResult(bad, "abdomen"));
  }
});
test("unavailable and invalid audio retain reasons without classifications", () => {
  for (const status of ["unavailable", "error"]) {
    const parsed = parseOrganAnalysisResult(result("abdomen", status));
    assert.equal(parsed.analysis, null); assert.ok(analysisNotice(parsed));
  }
});
test("shared HTTP client posts mode and preserves structured 503 and 422", async () => {
  for (const [status, httpStatus] of [["completed", 200], ["unavailable", 503], ["error", 422]]) {
    const service = new HttpOrganAnalysisService(async (url, init) => {
      assert.equal(url, "/api/analysis"); assert.equal(init.body.get("mode"), "abdomen");
      assert.equal(init.body.get("audio").name, "recording.wav");
      return Response.json(result("abdomen", status), { status: httpStatus });
    });
    assert.equal((await service.analyze(wavFile(), "abdomen")).status, status);
  }
  const service = new HttpOrganAnalysisService(async () => Response.json({ error: "Unavailable" }, { status: 503 }));
  await assert.rejects(service.analyze(wavFile(), "abdomen"), /Unavailable/);
});
test("browser fetch retains its global receiver", async () => {
  const service = new HttpOrganAnalysisService(async function () {
    assert.equal(this, globalThis);
    return Response.json(result());
  });
  await service.analyze(wavFile(), "abdomen");
});
test("PCM and WAV inputs converge on the same organ service", async () => {
  const capture = new PcgCaptureBuffer(); capture.start(); capture.accept(packet(0));
  const service = { analyze: async (file, mode) => { assert.equal(file.type, "audio/wav"); assert.equal(mode, "abdomen"); return result(); } };
  await analyzeOrganAudio({ kind: "pcm", audio: capture.stop("websocket-device") }, "abdomen", service);
});
test("route dispatch and fixed endpoint mode reject mismatches", async () => {
  const handler = createAnalysisHandler(undefined, false, async (_, mode) => { assert.equal(mode, "abdomen"); return result(); });
  assert.equal((await handler(request())).status, 200);
  assert.equal((await handler(request("spleen"))).status, 400);
  const fixed = createAnalysisHandler("heart", true, async () => { throw Error("Must not run"); });
  assert.equal((await fixed(request())).status, 400);
  assert.equal((await handler(request("abdomen", new File(["invalid"], "record.wav")))).status, 415);
});
test("route maps model unavailability and invalid audio to typed responses", async () => {
  for (const [state, http] of [["unavailable", 503], ["error", 422]]) {
    const handler = createAnalysisHandler(undefined, false, async () => result("abdomen", state));
    const response = await handler(request());
    assert.equal(response.status, http); assert.equal((await response.json()).status, state);
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
});
test("route bounds the actual multipart body without trusting content-length", async () => {
  const handler = createAnalysisHandler(undefined, false, async () => { throw Error("Must not analyze"); });
  const body = new ReadableStream({ start(controller) {
    controller.enqueue(new Uint8Array(17 * 1024 * 1024)); controller.close();
  } });
  const oversized = new Request("http://localhost/api/analysis", { method: "POST", body, duplex: "half",
    headers: { "content-type": "multipart/form-data; boundary=fixture" } });
  assert.equal(oversized.headers.get("content-length"), null);
  assert.equal((await handler(oversized)).status, 413);
});
test("legacy Heart route retains branchless invalid quality shape", async () => {
  const response = await createAnalysisHandler("heart", true, async () => result("heart", "error"))(request("heart"));
  const body = await response.json(); assert.equal(response.status, 200);
  assert.equal(body.schema_version, "heart-analysis-v1"); assert.equal(body.rhythm, null); assert.equal(body.quality.valid, false);
});
test("real recording freezes its mode, invokes audio analysis once and stores status", async () => {
  let calls = 0;
  const session = new RecordingSession({ analyze: async (file, mode) => { calls++; assert.equal(mode, "abdomen");
    assert.ok(file.size > 44); return result("abdomen", "unavailable"); } });
  session.start("abdomen", "websocket-device"); session.start("heart", "mock");
  session.accept(packet(0)); await Promise.all([session.stop(), session.stop()]);
  assert.equal(calls, 1); assert.equal(session.getSnapshot().phase, "done");
  assert.equal(session.getSnapshot().history[0].mode, "abdomen");
  assert.equal(session.getSnapshot().history[0].result.status, "unavailable"); session.dispose();
});
test("packet loss, changed position and disconnect never call inference", async () => {
  for (const action of [s => s.accept(packet(2)), s => s.accept(packet(1, "aortic")), s => s.disconnect()]) {
    let calls = 0; const session = new RecordingSession({ analyze: async () => { calls++; return result(); } });
    session.start("heart", "websocket-device"); session.accept(packet(0)); action(session); await session.stop();
    assert.equal(calls, 0); assert.equal(session.getSnapshot().phase, "error"); assert.equal(session.getSnapshot().result, null);
    session.dispose();
  }
});
test("reset cancels inference and discards late results", async () => {
  let resolve, signal;
  const session = new RecordingSession({ analyze: (file, mode, abort) => { signal = abort; return new Promise(r => { resolve = r; }); } });
  session.start("abdomen", "mock"); session.accept(packet(0)); const pending = session.stop(); session.reset();
  assert.equal(signal.aborted, true); resolve(result()); await pending;
  assert.equal(session.getSnapshot().result, null); assert.equal(session.getSnapshot().history.length, 0);
});
test("Abdomen result view renders acoustic windows and unavailable states", () => {
  const require = createRequire(import.meta.url);
  const source = readFileSync(new URL("../src/components/auriscore/organ-result-view.tsx", import.meta.url), "utf8");
  const js = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS } }).outputText;
  const module = { exports: {} };
  runInNewContext(js, { module, exports: module.exports, require: name => name.includes("analysis-result")
    ? { analysisNotice } : name === "./heart-result-view" ? { HeartResultView: () => null }
    : name === "./lung-result-view" ? { LungResultView: () => null } : require(name) });
  const View = module.exports.OrganResultView;
  const html = renderToStaticMarkup(createElement(View, { result: parseOrganAnalysisResult(result()) }));
  assert.match(html, /50\.0%/); assert.match(html, /Aktivitas terdeteksi/); assert.match(html, /bukan diagnosis/);
  assert.match(html, /belum dikalibrasi/); assert.doesNotMatch(html, /BPM/);
  const unavailable = renderToStaticMarkup(createElement(View, { result: parseOrganAnalysisResult(result("abdomen", "unavailable")) }));
  assert.match(unavailable, /belum tersedia/); assert.doesNotMatch(unavailable, /50\.0%/);
});
