/** No-audio engineering handshake. This client never requests recording/inference. */
import { parseDeviceHello } from "./device-protocol.ts";

export interface LinkTestState {
  paired: boolean;
  device: string | null;
  gatewayRttMs: number | null;
  error: string | null;
}
export class LinkTestConnection {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private pending: { id: string; time: number } | null = null;
  private sequence = 0;
  private state: LinkTestState = { paired: false, device: null, gatewayRttMs: null, error: null };
  constructor(private readonly changed: (state: LinkTestState) => void,
    private readonly makeSocket = (url: string) => new WebSocket(url),
    private readonly now = () => performance.now()) {}
  private update(change: Partial<LinkTestState>) {
    this.state = { ...this.state, ...change }; this.changed({ ...this.state });
  }
  connect(url: string, token: string) {
    const parsed = new URL(url);
    if (!["ws:", "wss:"].includes(parsed.protocol) || parsed.pathname !== "/browser"
      || parsed.username || parsed.password || parsed.search || parsed.hash || token.length < 16)
      throw Error("Periksa URL gateway dan kode pairing (minimal 16 karakter).");
    this.close();
    const socket = this.makeSocket(url); this.socket = socket;
    const current = () => this.socket === socket;
    socket.onopen = () => { if (current()) socket.send(JSON.stringify({ type: "authenticate", token })); };
    socket.onmessage = event => {
      if (!current()) return;
      try {
        if (typeof event.data !== "string") throw Error("Audio tidak diterima pada halaman uji koneksi.");
        const message = JSON.parse(event.data);
        if (message.type === "authenticated" && message.role === "browser") {
          this.update({ paired: true, error: null });
          if (!this.timer) this.timer = setInterval(() => this.probe(), 2000);
          this.probe();
        } else if (message.type === "device_hello") {
          if (!this.state.paired) throw Error("Gateway belum dipasangkan.");
          const hello = parseDeviceHello(message);
          const bench = hello.source === "engineering" && hello.device === "ESP32S3-NO-MIC-LINK-TEST"
            && hello.fw === "wifi-link-test-1";
          const capture = hello.source === "hardware" && hello.device === "ESP32S3-INMP441-WIFI"
            && ["wifi-capture-0.2.0", "wifi-capture-0.3.0"].includes(hello.fw);
          if (!bench && !capture) throw Error("Perangkat bukan firmware uji atau AurisCore capture yang didukung.");
          this.update({ device: hello.device, error: null });
        } else if (message.type === "device_state") {
          if (!["ready", "streaming"].includes(message.status)) this.update({ device: null });
        } else if (message.type === "heartbeat_ack" && this.pending && this.pending.id === message.id) {
          const rtt = this.now() - this.pending.time; this.pending = null;
          this.update({ gatewayRttMs: Math.max(0, rtt) });
        }
      } catch (error) { this.close(error instanceof Error ? error.message : "Pesan gateway tidak valid."); }
    };
    socket.onerror = () => { if (current()) this.close("Gateway tidak terjangkau. Periksa jaringan dan pairing."); };
    socket.onclose = () => { if (current()) this.close("Koneksi terputus atau pairing ditolak. Tutup browser pengendali lain."); };
  }
  private probe() {
    if (!this.state.paired || this.socket?.readyState !== 1) return;
    if (this.pending && this.now() - this.pending.time > 3000) this.update({ gatewayRttMs: null });
    if (this.pending && this.now() - this.pending.time <= 3000) return;
    this.pending = { id: `link-${++this.sequence}`, time: this.now() };
    this.socket.send(JSON.stringify({ type: "heartbeat", id: this.pending.id }));
  }
  close(error: string | null = null) {
    if (this.timer) clearInterval(this.timer);
    this.timer = null; this.pending = null;
    const socket = this.socket; this.socket = null; socket?.close();
    this.update({ paired: false, device: null, gatewayRttMs: null, error });
  }
}
