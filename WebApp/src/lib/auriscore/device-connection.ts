import { AudioContinuity, decodeAudioFrame, parseDeviceHello, type DeviceHello } from "./device-protocol.ts";
import type { PcgConnectionHandlers, PcgConnectionState } from "./pcg-connection.ts";
export interface DeviceConnectionOptions { url: string; token: string }
/** Physical gateway connection: socket open is not device/audio readiness. */
export class DeviceConnection {
  private socket: WebSocket | null = null;
  private closed = false;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private hello: DeviceHello | null = null;
  private continuity: AudioContinuity | null = null;
  private lastAudio = 0;
  private attempt = 0;
  private started = false;
  private packetSequence = 0;
  private commandSequence = 0;
  private authenticated = false;
  private ping: { id: string; sentAt: number } | null = null;
  private lastPingAt = -Infinity;
  private currentState: PcgConnectionState = "disconnected";
  constructor(private options: DeviceConnectionOptions, private handlers: PcgConnectionHandlers & {
    onError?: (message: string) => void; onLatency?: (milliseconds: number | null) => void;
  }) {}
  private state(state: PcgConnectionState) { if (this.currentState !== state) { this.currentState = state; this.handlers.onStateChange?.(state); } }
  connect() {
    this.closed = false; this.state("connecting");
    this.authenticated = false; this.ping = null; this.lastPingAt = -Infinity;
    this.handlers.onLatency?.(null);
    const socket = new WebSocket(this.options.url); this.socket = socket; socket.binaryType = "arraybuffer";
    socket.onopen = () => { socket.send(JSON.stringify({ type: "authenticate", token: this.options.token })); };
    socket.onmessage = event => {
      if (this.socket !== socket) return;
      try {
        if (event.data instanceof ArrayBuffer) {
          if (!this.hello || !this.continuity) throw Error("Audio before device handshake");
          const frame = decodeAudioFrame(new Uint8Array(event.data));
          if (!this.continuity.accept(frame)) return;
          this.lastAudio = Date.now(); this.attempt = 0; this.state("connected");
          // Normalize into the existing capture interface; absolute sample continuity
          // is checked above, and a monotonic local seq avoids uint32 wrap problems.
          this.handlers.onPacket?.({ type: "pcg_packet", seq: this.packetSequence++, ts: frame.firstSample / 8,
            samplingRate: 8000, channels: 1, organMode: "mitral", qualityFlag: "unknown",
            samples: Array.from(frame.samples) });
          return;
        }
        const message = JSON.parse(event.data);
        if (message.type === "authenticated") {
          this.authenticated = true; this.probeLatency(); return;
        }
        if (message.type === "heartbeat_ack") {
          if (this.ping && message.id === this.ping.id) {
            this.handlers.onLatency?.(Math.max(0, performance.now() - this.ping.sentAt));
            this.ping = null;
          }
          return;
        }
        if (message.type === "device_hello") {
          this.hello = parseDeviceHello(message); this.continuity = new AudioContinuity(this.hello.streamId);
          this.packetSequence = 0; this.started = false; this.lastAudio = 0;
          this.handlers.onHello?.({ type: "hello", protocol: 2,
            device: this.hello.source === "engineering" ? `${this.hello.device}-mock-engineering` : this.hello.device,
            fw: this.hello.fw, samplingRate: 8000, channels: 1 });
          this.startStream(); return;
        }
        if (message.type === "device_state") {
          if (["offline", "error", "stale"].includes(message.status)) {
            this.hello = null; this.continuity = null; this.started = false; this.state("disconnected");
            this.handlers.onError?.(message.reason || "Perangkat belum terhubung ke gateway.");
          }
          return;
        }
        if (message.type === "command_ack" && message.ok !== true) throw Error("Device did not accept streaming command");
      } catch { this.handlers.onError?.("Stream audio rusak atau tidak sesuai protokol. Hubungkan ulang perangkat.");
        this.state("disconnected"); socket.close(1008, "Invalid stream"); }
    };
    socket.onerror = () => {};
    socket.onclose = event => {
      if (this.socket !== socket) return;
      if (event.code === 1008 && !this.hello) {
        this.closed = true; this.handlers.onError?.("Pairing atau kontrol gateway ditolak. Periksa kode pairing dan koneksi browser lain.");
      }
      this.state("disconnected"); this.hello = null; this.continuity = null; this.started = false;
      this.authenticated = false; this.ping = null; this.handlers.onLatency?.(null);
      if (!this.closed) this.retry = setTimeout(() => this.connect(), Math.min(5000, 1000 * 2 ** this.attempt++));
    };
    if (!this.watchdog) this.watchdog = setInterval(() => {
      if (this.ping && performance.now() - this.ping.sentAt > 5000) {
        this.ping = null; this.handlers.onLatency?.(null);
      }
      if (performance.now() - this.lastPingAt >= 2000) this.probeLatency();
      if (this.lastAudio && Date.now() - this.lastAudio > 2000) {
        this.lastAudio = 0; this.state("disconnected"); this.handlers.onError?.("Audio perangkat berhenti; ulangi rekaman.");
      }
    }, 500);
  }
  private probeLatency() {
    if (!this.authenticated || this.closed || this.ping || this.socket?.readyState !== WebSocket.OPEN) return;
    const id = `ping-${Date.now()}-${++this.commandSequence}`;
    const now = performance.now();
    this.ping = { id, sentAt: now }; this.lastPingAt = now;
    this.socket.send(JSON.stringify({ type: "heartbeat", id }));
  }
  private startStream() {
    if (!this.started && this.socket?.readyState === WebSocket.OPEN) {
      this.started = true;
      // Correlation ID only; authentication still uses the pairing token.
      // randomUUID is unavailable on HTTP LAN origins in mobile browsers.
      const id = `stream-${Date.now()}-${++this.commandSequence}`;
      this.socket.send(JSON.stringify({ type: "command", id, command: "start_stream" }));
    }
  }
  setIndicator(mode: "heart" | "lung" | "abdomen", phase: "idle" | "recording" | "processing" | "done" | "error") {
    if (this.authenticated && this.hello?.indicatorProtocol === 1 && this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "indicator", mode, phase }));
    }
  }
  setMode() {} // Location is browser examination metadata, not a fabricated hardware command.
  setBpm() {} // Physical acquisition cannot set a patient's BPM.
  close() {
    this.closed = true; if (this.retry) clearTimeout(this.retry); if (this.watchdog) clearInterval(this.watchdog);
    this.retry = null; this.watchdog = null;
    this.authenticated = false; this.ping = null; this.handlers.onLatency?.(null);
    const socket = this.socket; this.socket = null;
    socket?.close(); this.state("disconnected");
  }
}
