import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { once } from "node:events";
import { createDeviceGateway } from "../mini-services/device-gateway/gateway.ts";
import { DeviceConnection } from "../src/lib/auriscore/device-connection.ts";
import { encodeAudioFrame } from "../src/lib/auriscore/device-protocol.ts";
import { RecordingSession } from "../src/lib/auriscore/recording-session.ts";
const require = createRequire(new URL("../mini-services/device-gateway/package.json", import.meta.url));
const { WebSocket } = require("ws");
const token = "fictional-streaming-test-token", origin = "http://localhost:3000";
function samples(seq) { return Int16Array.from({ length: 400 }, (_, i) => Math.round(8000 * Math.sin(2 * Math.PI * 65 * (seq * 400 + i) / 8000))); }

test("real gateway/browser decoder preserves 80,000 samples and automatic recording WAV", { timeout: 20_000 }, async () => {
  const original = globalThis.WebSocket;
  globalThis.WebSocket = class extends WebSocket { constructor(url) { super(url, { origin }); } };
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0 }); const address = await gateway.listen();
  const base = `ws://127.0.0.1:${address.port}`;
  let publisher, browser, interval;
  try {
    const states = []; let calls = 0, captured;
    const session = new RecordingSession({ analyze: async file => { calls++; captured = Buffer.from(await file.arrayBuffer());
      return { mode: "heart", status: "partial" }; } });
    browser = new DeviceConnection({ url: base + "/browser", token }, {
      onStateChange: state => { states.push(state); if (state === "connected" && session.getSnapshot().phase === "idle") session.start("heart", "mock"); },
      onPacket: packet => session.accept(packet),
    });
    browser.connect();
    await new Promise(resolve => setTimeout(resolve, 80)); assert.ok(!states.includes("connected"));
    publisher = new WebSocket(base + "/device");
    publisher.on("message", raw => {
      const message = JSON.parse(raw.toString());
      if (message.type === "authenticated") publisher.send(JSON.stringify({ type: "device_hello", protocol: 2,
        device: "engineering-test", fw: "test", source: "engineering", streamId: 19, channels: 1, samplingRate: 8000, encoding: "pcm16le" }));
      if (message.type === "command") {
        publisher.send(JSON.stringify({ ...message, type: "command_ack", ok: true })); let seq = 0;
        interval = setInterval(() => { publisher.send(encodeAudioFrame({ streamId: 19, seq, firstSample: seq * 400, flags: 0, samples: samples(seq) }));
          if (++seq === 200) clearInterval(interval); }, 50);
      }
    });
    await once(publisher, "open"); publisher.send(JSON.stringify({ type: "authenticate", token }));
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { off(); reject(Error("Recording did not complete")); }, 14_000);
      const off = session.subscribe(() => { if (session.getSnapshot().phase === "done") { clearTimeout(timer); off(); resolve(); } });
    });
    assert.equal(calls, 1); assert.equal(captured.length, 160044);
    assert.equal(session.getSnapshot().elapsedMs, 10000);
    for (let seq = 0; seq < 200; seq++) { const expected = samples(seq);
      for (let i = 0; i < 400; i++) assert.equal(captured.readInt16LE(44 + (seq * 400 + i) * 2), expected[i]); }
    session.dispose();
  } finally { clearInterval(interval); browser?.close(); publisher?.terminate(); await gateway.close(); globalThis.WebSocket = original; }
});
test("AudioWorklet listening resamples, bounds backlog and resets without altering source PCM", () => {
  let Processor;
  runInNewContext(readFileSync(new URL("../public/audio/pcg-listener.js", import.meta.url), "utf8"), {
    AudioWorkletProcessor: class { constructor() { this.port = {}; } }, Float32Array, sampleRate: 48000,
    registerProcessor: (_name, value) => { Processor = value; },
  });
  const listener = new Processor(), input = Float32Array.from({ length: 400 }, (_, i) => i / 400), copy = input.slice();
  for (let i = 0; i < 2; i++) listener.port.onmessage({ data: { type: "samples", samples: input } });
  const output = new Float32Array(128); listener.process([], [[output]]);
  assert.ok(output.some(value => value > 0)); assert.ok(listener.count < 800); assert.deepEqual(input, copy);
  for (let i = 0; i < 100; i++) listener.port.onmessage({ data: { type: "samples", samples: input } });
  assert.ok(listener.count <= 2400); listener.port.onmessage({ data: { type: "reset" } });
  listener.process([], [[output]]); assert.ok(output.every(value => value === 0));
});
test("recording watchdog refuses absent samples without calling analysis", async () => {
  let calls = 0; const session = new RecordingSession({ analyze: async () => { calls++; } });
  session.start("heart", "websocket-device");
  await new Promise(resolve => setTimeout(resolve, 2200));
  assert.equal(session.getSnapshot().phase, "error"); assert.equal(calls, 0); session.dispose();
});
