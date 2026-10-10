import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { WebSocket } from "ws";
import { createDeviceGateway } from "../gateway.ts";
import { encodeAudioFrame, decodeAudioFrame, AudioContinuity } from "../../../src/lib/auriscore/device-protocol.ts";
const token = "fictional-test-pairing-12345", origin = "http://localhost:3000";
const hello = { type: "device_hello", protocol: 2, device: "test-esp32", fw: "engineering-test", source: "engineering",
  streamId: 42, samplingRate: 8000, channels: 1, encoding: "pcm16le" };
function inbox(ws) {
  const queue = [], waiters = [];
  ws.on("message", (raw, binary) => { const value = binary ? new Uint8Array(raw) : JSON.parse(raw.toString());
    const index = waiters.findIndex(w => w.matches(value));
    if (index >= 0) { const [w] = waiters.splice(index, 1); clearTimeout(w.timer); w.resolve(value); } else queue.push(value); });
  return matches => {
    const index = queue.findIndex(matches); if (index >= 0) return Promise.resolve(queue.splice(index, 1)[0]);
    return new Promise((resolve, reject) => { const w = { matches, resolve, timer: null }; waiters.push(w);
      w.timer = setTimeout(() => { waiters.splice(waiters.indexOf(w), 1); reject(Error("Message timeout")); }, 4000); });
  };
}
async function peer(base, role) {
  const ws = new WebSocket(base + "/" + role, { origin }), next = inbox(ws); await once(ws, "open");
  ws.send(JSON.stringify({ type: "authenticate", token })); await next(v => v.type === "authenticated"); return { ws, next };
}
const frame = (seq = 0, firstSample = seq * 400) => encodeAudioFrame({ streamId: 42, seq, firstSample, flags: 0,
  samples: Int16Array.from({ length: 400 }, (_, i) => i - 200) });
test("binary golden layout, signed values, safe sample clock, gaps and duplicate rules", () => {
  const bytes = frame(), decoded = decodeAudioFrame(bytes); assert.equal(bytes.length, 832);
  assert.equal(Buffer.from(bytes.slice(0, 8)).toString("hex"), "4155524902002000");
  assert.equal(decoded.samples[0], -200); assert.equal(decoded.samples[399], 199);
  const continuity = new AudioContinuity(42); assert.equal(continuity.accept(decoded), true);
  assert.equal(continuity.accept(decoded), false); assert.throws(() => continuity.accept(decodeAudioFrame(frame(2))), /missing/);
  const wrong = frame(); wrong[31] = 9; assert.throws(() => decodeAudioFrame(wrong));
  assert.throws(() => decodeAudioFrame(bytes.slice(1))); const overflow = frame(); overflow[5] = 1;
  assert.throws(() => new AudioContinuity(42).accept(decodeAudioFrame(overflow)), /overflow/);
});
test("gateway routes exact PCM and acknowledged commands, then fails missing audio without substitution", { timeout: 15_000 }, async () => {
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0 }); const address = await gateway.listen();
  const base = `ws://127.0.0.1:${address.port}`;
  try {
    const device = await peer(base, "device"); device.ws.send(JSON.stringify(hello));
    const browser = await peer(base, "browser"); assert.deepEqual(await browser.next(v => v.type === "device_hello"), hello);
    browser.ws.send(JSON.stringify({ type: "command", id: "start-1", command: "start_stream" }));
    const command = await device.next(v => v.type === "command");
    device.ws.send(JSON.stringify({ type: "command_ack", ...command, type: "command_ack", ok: true }));
    await browser.next(v => v.type === "command_ack");
    device.ws.send(frame()); assert.deepEqual(await browser.next(v => v instanceof Uint8Array), frame());
    device.ws.send(frame(2)); assert.match((await browser.next(v => v.type === "device_state" && v.status === "error")).reason, /interrupted/);
    await browser.next(v => v.type === "device_state" && v.status === "offline");
  } finally { await gateway.close(); }
});
test("gateway rejects wrong origin/authentication and marks stalled device unavailable", { timeout: 15_000 }, async () => {
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0, staleMs: 50 }); const address = await gateway.listen();
  const base = `ws://127.0.0.1:${address.port}`;
  try {
    const bad = new WebSocket(base + "/browser", { origin: "http://untrusted.example" });
    const [error] = await once(bad, "error"); assert.match(error.message, /403/);
    const wrong = new WebSocket(base + "/device"); await once(wrong, "open");
    wrong.send(JSON.stringify({ type: "authenticate", token: "incorrect" })); const [code] = await once(wrong, "close"); assert.equal(code, 1008);
    const device = await peer(base, "device"); device.ws.send(JSON.stringify(hello));
    const browser = await peer(base, "browser"); await browser.next(v => v.type === "device_hello");
    browser.ws.send(JSON.stringify({ type: "command", id: "start", command: "start_stream" }));
    await device.next(v => v.type === "command"); device.ws.send(JSON.stringify({ type: "command_ack", id: "start", command: "start_stream", ok: true }));
    assert.match((await browser.next(v => v.type === "device_state" && v.status === "error")).reason, /stalled/);
  } finally { await gateway.close(); }
});
