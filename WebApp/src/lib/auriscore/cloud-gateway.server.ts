import { randomUUID } from "node:crypto";
import Redis from "ioredis";
import type { WebSocket, RawData } from "ws";
import { AUDIO_FRAME_BYTES, CLOUD_AUDIO_BATCH_BYTES, AudioContinuity, decodeAudioFrame, parseDeviceHello, type DeviceHello } from "./device-protocol.ts";
import { matchesToken } from "./cloud-auth.server.ts";
import { CLOUD_AUDIO_STALL_MS } from "./stream-timing.ts";

type Role = "device" | "browser";
type RedisCommand = (string | number)[];
const leaseMs = 20_000;
const renew = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('PEXPIRE',KEYS[1],ARGV[2]) end return 0";
const release = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0";
const publish = "if redis.call('GET',KEYS[1]) ~= ARGV[1] then return -1 end redis.call('PEXPIRE',KEYS[1],ARGV[3]) return redis.call('PUBLISH',KEYS[2],ARGV[2])";
const publishCapturedAudio = "if redis.call('GET',KEYS[1]) ~= ARGV[1] then return -1 end if redis.call('GET',KEYS[3]) ~= ARGV[4] then return -2 end redis.call('PEXPIRE',KEYS[1],ARGV[3]) return redis.call('PUBLISH',KEYS[2],ARGV[2])";
const validId = (id: unknown): id is string => typeof id === "string" && /^[\w-]{1,64}$/.test(id);

export function attachCloudSocket(ws: WebSocket, role: Role, options: { url: string; namespace: string; token: string;
  authorize?: (token: unknown) => Promise<boolean>;
  publishAudioCommands?: (commands: RedisCommand[]) => Promise<number[]> }) {
  const prefix = `auriscore:{${options.namespace}}`;
  const peer: Role = role === "device" ? "browser" : "device";
  const key = (r: Role) => `${prefix}:lease:${r}`;
  const channel = (r: Role) => `${prefix}:incoming:${r}`;
  const owner = randomUUID();
  const redis = new Redis(options.url, { lazyConnect: true, enableOfflineQueue: false, commandTimeout: 5000,
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
  let pendingAudioPublishes = 0;
  const waitingAudio: { data: Buffer; target: string }[] = [];
  let publishingAudio = false;
  let queue = Promise.resolve();
  let lastPeerActivity = performance.now(), checkingConnection = false;
  let refreshingBrowserLease = false;
  let accountToken: unknown = null, lastAuthorization = 0, reauthorizing = false;
  const send = (value: unknown) => { if (ws.readyState === 1) ws.send(JSON.stringify(value)); };
  const state = (status: string, reason: string | null = null) => ({ type: "device_state", status, reason });
  const relay = async (payload: unknown, target?: string) => {
    const count = await redis.eval(publish, 2, key(role), channel(peer), owner, JSON.stringify({ owner, target, payload }), leaseMs);
    if (count === -1) throw Error("Lease lost");
  };
  function checkAudioPublish(count: unknown) {
    if (count === -1) close(1011, "Audio relay lease lost");
    if (count === -2) close(1008, "Audio controller lease lost");
  }
  function audioPublishFailed(error: unknown) {
    const message = error instanceof Error ? error.message : "";
    const reason = /timed out|timeout/i.test(message) ? "Audio relay timeout"
      : /quota|limit|rate/i.test(message) ? "Audio relay provider limit"
      : "Audio relay connection unavailable";
    close(1011, reason);
  }
  function audioEnvelope(data: Buffer, target: string) {
    return JSON.stringify({ owner, target, payload: { type: "audio", data: data.toString("base64") } });
  }
  async function flushWaitingAudio() {
    if (closed || publishingAudio || !waitingAudio.length || !options.publishAudioCommands) return;
    publishingAudio = true;
    const target = waitingAudio[0].target;
    // Combine consecutive queued batches for one controller into one publish.
    // This preserves PCM order and avoids a Redis command for each arrival.
    const batch: Buffer[] = [];
    while (waitingAudio[0]?.target === target) batch.push(waitingAudio.shift()!.data);
    const envelope = audioEnvelope(Buffer.concat(batch), target);
    try {
      const [result] = await options.publishAudioCommands([
        ["EVAL", publishCapturedAudio, 3, key(role), channel(peer), key("browser"), owner, envelope, leaseMs, target],
      ]);
      checkAudioPublish(result);
    } catch (error) {
      audioPublishFailed(error);
    } finally {
      pendingAudioPublishes -= batch.length;
      publishingAudio = false;
      if (!closed && waitingAudio.length) void flushWaitingAudio();
    }
  }
  function relayAudio(data: Buffer, target: string) {
    if (pendingAudioPublishes >= 32) {
      close(1013, "Audio relay backlog");
      return;
    }
    pendingAudioPublishes++;
    // Redis receives commands in order on this socket. Waiting for a response
    // per PCM batch would make the relay's throughput depend on round-trip time.
    if (options.publishAudioCommands) {
      waitingAudio.push({ data, target });
      void flushWaitingAudio();
      return;
    }
    void redis.eval(publishCapturedAudio, 3, key(role), channel(peer), key("browser"), owner, audioEnvelope(data, target), leaseMs, target)
      .then(checkAudioPublish)
      .catch(audioPublishFailed)
      .finally(() => { pendingAudioPublishes--; });
  }
  function close(code?: number, reason?: string) {
    if (closed) return;
    closed = true;
    waitingAudio.length = 0;
    if (authenticated && code && reason) console.info("auriscore.gateway.closed", { role, code, reason });
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
  const deadline = setTimeout(() => close(1013, "Gateway handshake timed out"), 5000);
  const watchdog = setInterval(() => {
    if (closed || !authenticated) return;
    // Provider latency must not pause PCM relay or Redis lease renewal.
    if (options.authorize && !reauthorizing && Date.now() - lastAuthorization > 30_000) {
      reauthorizing = true;
      void options.authorize(accountToken).then(allowed => {
        if (!allowed) close(1008, "Account access expired");
        else lastAuthorization = Date.now();
      }).catch(() => close(1008, "Account access unavailable"))
        .finally(() => { reauthorizing = false; });
    }
    if (checkingConnection) return;
    checkingConnection = true;
    // A delayed lease check must not hold up PCM parsing or browser controls.
    void (async () => {
      // Mobile and embedded clients can deliver application data before a pong.
      const idleMs = performance.now() - lastPeerActivity;
      if (idleMs > CLOUD_AUDIO_STALL_MS) {
        close(1011, "Peer disconnected"); return;
      }
      if (idleMs >= 2000) ws.ping();
      if (role === "device" && captureOwner) {
        // An audio publish atomically checks both leases and renews the device.
        // A second Redis round trip is unnecessary during an active capture.
        if (Date.now() - lastAudio > CLOUD_AUDIO_STALL_MS) {
          close(1008, "Audio stalled");
        }
        return;
      }
      if (role === "device" && pending && pending.expires < Date.now()) {
        close(1008, "Audio start command stalled");
        return;
      }
      if (await redis.eval(renew, 1, key(role), owner, leaseMs) !== 1) {
        close(1011, "Gateway lease lost");
        return;
      }
      if (closed) return;
      const observedDevice = deviceOwner;
      if (role === "browser" && observedDevice && !(await redis.exists(key("device")))
        && !closed && deviceOwner === observedDevice) {
        hello = null;
        deviceOwner = null;
        send(state("offline", "Device disconnected"));
      }
    })().catch(() => {
      if (role !== "device" || !captureOwner) close(1011, "Gateway lease check unavailable");
    })
      .finally(() => { checkingConnection = false; });
  }, 1000);

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
        const audio = Buffer.from(payload.data, "base64");
        if (ws.bufferedAmount + audio.length > 128 * 1024) {
          close(1013, "Listening client too slow");
          return;
        }
        for (let offset = 0; offset < audio.length && ws.readyState === 1; offset += AUDIO_FRAME_BYTES) {
          ws.send(audio.subarray(offset, offset + AUDIO_FRAME_BYTES), { binary: true });
        }
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

  ws.on("pong", () => { lastPeerActivity = performance.now(); });
  ws.on("close", () => close());
  ws.on("error", () => close(1011, "Socket error"));
  ws.on("message", (raw: RawData, binary: boolean) => {
    const now = Date.now();
    if (now - windowStart >= 1000) { windowStart = now; messages = 0; }
    const bytes = Array.isArray(raw) ? Buffer.concat(raw) : Buffer.from(raw as Buffer);
    if (++messages > (role === "device" ? 50 : 10) || bytes.length > (binary && role === "device" ? CLOUD_AUDIO_BATCH_BYTES : 2048)) {
      close(1008, "Message limit exceeded"); return;
    }
    enqueue(async () => {
      if (binary) {
        if (role !== "device" || !continuity || !captureOwner) throw Error("Unexpected audio");
        if (!bytes.length || bytes.length % AUDIO_FRAME_BYTES !== 0) throw Error("Invalid PCM batch");
        const accepted: Buffer[] = [];
        for (let offset = 0; offset < bytes.length; offset += AUDIO_FRAME_BYTES) {
          const frame = bytes.subarray(offset, offset + AUDIO_FRAME_BYTES);
          if (continuity.accept(decodeAudioFrame(frame))) accepted.push(frame);
        }
        if (accepted.length === 0) return;
        lastAudio = Date.now();
        lastPeerActivity = performance.now();
        const contiguous = accepted.length === 1 ? accepted[0] : Buffer.concat(accepted);
        relayAudio(contiguous, captureOwner);
        return;
      }
      const message = JSON.parse(bytes.toString());
      if (!authenticated) {
        if (message?.type !== "authenticate"
            || !(options.authorize ? await options.authorize(message.token) : matchesToken(message.token, options.token)))
          throw Error("Authentication failed");
        if (closed) return;
        await Promise.all([redis.connect(), subscriber.connect()]);
        owned = await redis.set(key(role), owner, "PX", leaseMs, "NX") === "OK";
        if (closed) return;
        if (!owned) { close(1013, "Controller slot busy"); return; }
        await subscriber.subscribe(channel(role));
        authenticated = true;
        accountToken = message.token; lastAuthorization = Date.now();
        lastPeerActivity = performance.now();
        clearTimeout(deadline);
        send({ type: "authenticated", role });
        if (role === "browser") await relay({ type: "discover" });
        return;
      }
      if (message.type === "heartbeat") {
        if (role === "browser" && message.id !== undefined) {
          if (!validId(message.id)) throw Error("Invalid heartbeat");
          lastPeerActivity = performance.now();
          if (!refreshingBrowserLease) {
            refreshingBrowserLease = true;
            void redis.eval(renew, 1, key(role), owner, leaseMs).then(result => {
              if (result !== 1) close(1011, "Browser lease lost");
            }).catch(() => close(1011, "Browser lease refresh unavailable"))
              .finally(() => { refreshingBrowserLease = false; });
          }
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
        if (message.type === "source_error") {
          await relay(state("error", "Device audio source failed"));
          close(1011, "Device audio source failed");
          return;
        }
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
