import assert from "node:assert/strict";
import { once } from "node:events";
import { randomUUID } from "node:crypto";
import test from "node:test";
import { WebSocket, WebSocketServer } from "ws";
import Redis from "ioredis";
import { createRedisAudioPublisher } from "../src/lib/auriscore/cloud-audio-redis.server.ts";
import { attachCloudSocket } from "../src/lib/auriscore/cloud-gateway.server.ts";
import { encodeAudioFrame } from "../src/lib/auriscore/device-protocol.ts";

const url = process.env.AURISCORE_TEST_REDIS_URL;
const restUrl = process.env.AURISCORE_TEST_REDIS_REST_URL;
const restToken = process.env.AURISCORE_TEST_REDIS_REST_TOKEN;
test("HTTPS Redis audio publishes in order to the existing TCP subscriber", { skip: !url || !restUrl || !restToken, timeout: 5000 }, async t => {
  const publish = createRedisAudioPublisher(url, restUrl, restToken);
  const subscriber = new Redis(url, { lazyConnect: true });
  t.after(() => subscriber.disconnect());
  await subscriber.connect();
  const channel = `auriscore:audio-test:${randomUUID()}`;
  await subscriber.subscribe(channel);
  const seen = [];
  subscriber.on("message", (_channel, data) => seen.push(data));
  assert.deepEqual(await publish([["PUBLISH", channel, "first"], ["PUBLISH", channel, "second"]]), [1, 1]);
  const deadline = performance.now() + 1200;
  while (seen.length < 2 && performance.now() < deadline) await new Promise(resolve => setTimeout(resolve, 15));
  assert.deepEqual(seen, ["first", "second"]);
});
test("cloud gateway pairs separate listeners, relays PCM and fails closed on a sample gap", { skip: !url, timeout: 12000 }, async t => {
  const namespace = randomUUID();
  const cleanups = [];
  t.after(async () => { await Promise.all(cleanups.map(cleanup => cleanup())); });
  async function listener(role) {
    const token = randomUUID();
    const server = new WebSocketServer({ host: "127.0.0.1", port: 0 });
    cleanups.push(async () => {
      for (const peer of server.clients) peer.terminate();
      await new Promise(resolve => server.close(resolve));
    });
    server.on("connection", socket => attachCloudSocket(socket, role, { url, namespace, token }));
    await once(server, "listening");
    return async (credential = token) => {
      const socket = new WebSocket(`ws://127.0.0.1:${server.address().port}`);
      const received = [];
      socket.on("message", (data, binary) => received.push(binary ? data : JSON.parse(data.toString())));
      await once(socket, "open");
      const send = value => socket.send(JSON.stringify(value));
      const take = async predicate => {
        for (let tries = 0; tries < 100; tries++) {
          const index = received.findIndex(predicate);
          if (index >= 0) return received.splice(index, 1)[0];
          await new Promise(resolve => setTimeout(resolve, 20));
        }
        assert.fail(`Missing message; received ${received.map(message => message.type)}`);
      };
      send({ type: "authenticate", token: credential });
      return { socket, send, take };
    };
  }
  const connectDevice = await listener("device");
  const connectBrowser = await listener("browser");
  const denied = await connectDevice("invalid-token");
  assert.equal((await once(denied.socket, "close"))[0], 1008);
  const device = await connectDevice();
  await device.take(message => message.type === "authenticated");
  const hello = { type: "device_hello", protocol: 2, device: "fixture", fw: "test", source: "engineering",
    streamId: 12, samplingRate: 8000, channels: 1, encoding: "pcm16le", indicatorProtocol: 1 };
  device.send(hello);
  const browser = await connectBrowser();
  await browser.take(message => message.type === "authenticated");
  assert.deepEqual(await browser.take(message => ["device_hello", "device_state"].includes(message.type)), hello);
  const duplicate = await connectBrowser();
  assert.equal((await once(duplicate.socket, "close"))[0], 1013);

  const start = { type: "command", id: "start-1", command: "start_stream" };
  const frame = (seq, firstSample) => encodeAudioFrame({
    streamId: 12, seq, firstSample, flags: 0, samples: new Int16Array(400).fill(-1234),
  });
  const batch = [1, 2, 3, 4].map(seq => Buffer.from(frame(seq, seq * 400)));
  const nextBatch = [5, 6, 7, 8].map(seq => Buffer.from(frame(seq, seq * 400)));
  const evaluate = Redis.prototype.eval;
  let releaseResponse;
  const delayedResponse = new Promise(resolve => { releaseResponse = resolve; });
  let renewStarted;
  const renewalPending = new Promise(resolve => { renewStarted = resolve; });
  let delayedRenewal = false;
  let audioPublishes = 0;
  t.mock.method(Redis.prototype, "eval", function (...args) {
    const command = evaluate.apply(this, args);
    if (args[1] === 1 && args[0].includes("'PEXPIRE'") && String(args[2]).endsWith(":lease:device") && !delayedRenewal) {
      delayedRenewal = true;
      renewStarted();
      return command.then(async value => { await delayedResponse; return value; });
    }
    if (args[1] === 3 && args[0].includes("'PUBLISH'") && JSON.parse(args[6]).payload.type === "audio" && ++audioPublishes === 2) {
      return command.then(async value => { await delayedResponse; return value; });
    }
    return command;
  });
  try {
    await renewalPending;
    browser.send(start);
    assert.deepEqual(await device.take(message => message.type === "command"), start);
    device.send({ ...start, type: "command_ack", ok: true });
    await browser.take(message => message.type === "command_ack" && message.ok);
    device.socket.send(frame(0, 0));
    assert.deepEqual(await browser.take(Buffer.isBuffer), Buffer.from(frame(0, 0)));
    const observer = new Redis(url, { lazyConnect: true });
    t.after(() => observer.disconnect());
    await observer.connect();
    const deviceLease = `auriscore:{${namespace}}:lease:device`;
    await observer.pexpire(deviceLease, 2000);
    device.socket.send(Buffer.concat(batch));
    device.socket.send(Buffer.concat(nextBatch));
    for (const expected of [...batch, ...nextBatch]) assert.deepEqual(await browser.take(Buffer.isBuffer), expected);
    assert.equal(audioPublishes, 3);
    assert.ok(await observer.pttl(deviceLease) > 15000, "Active audio did not renew its lease");
  } finally { releaseResponse(); }
  device.socket.send(Buffer.concat([Buffer.from(frame(9, 3600)), Buffer.from(frame(11, 4400))]));
  await browser.take(message => message.type === "device_state" && message.status === "offline" && message.reason);
});


test("active mobile heartbeat keeps the browser lease across delayed WebSocket pongs", { skip: !url, timeout: 20000 }, async t => {
  const token = randomUUID();
  const server = new WebSocketServer({ host: "127.0.0.1", port: 0 });
  t.after(async () => {
    for (const peer of server.clients) peer.terminate();
    await new Promise(resolve => server.close(resolve));
  });
  server.on("connection", socket => attachCloudSocket(socket, "browser", { url, namespace: randomUUID(), token }));
  await once(server, "listening");
  const client = new WebSocket(`ws://127.0.0.1:${server.address().port}`, { autoPong: false });
  await once(client, "open");
  const auth = once(client, "message");
  client.send(JSON.stringify({ type: "authenticate", token }));
  assert.equal(JSON.parse((await auth)[0]).type, "authenticated");
  for (let i = 0; i < 5; i++) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    assert.equal(client.readyState, WebSocket.OPEN);
    const ack = once(client, "message");
    client.send(JSON.stringify({ type: "heartbeat", id: String(i) }));
    assert.equal(JSON.parse((await ack)[0]).id, String(i));
  }
  const [code, reason] = await once(client, "close");
  assert.equal(code, 1011);
  assert.equal(reason.toString(), "Peer disconnected");
});
