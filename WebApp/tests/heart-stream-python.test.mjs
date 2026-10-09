import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { PcgCaptureBuffer, pcmToWavFile } from "../src/lib/auriscore/heart-audio-source.ts";
import { parseHeartAnalysisResult } from "../src/lib/auriscore/heart-result.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const pipeline = path.resolve(here, "../../AI-Pipeline");
const python = process.env.AURISCORE_PYTHON ?? path.join(pipeline, ".runtime/python/python.exe");

test("synthetic mock packets become real CPU Heart DSP heart-analysis-v1 output", { skip: !existsSync(python) }, async () => {
  const rate = 8000;
  const capture = new PcgCaptureBuffer();
  capture.start();
  for (let seq = 0; seq < 160; seq++) {
    const samples = [];
    for (let j = 0; j < 400; j++) {
      const time = (seq * 400 + j) / rate;
      let value = 0;
      for (let s1 = .4; s1 < 7.2; s1 += .8) {
        for (const [center, amplitude] of [[s1, 1], [s1 + .3, .7]]) {
          const dt = time - center;
          value += amplitude * Math.sin(2 * Math.PI * 65 * dt) * Math.exp(-.5 * (dt / .016) ** 2);
        }
      }
      samples.push(Math.round(value * 16000));
    }
    capture.accept({ type: "pcg_packet", seq, ts: seq * 50, samplingRate: rate,
      organMode: "mitral", qualityFlag: "good", channels: 1, samples });
  }
  const wav = Buffer.from(await pcmToWavFile(capture.stop("mock")).arrayBuffer());
  const result = spawnSync(python, [path.join(pipeline, "scripts/analyze_heart_wav.py"), "--stdin"],
    { cwd: pipeline, input: wav, encoding: "utf8", timeout: 30000,
      env: { ...process.env, CUDA_VISIBLE_DEVICES: "-1" } });
  assert.equal(result.status, 0, result.stderr);
  const heart = parseHeartAnalysisResult(JSON.parse(result.stdout));
  assert.equal(heart.quality.valid, true);
  assert.equal(heart.rhythm.heart_rate_bpm, 75);
  assert.equal(heart.murmur.status, "unavailable");
});
