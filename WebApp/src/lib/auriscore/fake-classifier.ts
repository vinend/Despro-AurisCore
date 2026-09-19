/**
 * Klasifikasi TIRUAN untuk prototipe — BUKAN model AI dan tanpa backend.
 * Semua hasil wajib tampil dengan label "hasil simulasi" di UI
 * (aturan perilaku agent seksi 14).
 */

import type { OrganMode } from "./protocol";

/**
 * Toggle internal hasil tiruan (seksi 9: "hasil ditentukan toggle internal,
 * default Normal"). Ubah ke `true` lalu reload untuk mendemokan hasil
 * "Abnormal" — sengaja tidak diekspos ke UI.
 */
export const FORCE_ABNORMAL_RESULT = false;

export interface ClassificationResult {
  label: "Normal" | "Abnormal";
  /** Persen keyakinan acak 87–97 (tiruan). */
  confidencePercent: number;
  /** Waktu hasil dibuat (epoch ms). */
  ts: number;
  /** Durasi rekaman aktual (ms). */
  durationMs: number;
  organMode: OrganMode;
}

export function fakeClassify(
  organMode: OrganMode,
  durationMs: number
): ClassificationResult {
  const confidencePercent = 87 + Math.floor(Math.random() * 11); // 87..97 inklusif
  return {
    label: FORCE_ABNORMAL_RESULT ? "Abnormal" : "Normal",
    confidencePercent,
    ts: Date.now(),
    durationMs,
    organMode,
  };
}
