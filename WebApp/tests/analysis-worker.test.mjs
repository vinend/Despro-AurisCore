import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { AnalysisPythonWorker } from "../src/lib/auriscore/analysis-python.server.ts";
import { createAnalysisHandler } from "../src/lib/auriscore/analysis-route.server.ts";

const python = process.env.AURISCORE_PYTHON ?? path.join(process.env.USERPROFILE, ".codex/envs/auriscore-audit/Scripts/python.exe");
const pipeline = path.resolve("../AI-Pipeline");
const env = { ...process.env, AURISCORE_HEART_PACKAGE: "", AURISCORE_ABDOMEN_PACKAGE: "" };
function cleanup(directory) {
  const resolved = path.resolve(directory);
  assert.equal(path.dirname(resolved), path.resolve(tmpdir()));
  assert.ok(path.basename(resolved).startsWith("auriscore-"));
  // Windows retains the child's working-directory handle briefly after kill().
  rmSync(resolved, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
}
function wav(seconds = 8, silent = false) {
  const sr = 8000, size = sr * seconds, bytes = Buffer.alloc(44 + size * 2);
  bytes.write("RIFF"); bytes.writeUInt32LE(bytes.length - 8, 4); bytes.write("WAVEfmt ", 8);
  bytes.writeUInt32LE(16, 16); bytes.writeUInt16LE(1, 20); bytes.writeUInt16LE(1, 22);
  bytes.writeUInt32LE(sr, 24); bytes.writeUInt32LE(sr * 2, 28); bytes.writeUInt16LE(2, 32); bytes.writeUInt16LE(16, 34);
  bytes.write("data", 36); bytes.writeUInt32LE(size * 2, 40);
  for (let i = 0; i < size; i++) {
    const time = i / sr; let value = 0;
    if (!silent) for (let s1 = .4; s1 < seconds - .5; s1 += .8)
      for (const [center, amplitude] of [[s1, .4], [s1 + .3, .28]])
        value += amplitude * Math.sin(2 * Math.PI * 65 * (time - center)) * Math.exp(-.5 * ((time - center) / .016) ** 2);
    bytes.writeInt16LE(Math.round(value * 32767), 44 + i * 2);
  }
  return bytes;
}
const options = { skip: !existsSync(python), timeout: 90_000 };
test("real worker recovers after active cancellation and idle shutdown", options, async () => {
  const worker = new AnalysisPythonWorker(python, path.join(pipeline, "scripts/analyze_recording.py"), env, 30_000, 8, 30);
  try {
    const controller = new AbortController();
    const pending = worker.analyze(wav(), "heart", controller.signal);
    setTimeout(() => controller.abort(), 10);
    await assert.rejects(pending, e => e.httpStatus === 499);
    assert.equal((await worker.analyze(wav(), "heart")).analysis.rhythm.heart_rate_bpm, 75);
    const pid = worker.child.pid;
    await new Promise(resolve => setTimeout(resolve, 100));
    assert.equal(worker.child, null);
    assert.equal((await worker.analyze(wav(), "heart")).analysis.rhythm.heart_rate_bpm, 75);
    assert.notEqual(worker.child.pid, pid);
  } finally { await worker.dispose(); }
});
test("retained real Python worker correlates concurrent Heart/Abdomen requests and rejects silence", options, async () => {
  const worker = new AnalysisPythonWorker(python, path.join(pipeline, "scripts/analyze_recording.py"), env);
  try {
    const heart = await worker.analyze(wav(), "heart"); const pid = worker.child.pid;
    assert.equal(heart.analysis.rhythm.heart_rate_bpm, 75); assert.equal(heart.status, "partial");
    const [bowel, again, silence] = await Promise.all([worker.analyze(wav(), "abdomen"),
      worker.analyze(wav(), "heart"), worker.analyze(wav(5, true), "heart")]);
    assert.equal(bowel.status, "unavailable"); assert.equal(again.analysis.rhythm.heart_rate_bpm, 75);
    assert.equal(silence.status, "error"); assert.equal(silence.analysis, null);
    assert.equal(worker.child.pid, pid); assert.notEqual(again.request_id, heart.request_id);
  } finally { await worker.dispose(); }
});

function stub(directory, behavior) {
  const file = path.join(directory, "scripts/stub.py"); mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `import json,sys,time\nfor line in sys.stdin:\n r=json.loads(line)\n ${behavior}\n`);
  return file;
}
test("worker queue, timeout, cancellation and malformed output fail safely", options, async () => {
  const directory = mkdtempSync(path.join(tmpdir(), "auriscore-worker-"));
  try {
    let worker = new AnalysisPythonWorker(python, stub(directory, "time.sleep(5)"), env, 200, 1);
    const slow = worker.analyze(wav(), "heart");
    await assert.rejects(worker.analyze(wav(), "heart"), e => e.httpStatus === 503);
    await assert.rejects(slow, e => e.httpStatus === 504); await worker.dispose();
    worker = new AnalysisPythonWorker(python, stub(directory, "time.sleep(5)"), env, 5000);
    const controller = new AbortController(); const pending = worker.analyze(wav(), "heart", controller.signal);
    setTimeout(() => controller.abort(), 100);
    await assert.rejects(pending, e => e.httpStatus === 499); await worker.dispose();
    worker = new AnalysisPythonWorker(python, stub(directory, "print('private invalid result',flush=True)"), env, 5000);
    await assert.rejects(worker.analyze(wav(), "heart"), e => e.httpStatus === 502 && !e.message.includes("private"));
    await worker.dispose();
  } finally { cleanup(directory); }
});

test("configured real Heart and A005 packages flow through the existing HTTP handler", options, async () => {
  const directory = mkdtempSync(path.join(tmpdir(), "auriscore-model-fixture-"));
  try {
    // Both decisions/evaluations are FICTIONAL fixtures. They are never deployed.
    const code = `import runpy,sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(sys.argv[1])/'src'))\nroot=Path(sys.argv[1]);tmp=Path(sys.argv[2])\nfor organ in ('heart','abdomen'):\n d=runpy.run_path(str(root/'tests'/('test_'+organ+'_inference.py')))\n p=tmp/organ;p.mkdir()\n inputs=d['inputs'].__wrapped__(p)\n d['deployment'].__wrapped__(inputs)\n`;
    const prepared = spawnSync(python, ["-c", code, pipeline, directory], { env, encoding: "utf8", timeout: 60_000 });
    assert.equal(prepared.status, 0, prepared.stderr);
    const worker = new AnalysisPythonWorker(python, path.join(pipeline, "scripts/analyze_recording.py"),
      { ...env, AURISCORE_HEART_PACKAGE: path.join(directory, "heart/test-package"),
        AURISCORE_ABDOMEN_PACKAGE: path.join(directory, "abdomen/fixture-package") });
    try {
      const handler = createAnalysisHandler(undefined, false, (data, mode, signal) => worker.analyze(data, mode, signal));
      for (const mode of ["heart", "abdomen", "heart"]) {
        const form = new FormData(); form.set("mode", mode); form.set("audio", new File([wav()], "fixture.wav"));
        const response = await handler(new Request("http://localhost/api/analysis", { method: "POST", body: form }));
        assert.equal(response.status, 200); const body = await response.json();
        assert.equal(body.mode, mode); assert.equal(body.status, "completed");
        if (mode === "heart") { assert.equal(body.analysis.murmur.status, "available"); assert.equal(body.analysis.rhythm.heart_rate_bpm, 75); }
        else { assert.equal(body.analysis.activity.window_count, 2); assert.equal(body.analysis.bowel_rate_per_minute, null); }
      }
    } finally { await worker.dispose(); }
  } finally { cleanup(directory); }
});
