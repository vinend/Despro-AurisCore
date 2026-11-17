import { randomUUID } from "node:crypto";
import Redis from "ioredis";
import type { WebSocket, RawData } from "ws";
import { AudioContinuity, decodeAudioFrame, parseDeviceHello, type DeviceHello } from "./device-protocol.ts";
import { matchesToken } from "./cloud-auth.server.ts";

type Role = "device" | "browser";
const leaseMs = 6000;
const renew = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE',KEYS[1],ARGV[2]) end return 0";
const release = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0";
const publish = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('PUBLISH',KEYS[2],ARGV[2]) end return -1";
const validId = (id: unknown): id is string => typeof id === "string" && /^[\w-]{1,64}$/.test(id);

export function attachCloudSocket(ws: WebSocket, role: Role, options: { url: string; namespace: string; token: string }) {
  const prefix = `auriscore:{${options.namespace}}`;
  const peer: Role = role === "device" ? "browser" : "device";
  const key = (r: Role) => `${prefix}:lease:${r}`;
  const channel = (r: Role) => `${prefix}:incoming:${r}`;
  const owner = randomUUID();
  const redis = new Redis(options.url, { lazyConnect: true, enableOfflineQueue: false, commandTimeout: 1500,
    connectTimeout: 2500, retryStrategy: () => null, maxRetriesPerRequest: 0 });
  const subscriber = redis.duplicate();
  let closed = false, owned = false, authenticated = false;
  let hello: DeviceHello | null = null;
  let deviceOwner: string | null = null;
  let captureOwner: string | null = null;
  let continuity: AudioContinuity | null = null;
  let lastAudio = 0;
  let pending: { id: string; command: string; browser: string; expires: number } | null = null;
  let windowStart = Date.now(), messages = 0, queued = 0;
  let queue = Promise.resolve();
  let missedPongs = 0;
  const send = (value: unknown) => { if (ws.readyState === 1) ws.send(JSON.stringify(value)); };
  const state = (status: string, reason: string | null = null) => ({ type: "device_state", status, reason });
  const relay = async (payload: unknown, target?: string) => {
    const count = await redis.eval(publish, 2, key(role), channel(peer), owner, JSON.stringify({ owner, target, payload }));
    if (count === -1) throw Error("Lease lost");
  };
  function close(code?: number, reason?: string) {
    if (closed) return;
    closed = true;
    clearTimeout(deadline);
    clearInterval(watchdog);
    if (code && ws.readyState === 1) ws.close(code, reason);
    subscriber.disconnect();
    void queue.finally(async () => {
      try {
        if (owned) {
          await relay(role === "device" ? state("offline", "Device disconnected") : { type: "peer_left" });
          await redis.eval(release, 1, key(role), owner);
        }
      } catch { /* Lease expires if Redis is unavailable. */ }
      finally { redis.disconnect(); }
    });
  }
  function enqueue(task: () => Promise<void>) {
    if (closed) return;
    if (++queued > 32) { close(1013, "Relay busy"); return; }
    queue = queue.then(async () => { if (!closed) await task(); })
      .catch(() => close(1008, "Invalid message or relay unavailable"))
      .finally(() => { queued--; });
  }
  const deadline = setTimeout(() => close(1008, "Authentication required"), 5000);
  const watchdog = setInterval(() => enqueue(async () => {
    if (!authenticated) return;
    if (++missedPongs > 3) { close(1011, "Peer disconnected"); return; }
    ws.ping();
    if (await redis.eval(renew, 1, key(role), owner, leaseMs) !== 1) throw Error("Lease lost");
    if (role === "browser" && hello && !(await redis.exists(key("device")))) {
      hello = null;
      deviceOwner = null;
      send(state("offline", "Device disconnected"));
    }
    if (role === "device" && (pending && pending.expires < Date.now()
      || captureOwner && (Date.now() - lastAudio > 2000 || await redis.get(key("browser")) !== captureOwner))) {
      await relay(state("error", "Audio or control stalled"));
      close(1008, "Audio or control stalled");
    }
  }), 1000);

  subscriber.on("error", () => close(1011, "Relay unavailable"));
  redis.on("error", () => close(1011, "Relay unavailable"));
  subscriber.on("end", () => close(1011, "Relay unavailable"));
  redis.on("end", () => close(1011, "Relay unavailable"));
  subscriber.on("message", (_channel, raw) => enqueue(async () => {
    if (!authenticated) return;
    const { owner: sender, target, payload } = JSON.parse(raw);
    if (target && target !== owner) return;
    if (role === "browser") {
      if (payload.type === "audio") {
        if (deviceOwner !== sender) return;
        if (ws.bufferedAmount > 64 * 1024) { close(1013, "Listening client too slow"); return; }
        if (ws.readyState === 1) ws.send(Buffer.from(payload.data, "base64"), { binary: true });
        return;
      }
      if (payload.type === "device_hello") {
        if (deviceOwner === sender) return;
        hello = parseDeviceHello(payload);
        deviceOwner = sender;
      } else if (deviceOwner !== sender) return;
      if (payload.type === "device_state" && payload.status === "offline") { hello = null; deviceOwner = null; }
      send(payload);
      return;
    }
    if (payload.type === "peer_left") {
      if (captureOwner === sender || pending?.browser === sender) close(1008, "Controller disconnected");
      return;
    }
    if (payload.type === "discover") {
      if (captureOwner && captureOwner !== sender) { close(1011, "Controller changed"); return; }
      if (hello) { await relay(hello, sender); await relay(state("ready"), sender); }
      return;
    }
    if (payload.type === "indicator") {
      if (hello?.indicatorProtocol === 1) send(payload);
      return;
    }
    if (payload.type === "command") {
      if (!hello || pending) {
        await relay({ type: "command_ack", id: payload.id, command: payload.command, ok: false }, sender);
        return;
      }
      pending = { id: payload.id, command: payload.command, browser: sender, expires: Date.now() + 3000 };
      send(payload);
    }
  }));

  ws.on("pong", () => { missedPongs = 0; });
  ws.on("close", () => close());
  ws.on("error", () => close(1011, "Socket error"));
  ws.on("message", (raw: RawData, binary: boolean) => {
    const now = Date.now();
    if (now - windowStart >= 1000) { windowStart = now; messages = 0; }
    const bytes = Array.isArray(raw) ? Buffer.concat(raw) : Buffer.from(raw as Buffer);
    if (++messages > (role === "device" ? 50 : 10) || bytes.length > 2048) {
      close(1008, "Message limit exceeded"); return;
    }
    enqueue(async () => {
      if (binary) {
        if (role !== "device" || !continuity || !captureOwner) throw Error("Unexpected audio");
        if (!continuity.accept(decodeAudioFrame(bytes))) return;
        lastAudio = Date.now();
        await relay({ type: "audio", data: bytes.toString("base64") }, captureOwner);
        return;
      }
      const message = JSON.parse(bytes.toString());
      if (!authenticated) {
        if (message?.type !== "authenticate" || !matchesToken(message.token, options.token)) throw Error("Authentication failed");
        await Promise.all([redis.connect(), subscriber.connect()]);
        owned = await redis.set(key(role), owner, "PX", leaseMs, "NX") === "OK";
        if (!owned || closed) throw Error("Connection unavailable");
        await subscriber.subscribe(channel(role));
        authenticated = true;
        clearTimeout(deadline);
        send({ type: "authenticated", role });
        if (role === "browser") { send(state("offline")); await relay({ type: "discover" }); }
        return;
      }
      if (message.type === "heartbeat") {
        if (role === "browser" && message.id !== undefined) {
          if (!validId(message.id)) throw Error("Invalid heartbeat");
          send({ type: "heartbeat_ack", id: message.id });
        }
        return;
      }
      if (role === "device") {
        if (message.type === "device_hello" && !hello) {
          hello = parseDeviceHello(message);
          await relay(hello);
          await relay(state("ready"));
          return;
        }
        if (message.type === "command_ack" && hello && pending && pending.id === message.id
          && pending.command === message.command && typeof message.ok === "boolean") {
          const { browser, id, command } = pending;
          pending = null;
          if (message.ok && command === "start_stream") {
            continuity = new AudioContinuity(hello.streamId);
            captureOwner = browser;
            lastAudio = Date.now();
          }
          if (message.ok && command === "stop_stream") { continuity = null; captureOwner = null; }
          await relay({ type: "command_ack", id, command, ok: message.ok }, browser);
          if (message.ok) await relay(state(captureOwner ? "streaming" : "ready"), browser);
          return;
        }
        if (message.type === "source_error") await relay(state("error", "Device audio source failed"));
        throw Error("Unexpected device message");
      }
      if (message.type === "command" && deviceOwner && validId(message.id)
        && ["start_stream", "stop_stream"].includes(message.command)) {
        await relay({ type: "command", id: message.id, command: message.command }, deviceOwner);
        return;
      }
      if (message.type === "indicator" && ["heart", "lung", "abdomen"].includes(message.mode)
        && ["idle", "recording", "processing", "done", "error"].includes(message.phase)) {
        await relay({ type: "indicator", mode: message.mode, phase: message.phase });
        return;
      }
      throw Error("Unexpected browser message");
    });
  });
}
