import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import { WebSocket } from "ws";
import { createDeviceGateway } from "../mini-services/device-gateway/gateway.ts";
import { LinkTestConnection } from "../src/lib/auriscore/link-test.ts";

const token = "fictional-no-mic-link-test-token", origin = "http://localhost:3000";
const hello = { type: "device_hello", protocol: 2, device: "ESP32S3-NO-MIC-LINK-TEST",
  fw: "wifi-link-test-1", source: "engineering", streamId: 9, samplingRate: 8000, channels: 1, encoding: "pcm16le" };
async function until(condition) {
  const deadline = Date.now() + 4000;
  while (!condition()) {
    if (Date.now() > deadline) throw Error("Timed out waiting for link state");
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}

test("no-mic browser authenticates through real gateway, probes RTT and sends no audio/start commands", async t => {
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0 });
  const address = await gateway.listen(), base = `ws://127.0.0.1:${address.port}`;
  const board = new WebSocket(base + "/device");
  const received = []; board.on("message", raw => received.push(JSON.parse(raw.toString())));
  await once(board, "open"); board.send(JSON.stringify({ type: "authenticate", token }));
  await until(() => received.some(x => x.type === "authenticated")); board.send(JSON.stringify(hello));
  let state;
  const client = new LinkTestConnection(value => { state = value; }, url => new WebSocket(url, { origin }));
  t.after(async () => { client.close(); board.close(); await gateway.close(); });
  client.connect(base + "/browser", token);
  await until(() => state?.device === hello.device && state.gatewayRttMs !== null);
  assert.equal(state.paired, true); assert.ok(state.gatewayRttMs >= 0);
  assert.equal(received.some(x => x.type === "command"), false);
  board.close(); await until(() => state.device === null);
  assert.equal(state.paired, true);
});

test("test client rejects another firmware, binary audio and invalid pairing URLs", () => {
  let socket, state;
  const factory = () => socket = { readyState: 1, send() {}, close() {} };
  const client = new LinkTestConnection(value => { state = value; }, factory);
  assert.throws(() => client.connect("ws://localhost/browser?token=secret", token));
  assert.throws(() => client.connect("ws://localhost/browser", "short"));
  client.connect("ws://localhost/browser", token);
  socket.onmessage({ data: JSON.stringify({ type: "authenticated", role: "browser" }) });
  socket.onmessage({ data: JSON.stringify({ ...hello, source: "hardware" }) });
  assert.equal(state.paired, false); assert.match(state.error, /bukan firmware uji/);
  client.connect("ws://localhost/browser", token);
  socket.onmessage({ data: new Uint8Array(832) });
  assert.equal(state.device, null); assert.match(state.error, /Audio tidak diterima/);
});

test("connection-only client accepts the prepared AurisCore capture firmware without requesting audio", () => {
  let socket, state; const sent = [];
  const client = new LinkTestConnection(value => { state = value; }, () => socket = {
    readyState: 1, send(value) { sent.push(JSON.parse(value)); }, close() {} });
  client.connect("ws://localhost/browser", token); socket.onopen();
  socket.onmessage({ data: JSON.stringify({ type: "authenticated", role: "browser" }) });
  socket.onmessage({ data: JSON.stringify({ ...hello, device: "ESP32S3-INMP441-WIFI", fw: "wifi-capture-0.2.0", source: "hardware" }) });
  assert.equal(state.device, "ESP32S3-INMP441-WIFI");
  assert.equal(sent.some(x => x.type === "command"), false);
  client.close();
});

test("wrong token fails closed at actual gateway", async t => {
  const gateway = createDeviceGateway({ token, origins: [origin], port: 0 });
  const address = await gateway.listen(); let state;
  const client = new LinkTestConnection(value => { state = value; }, url => new WebSocket(url, { origin }));
  t.after(async () => { client.close(); await gateway.close(); });
  client.connect(`ws://127.0.0.1:${address.port}/browser`, "fictional-wrong-test-token");
  await until(() => state?.error);
  assert.equal(state.paired, false); assert.equal(state.device, null);
});
