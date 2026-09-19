// index.ts -- server WebSocket mock-device AurisCore (simulator stetoskop digital).
//
// Port 8081 HARDCODED -- tidak pernah dibaca dari environment.
// Browser menjangkau service ini lewat gateway Caddy yang meneruskan
// ws(s)://<host>/ws?XTransformPort=8081 ke localhost:8081 dengan path URI
// diteruskan apa adanya; karena itu WebSocketServer dibuat TANPA pembatasan
// path dan TANPA pemeriksaan header Origin.
//
// Menjalankan:
//   bun run dev             (bun --hot, aman berkat cleanup globalThis)
//   bun run start
//   tambahkan --chaos       untuk menjatuhkan ~1% pcg_packet secara acak.

import { WebSocket, WebSocketServer, type RawData } from 'ws';
import { NOISE_LEVEL, PcgSynthesizer } from './pcg';
import {
  BATTERY_PERCENT_MOCK,
  BPM_MAX,
  BPM_MIN,
  CHANNELS,
  DEVICE_NAME,
  FIRMWARE_VERSION,
  PACKET_INTERVAL_MS,
  PROTOCOL_VERSION,
  SAMPLES_PER_PACKET,
  SAMPLING_RATE,
  STATUS_INTERVAL_MS,
  clampBpm,
  isSetBpmMessage,
  isSetModeMessage,
  messageTypeName,
  type DeviceStatusMessage,
  type HelloMessage,
  type ModeAckMessage,
  type OrganMode,
  type PcgPacketMessage,
  type QualityFlag,
  type ServerMessage,
} from './protocol';

const PORT = 8081; // hardcoded, jangan baca dari env
const INITIAL_BPM = 75;
const CHAOS_MODE = process.argv.includes('--chaos');
const CHAOS_DROP_PROBABILITY = 0.01; // ~1% pcg_packet dijatuhkan saat --chaos

// Penjaga hot-reload `bun --hot`: saat modul dievaluasi ulang setelah file
// berubah, server lama masih memegang port 8081 (EADDRINUSE) -> matikan dulu
// semuanya lewat cleanup yang tersimpan di globalThis.
declare global {
  var __mockDeviceCleanup: (() => void) | undefined;
}

globalThis.__mockDeviceCleanup?.();

type IntervalId = ReturnType<typeof setInterval>;

/** State per koneksi: seq, posisi synthesizer, bpm, mode organ, timer. */
interface ClientState {
  socket: WebSocket;
  /** seq pcg_packet berikutnya (mulai 0, +1 tepat 1 per paket). */
  seq: number;
  synthesizer: PcgSynthesizer;
  organMode: OrganMode;
  /** qualityFlag pcg_packet terakhir (dipakai device_status.signalQuality). */
  lastQualityFlag: QualityFlag;
  packetTimer: IntervalId | null;
  statusTimer: IntervalId | null;
}

const clients = new Set<ClientState>();

function sendJson(socket: WebSocket, message: ServerMessage): void {
  if (socket.readyState !== WebSocket.OPEN) return;
  try {
    socket.send(JSON.stringify(message));
  } catch (error) {
    console.warn(`[mock-device] gagal mengirim pesan: ${(error as Error).message}`);
  }
}

function stopClient(state: ClientState): void {
  if (state.packetTimer !== null) clearInterval(state.packetTimer);
  if (state.statusTimer !== null) clearInterval(state.statusTimer);
  state.packetTimer = null;
  state.statusTimer = null;
}

/** Ubah data frame ws (Buffer / ArrayBuffer / Buffer[]) menjadi string UTF-8. */
function rawDataToString(data: RawData): string {
  if (Array.isArray(data)) return Buffer.concat(data).toString();
  if (data instanceof ArrayBuffer) return Buffer.from(data).toString();
  return data.toString();
}

/**
 * Aturan qualityFlag: "poor" bila noiseLevel > 0.05; selain itu acak seragam
 * antara "good" dan "fair". Mock memakai noiseLevel konstan 0.02 sehingga
 * praktis tidak pernah "poor" -- firmware ESP32 meniru ATURANNYA (dihitung
 * dari noise level perangkat sungguhan), bukan nilai acaknya.
 */
function rollQualityFlag(): QualityFlag {
  if (NOISE_LEVEL > 0.05) return 'poor';
  return Math.random() < 0.5 ? 'good' : 'fair';
}

const wss = new WebSocketServer({ port: PORT }, () => {
  console.log(
    `[mock-device] listening ws://localhost:${PORT} ` +
      `(protocol v${PROTOCOL_VERSION}, ${SAMPLING_RATE} Hz, ${CHANNELS} kanal` +
      `${CHAOS_MODE ? ', --chaos AKTIF' : ''})`,
  );
});

wss.on('error', (error: Error) => {
  console.error(`[mock-device] error server: ${error.message}`);
  process.exit(1);
});

wss.on('connection', (socket: WebSocket) => {
  const state: ClientState = {
    socket,
    seq: 0,
    synthesizer: new PcgSynthesizer(SAMPLING_RATE, INITIAL_BPM),
    organMode: 'mitral',
    lastQualityFlag: 'good',
    packetTimer: null,
    statusTimer: null,
  };
  clients.add(state);
  console.log(`[mock-device] klien tersambung (${clients.size} klien aktif)`);

  // 1) hello -- sekali di awal koneksi.
  const hello: HelloMessage = {
    type: 'hello',
    protocol: PROTOCOL_VERSION,
    device: DEVICE_NAME,
    fw: FIRMWARE_VERSION,
    samplingRate: SAMPLING_RATE,
    channels: CHANNELS,
  };
  sendJson(socket, hello);

  // 2) pcg_packet -- tiap 50 ms realtime (setInterval per koneksi, bukan
  //    as-fast-as-possible).
  state.packetTimer = setInterval(() => {
    // Synthesizer dan seq SELALU maju, termasuk saat chaos menjatuhkan paket,
    // supaya klien melihat lompatan seq dan bisa mengisi keheningan
    // (itu memang tujuan flag --chaos).
    const samples = state.synthesizer.nextSamples(SAMPLES_PER_PACKET);
    const seq = state.seq;
    state.seq += 1;
    const qualityFlag = rollQualityFlag();
    state.lastQualityFlag = qualityFlag;

    if (CHAOS_MODE && Math.random() < CHAOS_DROP_PROBABILITY) {
      console.log(`[mock-device] chaos: pcg_packet seq=${seq} dijatuhkan`);
      return;
    }

    const packet: PcgPacketMessage = {
      type: 'pcg_packet',
      seq,
      ts: Date.now(),
      samplingRate: SAMPLING_RATE,
      organMode: state.organMode,
      qualityFlag,
      channels: CHANNELS,
      samples,
    };
    sendJson(socket, packet);
  }, PACKET_INTERVAL_MS);

  // 3) device_status -- tiap 1000 ms.
  state.statusTimer = setInterval(() => {
    const status: DeviceStatusMessage = {
      type: 'device_status',
      ts: Date.now(),
      bpm: state.synthesizer.getBpm(),
      batteryPercent: BATTERY_PERCENT_MOCK,
      signalQuality: state.lastQualityFlag,
    };
    sendJson(socket, status);
  }, STATUS_INTERVAL_MS);

  // 5) set_mode / 6) set_bpm / pesan tak dikenal.
  socket.on('message', (data: RawData, isBinary: boolean) => {
    if (isBinary) {
      console.warn('[mock-device] frame biner diterima, diabaikan (prototipe hanya JSON)');
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(rawDataToString(data));
    } catch {
      console.warn('[mock-device] pesan non-JSON / JSON rusak diterima, diabaikan');
      return;
    }

    const type = messageTypeName(parsed);
    if (type === 'set_mode') {
      if (isSetModeMessage(parsed)) {
        state.organMode = parsed.organMode;
        const ack: ModeAckMessage = { type: 'mode_ack', organMode: state.organMode };
        sendJson(socket, ack);
        console.log(
          `[mock-device] set_mode: organMode=${state.organMode} (mode_ack terkirim)`,
        );
      } else {
        console.log(
          '[mock-device] set_mode dengan nilai organMode tidak valid, diabaikan',
        );
      }
      return;
    }
    if (type === 'set_bpm') {
      if (isSetBpmMessage(parsed)) {
        const clamped = clampBpm(parsed.bpm);
        state.synthesizer.setBpm(clamped);
        console.log(
          `[mock-device] set_bpm: ${parsed.bpm} diklem ke [${BPM_MIN}, ${BPM_MAX}] = ` +
            `${clamped} (berlaku mulai beat berikutnya, tanpa balasan)`,
        );
      } else {
        console.log('[mock-device] set_bpm dengan nilai bpm tidak valid, diabaikan');
      }
      return;
    }
    console.log(
      `[mock-device] pesan tak dikenal (type=${type ?? '(tanpa type)'}), ` +
        'diabaikan (aturan forward-compat)',
    );
  });

  socket.on('close', () => {
    stopClient(state);
    clients.delete(state);
    console.log(`[mock-device] klien terputus (${clients.size} klien aktif)`);
  });

  socket.on('error', (error: Error) => {
    console.warn(`[mock-device] error socket klien: ${error.message}`);
  });
});

// Penutupan rapi: dipakai oleh SIGINT/SIGTERM dan oleh evaluasi ulang hot-reload.
let serverClosed = false;

function shutdown(signal: string): void {
  console.log(`[mock-device] menerima ${signal}, mematikan service...`);
  globalThis.__mockDeviceCleanup?.();
  process.exit(0);
}

const onSigint = (): void => shutdown('SIGINT');
const onSigterm = (): void => shutdown('SIGTERM');
process.on('SIGINT', onSigint);
process.on('SIGTERM', onSigterm);

globalThis.__mockDeviceCleanup = () => {
  for (const state of clients) {
    stopClient(state);
    if (state.socket.readyState !== WebSocket.CLOSED) {
      try {
        state.socket.terminate();
      } catch {
        // abaikan
      }
    }
  }
  clients.clear();
  if (!serverClosed) {
    serverClosed = true;
    try {
      wss.close();
    } catch {
      // abaikan -- server mungkin belum / sudah tertutup
    }
  }
  // Lepas handler sinyal milik evaluasi modul ini agar `bun --hot`
  // tidak menumpuk listener SIGINT/SIGTERM antar evaluasi modul.
  process.off('SIGINT', onSigint);
  process.off('SIGTERM', onSigterm);
};
