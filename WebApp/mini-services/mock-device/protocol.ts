// protocol.ts -- SUMBER KEBENARAN kontrak pesan WebSocket mock-device AurisCore.
// Salinan aplikasi web: src/lib/auriscore/protocol.ts.
// Aturan (DECISIONS.md seksi 4): setiap perubahan tipe WAJIB diedit di kedua
// file pada waktu yang sama. Jangan membuat monorepo / paket bersama.

export const PROTOCOL_VERSION = 1;
export const DEVICE_NAME = 'AurisCore-Mock';
export const FIRMWARE_VERSION = '0.1.0-mock';

/** Laju sampling PCG (Hz), mengikuti spesifikasi PDS dan pipeline AI. */
export const SAMPLING_RATE = 8000;
/** Jumlah kanal audio. Draf 1 kanal (pertanyaan terbuka, lihat DECISIONS.md). */
export const CHANNELS = 1;

/** 400 sampel @ 8000 Hz = 50 ms audio per paket. */
export const SAMPLES_PER_PACKET = 400;
/** Interval pengiriman pcg_packet (realtime, per koneksi). */
export const PACKET_INTERVAL_MS = 50;
/** Interval pengiriman device_status. */
export const STATUS_INTERVAL_MS = 1000;

export const ORGAN_MODES = ['mitral', 'aortic', 'pulmonic', 'tricuspid'] as const;
export type OrganMode = (typeof ORGAN_MODES)[number];

export const QUALITY_FLAGS = ['good', 'fair', 'poor'] as const;
export type QualityFlag = (typeof QUALITY_FLAGS)[number];

export const BPM_MIN = 60;
export const BPM_MAX = 100;
/** Persentase baterai laporan device_status (mock: selalu 87). */
export const BATTERY_PERCENT_MOCK = 87;

// ---------------------------------------------------------------------------
// Pesan server -> klien (satu objek JSON dengan field "type";
// timestamp selalu epoch milidetik)
// ---------------------------------------------------------------------------

/** Dikirim sekali saat koneksi terbuka. */
export interface HelloMessage {
  type: 'hello';
  /** Versi protokol (mulai dari 1). */
  protocol: number;
  /** Nama perangkat. */
  device: string;
  /** Versi firmware. */
  fw: string;
  /** Laju sampling (Hz). */
  samplingRate: number;
  /** Jumlah kanal. */
  channels: number;
}

/** Dikirim tiap PACKET_INTERVAL_MS (50 ms realtime). */
export interface PcgPacketMessage {
  type: 'pcg_packet';
  /** Urutan paket: mulai 0 per koneksi, bertambah tepat 1 per paket. */
  seq: number;
  /** Epoch milidetik saat paket dibuat. */
  ts: number;
  samplingRate: number;
  organMode: OrganMode;
  qualityFlag: QualityFlag;
  channels: number;
  /** Tepat SAMPLES_PER_PACKET nilai int16 sebagai angka JSON. */
  samples: number[];
}

/** Dikirim tiap STATUS_INTERVAL_MS (1000 ms). */
export interface DeviceStatusMessage {
  type: 'device_status';
  /** Epoch milidetik. */
  ts: number;
  /** bpm yang berlaku saat ini. */
  bpm: number;
  /** Persentase baterai (mock: selalu 87). */
  batteryPercent: number;
  /** = qualityFlag dari pcg_packet terakhir. */
  signalQuality: QualityFlag;
}

/** Balasan atas set_mode yang valid. */
export interface ModeAckMessage {
  type: 'mode_ack';
  organMode: OrganMode;
}

export type ServerMessage =
  | HelloMessage
  | PcgPacketMessage
  | DeviceStatusMessage
  | ModeAckMessage;

// ---------------------------------------------------------------------------
// Pesan klien -> server
// ---------------------------------------------------------------------------

/** Ganti mode organ; dibalas mode_ack bila organMode valid. */
export interface SetModeMessage {
  type: 'set_mode';
  organMode: OrganMode;
}

/** Atur bpm; clamp [BPM_MIN, BPM_MAX], berlaku mulai beat berikutnya, tanpa balasan. */
export interface SetBpmMessage {
  type: 'set_bpm';
  bpm: number;
}

export type ClientMessage = SetModeMessage | SetBpmMessage;

// ---------------------------------------------------------------------------
// Helper validasi kecil (dipakai server; klien boleh meniru)
// ---------------------------------------------------------------------------

export function isOrganMode(value: unknown): value is OrganMode {
  return typeof value === 'string' && (ORGAN_MODES as readonly string[]).includes(value);
}

export function isQualityFlag(value: unknown): value is QualityFlag {
  return typeof value === 'string' && (QUALITY_FLAGS as readonly string[]).includes(value);
}

/** Batasi bpm ke rentang [BPM_MIN, BPM_MAX]. */
export function clampBpm(bpm: number): number {
  return Math.min(BPM_MAX, Math.max(BPM_MIN, bpm));
}

/** true bila value adalah pesan set_mode dengan organMode valid. */
export function isSetModeMessage(value: unknown): value is SetModeMessage {
  return isRecord(value) && value.type === 'set_mode' && isOrganMode(value.organMode);
}

/** true bila value adalah pesan set_bpm dengan bpm berupa angka berhingga. */
export function isSetBpmMessage(value: unknown): value is SetBpmMessage {
  return (
    isRecord(value) &&
    value.type === 'set_bpm' &&
    typeof value.bpm === 'number' &&
    Number.isFinite(value.bpm)
  );
}

/** Nama tipe pesan untuk logging; null bila bukan objek dengan field type string. */
export function messageTypeName(value: unknown): string | null {
  if (!isRecord(value)) return null;
  return typeof value.type === 'string' ? value.type : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
