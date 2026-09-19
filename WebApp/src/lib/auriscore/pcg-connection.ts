/**
 * Transport WebSocket ke perangkat AurisCore (untuk prototipe: mock-device).
 *
 * - Validasi tiap pesan masuk; pesan tidak valid diabaikan dan dicatat ke
 *   console sebagai peringatan — tidak pernah melempar exception.
 * - Pesan bertipe tidak dikenal diabaikan diam-diam (kompatibilitas ke depan).
 * - Reconnect otomatis: tunda 1 detik, lalu 2, lalu maksimum 5 detik,
 *   diulang terus sampai tersambung.
 * - URL default relatif terhadap origin halaman (melalui gateway +
 *   XTransformPort, tanpa alamat absolut ke port lokal). Parameter URL
 *   `?device=ws://...` menimpa default — mekanisme menukar ke perangkat
 *   ESP32 sungguhan di masa depan tanpa perubahan kode.
 */

import {
  parseServerMessage,
  type ClientMessage,
  type DeviceStatusMsg,
  type HelloMsg,
  type ModeAckMsg,
  type OrganMode,
  type PcgPacketMsg,
} from "./protocol";

export type PcgConnectionState = "connecting" | "connected" | "disconnected";

export interface PcgConnectionHandlers {
  onHello?: (msg: HelloMsg) => void;
  onPacket?: (msg: PcgPacketMsg) => void;
  onStatus?: (msg: DeviceStatusMsg) => void;
  onModeAck?: (msg: ModeAckMsg) => void;
  onStateChange?: (state: PcgConnectionState) => void;
}

/** Port mock-device (mini-services/mock-device), diteruskan gateway lewat XTransformPort. */
export const MOCK_DEVICE_PORT = 8081;

/**
 * URL WebSocket perangkat.
 * Default: ws(s)://<origin>/ws?XTransformPort=8081 (relatif, lewat gateway).
 * Override: parameter URL ?device=ws://... (perangkat asli di masa depan).
 */
export function resolveDeviceUrl(): string {
  if (typeof window === "undefined") return "";
  const override = new URLSearchParams(window.location.search).get("device");
  if (override) return override;
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}/ws?XTransformPort=${MOCK_DEVICE_PORT}`;
}

/** Tunda reconnect: 1 dtk, 2 dtk, lalu maksimum 5 dtk (diulang terus). */
const RECONNECT_DELAYS_MS = [1000, 2000, 5000];

export class PcgConnection {
  private ws: WebSocket | null = null;
  private readonly url: string;
  private state: PcgConnectionState = "disconnected";
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private manualClose = false;

  constructor(url: string, private readonly handlers: PcgConnectionHandlers) {
    this.url = url;
  }

  connect(): void {
    this.manualClose = false;
    this.openSocket();
  }

  get connectionState(): PcgConnectionState {
    return this.state;
  }

  send(message: ClientMessage): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn("[pcg] kirim dilewati karena tidak terhubung:", message.type);
    }
  }

  /** Kontrol demo: ganti mode organ (dibalas mode_ack oleh perangkat). */
  setMode(organMode: OrganMode): void {
    this.send({ type: "set_mode", organMode });
  }

  /** Kontrol demo: ubah BPM (rentang 60–100, berlaku mulai beat berikutnya). */
  setBpm(bpm: number): void {
    this.send({ type: "set_bpm", bpm });
  }

  close(): void {
    this.manualClose = true;
    this.clearReconnectTimer();
    const ws = this.ws;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
    }
    this.ws = null;
    this.setState("disconnected");
  }

  private openSocket(): void {
    this.clearReconnectTimer();
    this.setState("connecting");
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch (err) {
      console.warn("[pcg] WebSocket gagal dibuat, akan dicoba lagi:", err);
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this.setState("connected");
    };
    ws.onmessage = (event: MessageEvent) => this.handleRawMessage(event.data);
    ws.onerror = () => {
      // Detail kegagalan terlihat lewat onclose; jangan lempar exception.
    };
    ws.onclose = () => {
      if (this.manualClose) {
        this.setState("disconnected");
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    this.setState("disconnected");
    const delay =
      RECONNECT_DELAYS_MS[
        Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)
      ];
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.openSocket();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private setState(next: PcgConnectionState): void {
    if (next !== this.state) {
      this.state = next;
      this.handlers.onStateChange?.(next);
    }
  }

  private handleRawMessage(raw: unknown): void {
    let parsed: unknown = raw;
    if (typeof raw === "string") {
      try {
        parsed = JSON.parse(raw);
      } catch {
        console.warn("[pcg] pesan bukan JSON valid, diabaikan");
        return;
      }
    }
    const msg = parseServerMessage(parsed);
    if (msg === null) return;
    switch (msg.type) {
      case "hello":
        this.handlers.onHello?.(msg);
        break;
      case "pcg_packet":
        this.handlers.onPacket?.(msg);
        break;
      case "device_status":
        this.handlers.onStatus?.(msg);
        break;
      case "mode_ack":
        this.handlers.onModeAck?.(msg);
        break;
    }
  }
}
