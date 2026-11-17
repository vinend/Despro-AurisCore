import test from "node:test";
import assert from "node:assert/strict";
import { LivePcmWindow, LIVE_WINDOW_SAMPLES } from "../src/lib/auriscore/live-analysis.ts";
import { createLiveAnalysisHandler } from "../src/lib/auriscore/live-analysis-route.server.ts";

const packet = (seq, value = seq) => ({ type: "pcg_packet", seq, ts: seq * 50,
  samplingRate: 8000, channels: 1, organMode: "mitral", qualityFlag: "unknown", samples: Array(400).fill(value) });
for (const mode of ["heart", "lung", "abdomen"]) {
  test(`${mode}: rolling PCM reaches the analyzer unchanged`, async () => {
    const buffer = new LivePcmWindow(mode);
    const blocks = LIVE_WINDOW_SAMPLES[mode] / 400;
    for (let seq = 0; seq < blocks; seq++) buffer.accept(packet(seq, seq - 1000));
    assert.equal(buffer.take().startSample, 0);
    assert.equal(buffer.take(), null);
    for (let seq = blocks; seq < blocks + 20; seq++) buffer.accept(packet(seq, seq - 1000));
    const next = buffer.take();
    assert.equal(next.startSample, 8000);
    const handler = createLiveAnalysisHandler(async (samples, actualMode) => {
      assert.equal(actualMode, mode);
      assert.equal(samples.length, LIVE_WINDOW_SAMPLES[mode]);
      assert.equal(samples[0], -980);
      assert.equal(samples.at(-1), blocks + 19 - 1000);
      return { mode };
    });
    const request = pcm => new Request(`http://localhost/api/analysis/live?mode=${mode}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream", "X-AurisCore-Start-Sample": "8000" }, body: pcm,
    });
    const response = await handler(request(next.pcm));
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { startSample: 8000, endSample: next.endSample, result: { mode } });
    assert.equal((await handler(request(next.pcm.slice(2)))).status, 400);
  });
}
test("sequence gaps require a fresh window; duplicates add no samples", () => {
  const buffer = new LivePcmWindow("abdomen");
  for (let seq = 0; seq < 99; seq++) buffer.accept(packet(seq));
  buffer.accept(packet(98));
  assert.equal(buffer.take(), null);
  assert.equal(buffer.accept(packet(100, -123)), "reset");
  for (let seq = 101; seq < 199; seq++) buffer.accept(packet(seq));
  assert.equal(buffer.take(), null);
  buffer.accept(packet(199));
  const window = buffer.take();
  assert.equal(window.startSample, 0);
  assert.equal(new DataView(window.pcm).getInt16(0, true), -123);
});

test("cloud live analysis requires an operator token and forwards original PCM bytes", async t => {
  const env = { AURISCORE_CLOUD_ANALYSIS: "1", AURISCORE_OPERATOR_TOKEN: "test-operator-token",
    AURISCORE_INFERENCE_URL: "https://inference.example", AURISCORE_INFERENCE_TOKEN: "test-inference-token" };
  for (const [name, value] of Object.entries(env)) {
    const previous = process.env[name];
    process.env[name] = value;
    t.after(() => { if (previous === undefined) delete process.env[name]; else process.env[name] = previous; });
  }
  const pcm = new Uint8Array(LIVE_WINDOW_SAMPLES.lung * 2);
  pcm.set([0x12, 0x90]);
  const handler = createLiveAnalysisHandler(() => assert.fail("Cloud used the subprocess"));
  const request = token => new Request("http://localhost/api/analysis/live?mode=lung", { method: "POST",
    headers: { "Content-Type": "application/octet-stream", "X-AurisCore-Start-Sample": "0",
      ...(token ? { "X-AurisCore-Operator-Token": token } : {}) }, body: pcm });
  assert.equal((await handler(request())).status, 401);
  const fetch = t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(String(url), "https://inference.example/v1/analysis/lung/pcm");
    assert.equal(options.headers.Authorization, "Bearer test-inference-token");
    assert.deepEqual(options.body, pcm);
    return new Response(null, { status: 429 });
  });
  assert.equal((await handler(request(env.AURISCORE_OPERATOR_TOKEN))).status, 429);
  assert.equal(fetch.mock.callCount(), 1);
});
