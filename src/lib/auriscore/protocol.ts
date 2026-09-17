/**
 * Tipe pesan protokol AurisCore — SALINAN dari
 * mini-services/mock-device/protocol.ts (sumber kebenaran).
 * Setiap perubahan wajib disinkronkan di kedua file pada waktu yang sama dan
 * dicatat di DECISIONS.md. Jangan membuat monorepo atau paket bersama.
 */

export const PROTOCOL_VERSION = 1;

export const ORGAN_MODES = ["mitral", "aortic", "pulmonic", "tricuspid"] as const;
export type OrganMode = (typeof ORGAN_MODES)[number];

export const QUALITY_FLAGS = ["good", "fair", "poor"] as const;
export type QualityFlag = (typeof QUALITY_FLAGS)[number];

/** Server → klien. Dikirim sekali saat koneksi terbuka. */
export interface HelloMsg {
  type: "hello";
  protocol: number;
  device: string;
  fw: string;
  samplingRate: number;
  channels: number;
}

/** Server → klien. Dikirim tiap 50 ms: tepat 100 sampel int16 signed. */
export interface PcgPacketMsg {
  type: "pcg_packet";
  seq: number;
  ts: number;
  samplingRate: number;
  organMode: OrganMode;
  qualityFlag: QualityFlag;
  channels: number;
  samples: number[];
}

/** Server → klien. Dikirim tiap 1 detik. */
export interface DeviceStatusMsg {
  type: "device_status";
  ts: number;
  bpm: number;
  batteryPercent: number;
  signalQuality: QualityFlag;
}

/** Server → klien. Balasan atas perintah set_mode. */
export interface ModeAckMsg {
  type: "mode_ack";
  organMode: OrganMode;
}

export type ServerMessage =
  | HelloMsg
  | PcgPacketMsg
  | DeviceStatusMsg
  | ModeAckMsg;

/** Klien → server. Kontrol demo (bukan kontrak klinis final). */
export type ClientMessage =
  | { type: "set_mode"; organMode: OrganMode }
  | { type: "set_bpm"; bpm: number };

const SERVER_TYPES: readonly string[] = [
  "hello",
  "pcg_packet",
  "device_status",
  "mode_ack",
];

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null;

const isFiniteNumber = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v);

const isNonNegativeInt = (v: unknown): v is number =>
  isFiniteNumber(v) && Number.isInteger(v) && v >= 0;

const isPositiveInt = (v: unknown): v is number =>
  isFiniteNumber(v) && Number.isInteger(v) && v >= 1;

const isNonEmptyString = (v: unknown): v is string =>
  typeof v === "string" && v.length > 0;

const isOrganMode = (v: unknown): v is OrganMode =>
  typeof v === "string" && (ORGAN_MODES as readonly string[]).includes(v);

const isQualityFlag = (v: unknown): v is QualityFlag =>
  typeof v === "string" && (QUALITY_FLAGS as readonly string[]).includes(v);

/**
 * Validasi dan parse satu pesan server (objek hasil JSON.parse atau apa pun).
 * - Pesan bertipe tidak dikenal → null diam-diam (kompatibilitas ke depan:
 *   penerima wajib mengabaikan pesan bertipe tidak dikenal).
 * - Pesan dikenal tapi tidak valid → console.warn + null.
 * - Tidak pernah melempar exception.
 */
export function parseServerMessage(raw: unknown): ServerMessage | null {
  if (!isRecord(raw)) return null;
  const type = raw.type;

  if (typeof type !== "string" || !SERVER_TYPES.includes(type)) return null;

  if (type === "hello") {
    if (
      !isFiniteNumber(raw.protocol) ||
      !isNonEmptyString(raw.device) ||
      !isNonEmptyString(raw.fw) ||
      !isPositiveInt(raw.samplingRate) ||
      !isPositiveInt(raw.channels)
    ) {
      console.warn("[pcg] pesan hello tidak valid, diabaikan:", raw);
      return null;
    }
    return {
      type,
      protocol: raw.protocol,
      device: raw.device,
      fw: raw.fw,
      samplingRate: raw.samplingRate,
      channels: raw.channels,
    };
  }

  if (type === "pcg_packet") {
    if (
      !isNonNegativeInt(raw.seq) ||
      !isFiniteNumber(raw.ts) ||
      !isPositiveInt(raw.samplingRate) ||
      !isOrganMode(raw.organMode) ||
      !isQualityFlag(raw.qualityFlag) ||
      !isPositiveInt(raw.channels) ||
      !Array.isArray(raw.samples) ||
      raw.samples.length === 0 ||
      !raw.samples.every(isFiniteNumber)
    ) {
      // Jangan cetak seluruh isi (samples panjang) — cukup ringkas.
      console.warn(
        `[pcg] pesan pcg_packet tidak valid (seq=${String(raw.seq)}), diabaikan`
      );
      return null;
    }
    return {
      type,
      seq: raw.seq,
      ts: raw.ts,
      samplingRate: raw.samplingRate,
      organMode: raw.organMode,
      qualityFlag: raw.qualityFlag,
      channels: raw.channels,
      samples: raw.samples as number[],
    };
  }

  if (type === "device_status") {
    if (
      !isFiniteNumber(raw.ts) ||
      !isFiniteNumber(raw.bpm) ||
      !isFiniteNumber(raw.batteryPercent) ||
      !isQualityFlag(raw.signalQuality)
    ) {
      console.warn("[pcg] pesan device_status tidak valid, diabaikan:", raw);
      return null;
    }
    return {
      type,
      ts: raw.ts,
      bpm: raw.bpm,
      batteryPercent: raw.batteryPercent,
      signalQuality: raw.signalQuality,
    };
  }

  // type === "mode_ack"
  if (!isOrganMode(raw.organMode)) {
    console.warn("[pcg] pesan mode_ack tidak valid, diabaikan:", raw);
    return null;
  }
  return { type, organMode: raw.organMode };
}
