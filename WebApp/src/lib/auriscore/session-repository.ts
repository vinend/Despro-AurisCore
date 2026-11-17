import type { SupabaseClient } from "@supabase/supabase-js";
import { parseOrganAnalysisResult, type OrganAnalysisResult, type AnalysisMode } from "./analysis-result.ts";

export interface SavedSession {
  id: string;
  user_id: string;
  recorded_at: string;
  mode: AnalysisMode;
  source: string;
  duration_ms: number;
  result: OrganAnalysisResult;
  audio_path: string;
  audio_sha256: string;
  audio_bytes: number;
  sync_state: "uploading" | "ready";
}
export interface PendingSession { record: SavedSession; audio: Blob }

/** Each user's immutable session UUID is also the retry and object identity. */
export async function syncSession(client: SupabaseClient, pending: PendingSession): Promise<SavedSession> {
  const { record, audio } = pending;
  const { data: auth, error: authError } = await client.auth.getUser();
  if (authError || auth.user?.id !== record.user_id) throw new Error("Masuk kembali untuk menyimpan sesi ini.");
  let { data: existing, error } = await client.from("auriscore_sessions").select("*").eq("id", record.id).maybeSingle();
  if (error) throw new Error("Riwayat belum dapat dibaca.");
  if (!existing) {
    const inserted = await client.from("auriscore_sessions").insert(record).select().single();
    if (inserted.error) {
      // Another tab may have inserted this same immutable session.
      const concurrent = await client.from("auriscore_sessions").select("*").eq("id", record.id).maybeSingle();
      if (concurrent.error || !concurrent.data) throw new Error("Sesi belum dapat disimpan.");
      existing = concurrent.data;
    } else existing = inserted.data;
  }
  if (existing.audio_sha256 !== record.audio_sha256 || existing.audio_bytes !== record.audio_bytes)
    throw new Error("Identitas rekaman berbeda dari sesi tersimpan.");
  if (existing.sync_state === "ready") return existing as SavedSession;
  const upload = await client.storage.from("auriscore-recordings").upload(record.audio_path, audio, {
    contentType: "audio/wav", upsert: false,
  });
  if (upload.error) {
    // A previous attempt may have uploaded successfully before its response was lost.
    const stored = await client.storage.from("auriscore-recordings").download(record.audio_path);
    if (stored.error || !stored.data || stored.data.size !== record.audio_bytes
      || await sha256(stored.data) !== record.audio_sha256) throw new Error("Rekaman menunggu unggahan ulang.");
  }
  const finished = await client.from("auriscore_sessions").update({ sync_state: "ready" })
    .eq("id", record.id).select().single();
  if (finished.error) throw new Error("Rekaman terunggah. Penyelesaian sinkronisasi perlu dicoba lagi.");
  return finished.data as SavedSession;
}

export async function sha256(blob: Blob): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
}

export async function listSessions(client: SupabaseClient, userId: string, before?: SavedSession): Promise<SavedSession[]> {
  let query = client.from("auriscore_sessions").select("*").eq("user_id", userId).eq("sync_state", "ready")
    .order("recorded_at", { ascending: false }).order("id", { ascending: false }).limit(30);
  if (before) query = query.or(`recorded_at.lt.${before.recorded_at},and(recorded_at.eq.${before.recorded_at},id.lt.${before.id})`);
  const { data, error } = await query;
  if (error) throw new Error("Riwayat belum dapat dimuat.");
  return data.map(row => ({ ...row, result: parseOrganAnalysisResult(row.result, row.mode) })) as SavedSession[];
}

function localDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("auriscore-session-outbox", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("sessions", { keyPath: "record.id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error("Penyimpanan lokal tidak tersedia."));
  });
}
async function localOperation<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await localDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction("sessions", mode);
    const request = operation(transaction.objectStore("sessions"));
    transaction.oncomplete = () => { db.close(); resolve(request.result); };
    transaction.onabort = () => { db.close(); reject(new Error("Rekaman belum tersimpan lokal.")); };
    transaction.onerror = () => { db.close(); reject(new Error("Penyimpanan lokal gagal.")); };
  });
}
export const queueSession = (session: PendingSession) => localOperation("readwrite", store => store.put(session));
export const removePending = (id: string) => localOperation("readwrite", store => store.delete(id));
export async function pendingSessions(userId: string): Promise<PendingSession[]> {
  return (await localOperation<PendingSession[]>("readonly", store => store.getAll()))
    .filter(session => session.record.user_id === userId);
}
