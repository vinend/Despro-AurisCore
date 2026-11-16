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
import { defaultGatewayUrl } from "../src/lib/auriscore/gateway-url.ts";
import { SignalMeter } from "../src/lib/auriscore/signal-meter.ts";
const require = createRequire(new URL("../mini-services/device-gateway/package.json", import.meta.url));
const { WebSocket } = require("ws");
const token = "fictional-streaming-test-token", origin = "http://localhost:3000";
function samples(seq) { return Int16Array.from({ length: 400 }, (_, i) => Math.round(8000 * Math.sin(2 * Math.PI * 65 * (seq * 400 + i) / 8000))); }

test("gateway defaults follow the page host on phone, localhost and HTTPS", () => {
  for (const [page, expected] of [
    ["http://192.168.0.193:3000", "ws://192.168.0.193:8082/browser"],
    ["http://localhost:3000", "ws://localhost:8082/browser"],
    ["https://auriscore.local", "wss://auriscore.local/browser"],
    ["https://auriscore.local:8443", "wss://auriscore.local:8443/browser"],
    ["http://[::1]:3000", "ws://[::1]:8082/browser"],
  ]) assert.equal(defaultGatewayUrl(new URL(page)), expected);
});

test("HTTP LAN handshake starts streaming without secure-context crypto APIs", () => {
  const originalSocket = globalThis.WebSocket;
  const originalCrypto = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  const originalPerformance = Object.getOwnPropertyDescriptor(globalThis, "performance");
  let clock = 100;
  let socket;
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor() { socket = this; }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() {}
  }
  const states = [], errors = [], latencies = [];
  let browser;
  try {
    // Models an HTTP LAN browser where randomUUID is unavailable.
    Object.defineProperty(globalThis, "crypto", { configurable: true, value: {} });
    Object.defineProperty(globalThis, "performance", { configurable: true, value: { now: () => clock } });
    globalThis.WebSocket = Socket;
    browser = new DeviceConnection({ url: "ws://192.168.0.193:8082/browser", token }, {
      onStateChange: state => states.push(state), onError: error => errors.push(error),
      onLatency: value => latencies.push(value),
    });
    browser.connect(); socket.onopen();
    assert.deepEqual(socket.sent[0], { type: "authenticate", token });
    socket.onmessage({ data: JSON.stringify({ type: "authenticated", role: "browser" }) });
    assert.equal(socket.sent[1].type, "heartbeat");
    socket.onmessage({ data: JSON.stringify({ type: "heartbeat_ack", id: "wrong" }) });
    assert.deepEqual(latencies, [null]);
    clock = 125.5;
    socket.onmessage({ data: JSON.stringify({ type: "heartbeat_ack", id: socket.sent[1].id }) });
    assert.equal(latencies.at(-1), 25.5);
    socket.onmessage({ data: JSON.stringify({ type: "device_hello", protocol: 2,
      device: "ESP32S3-USB-COM3", fw: "serial-v4", source: "hardware", streamId: 12,
      channels: 1, samplingRate: 8000, encoding: "pcm16le" }) });
    assert.equal(socket.sent[2].command, "start_stream");
    assert.match(socket.sent[2].id, /^[\w-]{1,64}$/);
    assert.ok(!states.includes("connected"));
    const audio = encodeAudioFrame({ streamId: 12, seq: 0, firstSample: 0, flags: 0, samples: samples(0) });
    socket.onmessage({ data: audio.buffer });
    assert.equal(states.at(-1), "connected"); assert.deepEqual(errors, []);
    const beforeIndicator = socket.sent.length;
    browser.setIndicator("heart", "recording");
    assert.equal(socket.sent.length, beforeIndicator);
    socket.onmessage({ data: JSON.stringify({ type: "device_hello", protocol: 2,
      device: "ESP32S3-WIFI", fw: "indicator-test", source: "hardware", streamId: 13,
      channels: 1, samplingRate: 8000, encoding: "pcm16le", indicatorProtocol: 1 }) });
    browser.setIndicator("lung", "done");
    assert.deepEqual(socket.sent.at(-1), { type: "indicator", mode: "lung", phase: "done" });
  } finally {
    browser?.close(); globalThis.WebSocket = originalSocket;
    if (originalCrypto) Object.defineProperty(globalThis, "crypto", originalCrypto);
    else delete globalThis.crypto;
    if (originalPerformance) Object.defineProperty(globalThis, "performance", originalPerformance);
    else delete globalThis.performance;
  }
});

test("signal meter preserves PCM and measures level, clipping and the rolling second", () => {
  const meter = new SignalMeter(); assert.equal(meter.read(), null);
  const pcm = Int16Array.from({ length: 8000 }, (_, i) => i % 2 ? 16384 : -16384), copy = pcm.slice();
  meter.accept(pcm); assert.deepEqual(pcm, copy);
  assert.ok(Math.abs(meter.read().rmsDbfs + 6.020599913) < 1e-8);
  assert.equal(meter.read().clippedFraction, 0);
  meter.accept([-32768, 32767]); assert.equal(meter.read().clippedFraction, 2 / 8000);
  meter.accept(new Int16Array(8000));
  assert.deepEqual(meter.read(), { sampleCount: 8000, rmsDbfs: null, clippedFraction: 0 });
  assert.throws(() => meter.accept([1, NaN]), /PCM16/);
  assert.throws(() => meter.accept([32768]), /PCM16/);
  assert.equal(meter.read().rmsDbfs, null);
});

test("browser handoff releases a publisher even when its close handshake stalls", { timeout: 4000 }, async () => {
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0 });
  const address = await gateway.listen(), base = `ws://127.0.0.1:${address.port}`;
  const clients = [];
  async function paired(role) {
    const socket = new WebSocket(`${base}/${role}`, role === "browser" ? { origin } : {});
    clients.push(socket); await once(socket, "open");
    const response = once(socket, "message");
    socket.send(JSON.stringify({ type: "authenticate", token }));
    assert.equal(JSON.parse((await response)[0].toString()).type, "authenticated");
    return socket;
  }
  try {
    const publisher = await paired("device"), controller = await paired("browser");
    const ack = once(controller, "message");
    controller.send(JSON.stringify({ type: "heartbeat", id: "test-rtt-1" }));
    assert.deepEqual(JSON.parse((await ack)[0].toString()), { type: "heartbeat_ack", id: "test-rtt-1" });
    // A real paused TCP reader cannot acknowledge the server's close frame.
    publisher._socket.pause();
    controller.close(); await once(controller, "close");
    await new Promise(resolve => setTimeout(resolve, 100));
    await paired("device");
    await paired("browser");
  } finally {
    for (const socket of clients) socket.terminate();
    await gateway.close();
  }
});

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
