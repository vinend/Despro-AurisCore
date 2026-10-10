/** Real HTTP acceptance checks against an isolated production server; synthetic audio only. */
import assert from "node:assert/strict";
import { spawn, execFile } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import nextEnv from "@next/env";
import { parseOrganAnalysisResult } from "../src/lib/auriscore/analysis-result.ts";
import { parseHeartAnalysisResult } from "../src/lib/auriscore/heart-result.ts";

const app = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
nextEnv.loadEnvConfig(app, false, { info() {}, error() {} });
const python = process.env.AURISCORE_PYTHON;
const pipeline = process.env.AURISCORE_PIPELINE_DIR ?? path.resolve(app, "../AI-Pipeline");
assert.ok(python && existsSync(python), "Configure AURISCORE_PYTHON before verification; no skipped Python checks.");
const serverFile = path.join(app, ".next/standalone/server.js");
assert.ok(existsSync(serverFile), "Run npm run build before HTTP verification.");
assert.ok(existsSync(path.join(pipeline, "scripts/analyze_recording.py")), "Configure AURISCORE_PIPELINE_DIR.");

function wav(bpm = 75, silent = false) {
  const rate = 8000, seconds = 8, size = rate * seconds, bytes = Buffer.alloc(44 + size * 2);
  bytes.write("RIFF"); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(rate, 24); bytes.writeUInt32LE(rate * 2, 28);
  bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34); bytes.write("data", 36);
  bytes.writeUInt32LE(size * 2, 40);
  for (let i = 0; i < size; i++) {
    const time = i / rate; let value = 0;
    if (!silent) for (let s1 = .4; s1 < seconds - .5; s1 += 60 / bpm)
      for (const [center, amplitude] of [[s1, .4], [s1 + .3, .28]])
        value += amplitude * Math.sin(2 * Math.PI * 65 * (time - center))
          * Math.exp(-.5 * ((time - center) / .016) ** 2);
    bytes.writeInt16LE(Math.round(value * 32767), 44 + i * 2);
  }
  return bytes;
}
const reservation = createServer();
await new Promise(resolve => reservation.listen(0, "127.0.0.1", resolve));
const port = reservation.address().port;
await new Promise(resolve => reservation.close(resolve));
const base = `http://127.0.0.1:${port}`;
// Empty package settings deliberately exercise the default fail-safe baseline.
// No research candidate is selected, and .env.local is never modified.
const server = spawn(process.execPath, [serverFile], { cwd: app, windowsHide: true, detached: process.platform !== "win32",
  env: { ...process.env, PORT: String(port), HOSTNAME: "127.0.0.1", NODE_ENV: "production",
    AURISCORE_PYTHON: python, AURISCORE_PIPELINE_DIR: pipeline,
    AURISCORE_HEART_PACKAGE: "", AURISCORE_ABDOMEN_PACKAGE: "", AURISCORE_LUNG_PACKAGE: "" }, stdio: ["ignore", "pipe", "pipe"] });
let log = "", startupError;
server.on("error", error => { startupError = error; });
for (const stream of [server.stdout, server.stderr]) stream.on("data", part => { log = (log + part).slice(-8000); });
const checks = [];
async function check(name, run) {
  const start = performance.now();
  try { await run(); checks.push({ name, status: "passed", elapsed_ms: Math.round(performance.now() - start) }); }
  catch (error) { checks.push({ name, status: "failed", error: error.message }); throw error; }
}
async function post(route, mode, data = wav(), filename = "synthetic.wav") {
  const form = new FormData();
  if (mode !== undefined) form.set("mode", mode);
  if (data !== null) form.set("audio", new File([data], filename, { type: "audio/wav" }));
  const response = await fetch(base + route, { method: "POST", body: form, signal: AbortSignal.timeout(100_000) });
  return { response, body: await response.json() };
}
function heart(result, bpm) {
  assert.equal(result.response.status, 200);
  const body = parseOrganAnalysisResult(result.body, "heart");
  assert.equal(body.status, "partial"); assert.equal(body.quality.valid, true);
  assert.ok(Math.abs(body.analysis.rhythm.heart_rate_bpm - bpm) < .1);
  assert.equal(body.analysis.murmur.status, "unavailable");
  assert.equal(body.analysis.murmur.probability, null);
  assert.ok(body.errors.some(error => error.code === "MODEL_UNAVAILABLE"));
  assert.equal(result.response.headers.get("cache-control"), "no-store");
  return body;
}
let failed;
try {
  await check("production page and static assets", async () => {
    const deadline = Date.now() + 30_000;
    let response;
    while (Date.now() < deadline) {
      if (startupError) throw startupError;
      if (server.exitCode !== null) throw new Error(`Server exited: ${log}`);
      try { response = await fetch(base, { signal: AbortSignal.timeout(2000) }); if (response.ok) break; } catch {}
      await delay(200);
    }
    assert.ok(response?.ok, "Production server did not become ready.");
    const html = await response.text();
    const asset = html.match(/src="([^" ]+\/_next\/static\/[^" ]+\.js)"/)?.[1]
      ?? html.match(/src="(\/_next\/static\/[^" ]+\.js)"/)?.[1];
    assert.ok(asset, "Production page has no JavaScript asset.");
    assert.equal((await fetch(new URL(asset, base), { signal: AbortSignal.timeout(5000) })).status, 200);
  });
  await check("Heart WAV reaches real Python DSP with unavailable Murmur", async () => heart(await post("/api/analysis", "heart"), 75));
  await check("concurrent distinct recordings and organs retain correlation", async () => {
    const [a, bowel, b] = await Promise.all([post("/api/analysis", "heart", wav(75)),
      post("/api/abdomen/analyze", undefined), post("/api/analysis", "heart", wav(90))]);
    const first = heart(a, 75), second = heart(b, 90);
    const abdomen = parseOrganAnalysisResult(bowel.body, "abdomen");
    assert.equal(bowel.response.status, 503); assert.equal(abdomen.status, "unavailable");
    assert.equal(abdomen.analysis, null); assert.equal(abdomen.model_version, null);
    assert.equal(new Set([first.request_id, second.request_id, abdomen.request_id]).size, 3);
  });
  await check("shared Abdomen endpoint fails safely without a final model", async () => {
    const result = await post("/api/analysis", "abdomen");
    assert.equal(result.response.status, 503);
    assert.equal(parseOrganAnalysisResult(result.body, "abdomen").analysis, null);
  });
  await check("Lung shared and fixed endpoints stay unavailable before approved training", async () => {
    for (const route of ["/api/analysis", "/api/lung/analyze"]) {
      const output = await post(route, "lung");
      assert.equal(output.response.status, 503);
      const body = parseOrganAnalysisResult(output.body, "lung");
      assert.equal(body.status, "unavailable"); assert.equal(body.analysis, null);
    }
  });
  await check("silent audio rejected for all organs without fabricated branches", async () => {
    for (const mode of ["heart", "abdomen", "lung"]) {
      const result = await post("/api/analysis", mode, wav(75, true));
      assert.equal(result.response.status, 422);
      const body = parseOrganAnalysisResult(result.body, mode);
      assert.equal(body.quality.valid, false); assert.equal(body.analysis, null);
    }
  });
  await check("legacy Heart endpoint preserves valid and invalid contracts", async () => {
    const valid = await post("/api/heart/analyze", undefined);
    assert.equal(valid.response.status, 200);
    assert.equal(parseHeartAnalysisResult(valid.body).rhythm.heart_rate_bpm, 75);
    const silent = await post("/api/heart/analyze", undefined, wav(75, true));
    assert.equal(silent.response.status, 200);
    assert.equal(parseHeartAnalysisResult(silent.body).rhythm, null);
  });
  await check("invalid modes, missing audio and corrupt WAV rejected", async () => {
    for (const [route, mode, data, status] of [
      ["/api/analysis", "spleen", wav(), 400], ["/api/abdomen/analyze", "heart", wav(), 400],
      ["/api/heart/analyze", "abdomen", wav(), 400], ["/api/analysis", "heart", null, 400],
      ["/api/analysis", "heart", Buffer.from("corrupt audio"), 415],
    ]) {
      const result = await post(route, mode, data); assert.equal(result.response.status, status);
      assert.equal(typeof result.body.error, "string"); assert.ok(!/traceback|python\.exe|[A-Z]:\\/i.test(result.body.error));
    }
  });
  await check("oversized upload rejected by real HTTP route", async () => {
    assert.equal((await post("/api/analysis", "heart", Buffer.alloc(17 * 1024 * 1024))).response.status, 413);
  });
  await check("worker still accepts Heart after failures", async () => heart(await post("/api/analysis", "heart", wav(90)), 90));
} catch (error) { failed = error; }
finally {
  // Terminate only the isolated server tree created above, including its Python child.
  if (process.platform === "win32" && server.pid) {
    await new Promise(resolve => execFile(path.join(process.env.SystemRoot ?? "C:\\Windows", "System32/taskkill.exe"),
      ["/PID", String(server.pid), "/T", "/F"], { windowsHide: true, timeout: 5000 }, resolve));
  } else if (server.pid) {
    try { process.kill(-server.pid, "SIGTERM"); } catch (error) { if (error.code !== "ESRCH") throw error; }
  }
  const report = { schema_version: "phase6-http-verification-v1", timestamp_utc: new Date().toISOString(),
    status: failed ? "failed" : "passed", audio: "synthetic 8 kHz mono PCM only", model_packages: "deliberately unset",
    clinical_performance_evaluated: false, checks };
  const output = path.join(app, "artifacts/phase6-http.json");
  mkdirSync(path.dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
  for (const item of checks) console.log(`${item.status}: ${item.name}`);
  console.log(`Evidence: ${output}`);
}
if (failed) { console.error(failed); process.exitCode = 1; }
