"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  PcgConnection,
  resolveDeviceUrl,
  type PcgConnectionState,
} from "@/lib/auriscore/pcg-connection";
import { RingBuffer } from "@/lib/auriscore/ring-buffer";
import {
  EXPECTED_SAMPLING_RATE,
  PROTOCOL_VERSION,
  type DeviceStatusMsg,
  type HelloMsg,
  type OrganMode,
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
  setOrganMode: (mode: OrganMode) => void;
  commitBpm: (bpm: number) => void;
}

/**
 * Hook utama stream PCG: memiliki PcgConnection dan RingBuffer.
 *
 * Paket PCG TIDAK memicu render React (hanya menaikkan versionRef yang dibaca
 * loop requestAnimationFrame) supaya 20 paket/detik tidak menimbulkan re-render
 * seluruh pohon UI. Render React hanya terjadi saat status (1 dtk), mode,
 * atau state koneksi berubah.
 */
export function usePcgStream(): PcgStream {
  // Buffer gelombang dibuat sekali per komponen lewat lazy state initializer
  // (bukan ref) agar tidak ada akses ref saat render.
  const [ring] = useState(
    () => new RingBuffer(EXPECTED_SAMPLING_RATE, EXPECTED_SAMPLING_RATE * 10)
  );

  const versionRef = useRef(0);
  const connRef = useRef<PcgConnection | null>(null);
  const modeRef = useRef<OrganMode>("mitral");

  const [state, setState] = useState<PcgConnectionState>("connecting");
  const [hello, setHello] = useState<HelloMsg | null>(null);
  const [status, setStatus] = useState<DeviceStatusMsg | null>(null);
  const [organMode, setOrganModeState] = useState<OrganMode>("mitral");
  const [bpmDraft, setBpmDraft] = useState<number | null>(null);

  useEffect(() => {
    const connection = new PcgConnection(resolveDeviceUrl(), {
      onHello: (msg) => {
        setHello(msg);
        if (msg.protocol !== PROTOCOL_VERSION) {
          console.warn(
            `[pcg] versi protokol perangkat ${msg.protocol} tidak sama dengan aplikasi ${PROTOCOL_VERSION}`
          );
        }
      },
      onPacket: (msg) => {
        ring.pushPacket(msg.seq, msg.samples, msg.samplingRate);
        versionRef.current += 1;
        // Sinkronkan label mode dari paket (menutupi reconnect dan perubahan
        // mode yang terjadi di sisi perangkat).
        if (msg.organMode !== modeRef.current) {
          modeRef.current = msg.organMode;
          setOrganModeState(msg.organMode);
        }
      },
      onStatus: (msg) => setStatus(msg),
      onModeAck: (msg) => {
        // Spesifikasi seksi 9: setelah mode_ack diterima, kosongkan buffer
        // gelombang dan perbarui label.
        ring.clear();
        modeRef.current = msg.organMode;
        setOrganModeState(msg.organMode);
      },
      onStateChange: (next) => {
        setState(next);
        if (next === "connected") {
          // Reconnect berhasil → reset penomoran urut yang diharapkan
          // (seksi 7): server memulai seq dari 0 lagi.
          ring.resetSequence();
          setBpmDraft(null);
        } else if (next === "disconnected") {
          setHello(null);
        }
      },
    });

    connRef.current = connection;
    connection.connect();

    return () => {
      connection.close();
      connRef.current = null;
    };
  }, [ring]);

  const setOrganMode = useCallback((mode: OrganMode) => {
    connRef.current?.setMode(mode);
  }, []);

  const commitBpm = useCallback((bpm: number) => {
    setBpmDraft(bpm);
    connRef.current?.setBpm(bpm);
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
    setOrganMode,
    commitBpm,
  };
}
