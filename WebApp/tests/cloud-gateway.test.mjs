import assert from "node:assert/strict";
import { once } from "node:events";
import { randomUUID } from "node:crypto";
import test from "node:test";
import { WebSocket, WebSocketServer } from "ws";
import { attachCloudSocket } from "../src/lib/auriscore/cloud-gateway.server.ts";
import { encodeAudioFrame } from "../src/lib/auriscore/device-protocol.ts";

const url = process.env.AURISCORE_TEST_REDIS_URL;
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
  assert.deepEqual(await browser.take(message => message.type === "device_hello"), hello);
  const duplicate = await connectBrowser();
  assert.equal((await once(duplicate.socket, "close"))[0], 1008);

  const start = { type: "command", id: "start-1", command: "start_stream" };
  browser.send(start);
  assert.deepEqual(await device.take(message => message.type === "command"), start);
  device.send({ ...start, type: "command_ack", ok: true });
  await browser.take(message => message.type === "command_ack" && message.ok);
  const frame = (seq, firstSample) => encodeAudioFrame({
    streamId: 12, seq, firstSample, flags: 0, samples: new Int16Array(400).fill(-1234),
  });
  device.socket.send(frame(0, 0));
  assert.deepEqual(await browser.take(Buffer.isBuffer), Buffer.from(frame(0, 0)));
  device.socket.send(frame(2, 800));
  await browser.take(message => message.type === "device_state" && message.status === "offline" && message.reason);
});
