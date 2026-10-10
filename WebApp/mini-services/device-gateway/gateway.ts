import { createServer, type IncomingMessage } from "node:http";
import { timingSafeEqual } from "node:crypto";
import { WebSocket, WebSocketServer } from "ws";
import { AudioContinuity, decodeAudioFrame, parseDeviceHello, type DeviceHello } from "../../src/lib/auriscore/device-protocol.ts";

export interface GatewayOptions { token: string; origins: string[]; host?: string; port?: number; staleMs?: number }
export function createDeviceGateway(options: GatewayOptions) {
  if (options.token.length < 16 || !options.origins.length) throw Error("Set a pairing token (16+ characters) and allowed browser origins.");
  const http = createServer((_req, res) => { res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"service":"auriscore-device-gateway","protocol":2}'); });
  const wss = new WebSocketServer({ noServer: true, maxPayload: 2048, perMessageDeflate: false });
  let device: WebSocket | null = null, hello: DeviceHello | null = null, continuity: AudioContinuity | null = null;
  let lastAudio = 0, active = false, ready = false, controller: WebSocket | null = null;
  const browsers = new Set<WebSocket>();
  const commands = new Map<string, { command: string; timer: ReturnType<typeof setTimeout> }>();
  const send = (socket: WebSocket, value: unknown) => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(value)); };
  const broadcast = (value: unknown) => { for (const socket of browsers) send(socket, value); };
  function state(status: "offline" | "ready" | "streaming" | "stale" | "error", reason?: string) {
    broadcast({ type: "device_state", status, reason: reason ?? null });
  }
  function stop(reason: string) {
    active = false; ready = false; continuity = null;
    state("error", reason);
    device?.close(1008, "Stream continuity failure");
  }
  const auth = (provided: unknown) => {
    if (typeof provided !== "string") return false;
    const supplied = Buffer.from(provided), expected = Buffer.from(options.token);
    return supplied.length === expected.length && timingSafeEqual(supplied, expected);
  };
  http.on("upgrade", (req: IncomingMessage, socket, head) => {
    const url = new URL(req.url ?? "/", "http://gateway");
    const role = url.pathname === "/device" ? "device" : url.pathname === "/browser" ? "browser" : null;
    if (!role || wss.clients.size >= 8 || (role === "browser" && !options.origins.includes(req.headers.origin ?? ""))) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n"); return;
    }
    wss.handleUpgrade(req, socket, head, ws => {
      let authenticated = false, messages = 0, windowStart = Date.now();
      const deadline = setTimeout(() => ws.close(1008, "Authentication required"), 5000);
      ws.on("error", () => {});
      ws.on("message", (raw, binary) => {
        try {
          if (Date.now() - windowStart > 1000) { windowStart = Date.now(); messages = 0; }
          if (++messages > (role === "device" ? 50 : 10)) throw Error("Message rate exceeded");
          if (!authenticated) {
            if (binary) throw Error("Authentication required");
            const request = JSON.parse(raw.toString());
            if (request.type !== "authenticate" || !auth(request.token)) throw Error("Authentication failed");
            if (role === "device") {
              if (device) throw Error("A device is already registered");
              device = ws;
            } else {
              if (controller) throw Error("A controlling browser is already connected");
              controller = ws; browsers.add(ws);
            }
            authenticated = true; clearTimeout(deadline); send(ws, { type: "authenticated", role });
            if (role === "browser") { if (hello) send(ws, hello); send(ws, { type: "device_state", status: active ? "streaming" : hello ? "ready" : "offline", reason: null }); }
            return;
          }
          if (role === "device" && binary) {
            if (!hello || !continuity || !ready) throw Error("Device handshake/start acknowledgement required");
            const bytes = new Uint8Array(Buffer.concat(Array.isArray(raw) ? raw : [Buffer.from(raw as Buffer)]));
            if (!continuity.accept(decodeAudioFrame(bytes))) return;
            lastAudio = Date.now();
            if (!active) { active = true; state("streaming"); }
            for (const browser of browsers) {
              if (browser.bufferedAmount > 64 * 1024) { browser.close(1013, "Listening client too slow"); continue; }
              browser.send(bytes, { binary: true });
            }
            return;
          }
          if (binary) throw Error("Browser audio publishing is not permitted");
          const message = JSON.parse(raw.toString());
          if (role === "device" && message.type === "device_hello") {
            if (hello) throw Error("Duplicate handshake");
            hello = parseDeviceHello(message); broadcast(hello); state("ready"); return;
          }
          if (role === "device" && message.type === "command_ack") {
            const pending = commands.get(message.id);
            if (!pending || pending.command !== message.command || typeof message.ok !== "boolean") throw Error("Invalid command acknowledgement");
            clearTimeout(pending.timer); commands.delete(message.id);
            if (message.ok && message.command === "start_stream") { ready = true; active = false; continuity = new AudioContinuity(hello!.streamId); lastAudio = Date.now(); }
            if (message.command === "stop_stream") { active = false; ready = false; continuity = null; state("ready"); }
            broadcast({ type: "command_ack", id: message.id, command: message.command, ok: message.ok }); return;
          }
          if (role === "browser" && message.type === "command") {
            if (!device || !hello || commands.size || !/^[\w-]{1,64}$/.test(message.id)
              || !["start_stream", "stop_stream"].includes(message.command)) throw Error("Device/control command unavailable");
            const timer = setTimeout(() => { commands.delete(message.id); stop("Device command timed out"); }, 3000);
            commands.set(message.id, { command: message.command, timer }); send(device, message); return;
          }
          if (role === "device" && message.type === "source_error") { stop("Device audio source failed or overflowed"); return; }
          if (message.type !== "heartbeat") throw Error("Unsupported message");
        } catch { if (ws === device && active) stop("Malformed audio/control or interrupted sample clock"); ws.close(1008, "Invalid protocol message"); }
      });
      ws.on("close", () => {
        clearTimeout(deadline); browsers.delete(ws);
        if (controller === ws) {
          controller = null;
          // A detached browser must not leave the source streaming indefinitely.
          if (device) device.close(1000, "Controller disconnected");
        }
        if (device === ws) {
          device = null; hello = null; active = false; ready = false; continuity = null;
          for (const pending of commands.values()) clearTimeout(pending.timer); commands.clear(); state("offline", "Device disconnected");
        }
      });
    });
  });
  const watchdog = setInterval(() => {
    if (ready && Date.now() - lastAudio > (options.staleMs ?? 2000)) stop("Audio stream stalled");
    for (const ws of wss.clients) {
      const peer = ws as WebSocket & { alive?: boolean };
      if (peer.alive === false) { ws.terminate(); continue; }
      peer.alive = false; ws.ping(); ws.once("pong", () => { peer.alive = true; });
    }
  }, 1000);
  watchdog.unref();
  return {
    async listen() { await new Promise<void>((resolve, reject) => {
      http.once("error", reject);
      http.listen(options.port ?? 8082, options.host ?? "127.0.0.1", () => { http.removeListener("error", reject); resolve(); });
    }); return http.address(); },
    async close() { clearInterval(watchdog); for (const command of commands.values()) clearTimeout(command.timer);
      for (const ws of wss.clients) ws.terminate(); await new Promise<void>(resolve => wss.close(() => http.close(() => resolve()))); },
  };
}
