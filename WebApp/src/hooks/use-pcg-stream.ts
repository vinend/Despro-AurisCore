"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  PcgConnection,
  resolveDeviceUrl,
  type PcgConnectionState,
} from "@/lib/auriscore/pcg-connection";
import { DeviceConnection } from "@/lib/auriscore/device-connection";
import { RingBuffer } from "@/lib/auriscore/ring-buffer";
import {
  EXPECTED_SAMPLING_RATE,
  PROTOCOL_VERSION,
  type DeviceStatusMsg,
  type HelloMsg,
  type OrganMode,
  type PcgPacketMsg,
} from "@/lib/auriscore/protocol";

export interface PcgStream {
  /** Buffer gelombang (kapasitas 10 dtk; canvas membaca jendela 5 dtk terakhir). */
  ring: RingBuffer;
  /** Versi data — bertambah tiap paket masuk; dipakai canvas untuk tahu kapan redraw. */
  versionRef: { current: number };
  state: PcgConnectionState;
  hello: HelloMsg | null;
  status: DeviceStatusMsg | null;
  organMode: OrganMode;
  bpm: number | null;
  isMock: boolean;
  isConnected: boolean;
  isHardware: boolean;
  error: string | null;
  setOrganMode: (mode: OrganMode) => void;
  commitBpm: (bpm: number) => void;
  subscribePacket: (listener: (packet: PcgPacketMsg) => void) => () => void;
  subscribeConnection: (listener: (state: PcgConnectionState) => void) => () => void;
}

/**
 * Hook utama stream PCG: memiliki PcgConnection dan RingBuffer.
 *
 * Paket PCG TIDAK memicu render React (hanya menaikkan versionRef yang dibaca
 * loop requestAnimationFrame) supaya 20 paket/detik tidak menimbulkan re-render
 * seluruh pohon UI. Render React hanya terjadi saat status (1 dtk), mode,
 * atau state koneksi berubah.
 */
export function usePcgStream(settings: { source: "mock" | "hardware"; url: string; token: string } = { source: "mock", url: "", token: "" }): PcgStream {
  const { source, url, token } = settings;
  const [error, setError] = useState<string | null>(null);
  // Buffer gelombang dibuat sekali per komponen lewat lazy state initializer
  // (bukan ref) agar tidak ada akses ref saat render.
  const [ring] = useState(
    () => new RingBuffer(EXPECTED_SAMPLING_RATE, EXPECTED_SAMPLING_RATE * 10)
  );

  const versionRef = useRef(0);
  const connRef = useRef<PcgConnection | DeviceConnection | null>(null);
  const modeRef = useRef<OrganMode>("mitral");
  const packetListeners = useRef(new Set<(packet: PcgPacketMsg) => void>());
  const connectionListeners = useRef(new Set<(state: PcgConnectionState) => void>());

  const [state, setState] = useState<PcgConnectionState>("connecting");
  const [hello, setHello] = useState<HelloMsg | null>(null);
  const [status, setStatus] = useState<DeviceStatusMsg | null>(null);
  const [organMode, setOrganModeState] = useState<OrganMode>("mitral");
  const [bpmDraft, setBpmDraft] = useState<number | null>(null);

  useEffect(() => {
    const handlers = {
      onHello: (msg: HelloMsg) => {
        setError(null);
        setHello(msg);
        if (source === "mock" && msg.protocol !== PROTOCOL_VERSION) {
          console.warn(
            `[pcg] versi protokol perangkat ${msg.protocol} tidak sama dengan aplikasi ${PROTOCOL_VERSION}`
          );
        }
      },
      onPacket: (msg: PcgPacketMsg) => {
        ring.pushPacket(msg.seq, msg.samples, msg.samplingRate);
        for (const listener of packetListeners.current) listener(msg);
        versionRef.current += 1;
        // Sinkronkan label mode dari paket (menutupi reconnect dan perubahan
        // mode yang terjadi di sisi perangkat).
        if (msg.organMode !== modeRef.current) {
          modeRef.current = msg.organMode;
          setOrganModeState(msg.organMode);
        }
      },
      onStatus: (msg: DeviceStatusMsg) => setStatus(msg),
      onModeAck: (msg: { organMode: OrganMode }) => {
        // Spesifikasi seksi 9: setelah mode_ack diterima, kosongkan buffer
        // gelombang dan perbarui label.
        ring.clear();
        modeRef.current = msg.organMode;
        setOrganModeState(msg.organMode);
      },
      onStateChange: (next: PcgConnectionState) => {
        if (next === "connecting") { setHello(null); setStatus(null); setError(null); }
        setState(next);
        for (const listener of connectionListeners.current) listener(next);
        if (next === "connected") {
          // Reconnect berhasil → reset penomoran urut yang diharapkan
          // (seksi 7): server memulai seq dari 0 lagi.
          ring.resetSequence();
          setBpmDraft(null);
        } else if (next === "disconnected") {
          setHello(null);
        }
      },
      onError: (message: string) => setError(message),
    };
    ring.clear(); ring.resetSequence();
    const connection = source === "hardware" ? new DeviceConnection({ url, token }, handlers)
      : new PcgConnection(resolveDeviceUrl(), handlers);

    connRef.current = connection;
    connection.connect();

    return () => {
      connection.close();
      connRef.current = null;
    };
  }, [ring, source, url, token]);

  const setOrganMode = useCallback((mode: OrganMode) => {
    connRef.current?.setMode(mode);
  }, []);

  const commitBpm = useCallback((bpm: number) => {
    setBpmDraft(bpm);
    connRef.current?.setBpm(bpm);
  }, []);

  const subscribePacket = useCallback((listener: (packet: PcgPacketMsg) => void) => {
    packetListeners.current.add(listener);
    return () => { packetListeners.current.delete(listener); };
  }, []);
  const subscribeConnection = useCallback((listener: (state: PcgConnectionState) => void) => {
    connectionListeners.current.add(listener);
    return () => { connectionListeners.current.delete(listener); };
  }, []);

  const bpm = bpmDraft ?? status?.bpm ?? null;
  const isMock = hello !== null && hello.device.toLowerCase().includes("mock");

  return {
    ring,
    versionRef,
    state,
    hello,
    status,
    organMode,
    bpm,
    isMock,
    isConnected: state === "connected",
    isHardware: source === "hardware",
    error,
    setOrganMode,
    commitBpm,
    subscribePacket,
    subscribeConnection,
  };
}
