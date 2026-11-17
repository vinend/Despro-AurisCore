"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAccount } from "@/components/auriscore/account-panel";
import { accountClient } from "@/lib/auriscore/account-client";
import { listSessions, pendingSessions, queueSession, removePending, sha256, syncSession,
  type SavedSession, type PendingSession } from "@/lib/auriscore/session-repository";
import type { HistoryEntry } from "@/lib/auriscore/recording-session";

export function useSessionHistory() {
  const { user } = useAccount();
  const [entries, setEntries] = useState<SavedSession[]>([]);
  const [loadedFor, setLoadedFor] = useState<string | undefined>();
  const [message, setMessage] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [saving, setSaving] = useState(false);
  const owner = useRef(user?.id);
  const processing = useRef(false);
  const savedFiles = useRef(new WeakSet<File>());
  useEffect(() => { owner.current = user?.id; }, [user?.id]);
  const refresh = useCallback(async () => {
    if (!user) return;
    const rows = await listSessions(accountClient(), user.id);
    if (owner.current === user.id) { setEntries(rows); setLoadedFor(user.id); setMore(rows.length === 30); }
  }, [user]);
  const retry = useCallback(async () => {
    if (!user || processing.current) return;
    processing.current = true;
    try {
      const queued = await pendingSessions(user.id);
      if (owner.current !== user.id) return;
      setSaving(true);
      for (const pending of queued) {
        if (owner.current !== user.id) return;
        await syncSession(accountClient(), pending);
        await removePending(pending.record.id);
      }
      await refresh();
      if (owner.current === user.id) setMessage("Riwayat tersinkron.");
    } catch (error) {
      if (owner.current === user.id) setMessage(error instanceof Error ? error.message : "Sinkronisasi belum berhasil.");
    } finally { processing.current = false; setSaving(false); }
  }, [refresh, user]);
  useEffect(() => {
    if (!user) return;
    const synchronize = () => { void retry(); };
    const scheduled = window.setTimeout(synchronize, 0);
    window.addEventListener("online", synchronize);
    const visible = () => { if (!document.hidden) synchronize(); };
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.clearTimeout(scheduled);
      window.removeEventListener("online", synchronize);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [user?.id, retry]);

  const save = useCallback(async (file: File, entry: HistoryEntry, userId: string | undefined) => {
    if (!userId || savedFiles.current.has(file)) return;
    savedFiles.current.add(file);
    try {
      const id = crypto.randomUUID();
      const pending: PendingSession = { audio: file, record: {
        id, user_id: userId, recorded_at: new Date(entry.ts).toISOString(), mode: entry.mode, source: entry.source,
        duration_ms: Math.round(entry.durationMs), result: entry.result, audio_path: `${userId}/${id}.wav`,
        audio_sha256: await sha256(file), audio_bytes: file.size, sync_state: "uploading",
      } };
      await queueSession(pending);
      setMessage("Rekaman tersimpan lokal. Menyinkronkan…");
      if (owner.current === userId) await retry();
    } catch { savedFiles.current.delete(file); setMessage("Rekaman belum tersimpan. Coba simpan lagi sebelum meninggalkan halaman."); }
  }, [retry]);
  const loadMore = async () => {
    if (!user || !entries.length) return;
    try {
      const rows = await listSessions(accountClient(), user.id, entries.at(-1));
      if (owner.current === user.id) { setEntries(current => [...current, ...rows]); setMore(rows.length === 30); }
    } catch { setMessage("Riwayat berikutnya belum dapat dimuat."); }
  };
  return { entries: loadedFor === user?.id ? entries : [], message, saving,
    more: loadedFor === user?.id && more, save, retry, loadMore };
}
