"use client";

import { memo, useEffect, useRef, useState } from "react";

import type { RingBuffer } from "@/lib/auriscore/ring-buffer";
import { cn } from "@/lib/utils";

interface PcgWaveformProps {
  buffer: RingBuffer;
  /** Bertambah tiap paket masuk — canvas hanya menggambar saat nilainya berubah. */
  versionRef: { current: number };
  /** Jendela tampil dalam detik (default 5 sesuai spesifikasi). */
  windowSeconds?: number;
  className?: string;
}

/** Warna cadangan bila CSS variables tidak terbaca (nilai sama dengan tokens). */
const FALLBACK_COLORS = {
  stroke: "#2dd4bf",
  grid: "rgba(148, 163, 184, 0.16)",
  bg: "#0f172a",
};

/**
 * Canvas gelombang PCG bergulir (seksi 8):
 * - Ukuran mengikuti container dengan devicePixelRatio, dipantau ResizeObserver.
 * - Loop requestAnimationFrame; hanya menggambar bila ada data baru atau resize.
 * - Peak envelope: tiap kolom piksel digambar garis vertikal min–maks sampel
 *   yang tercakup kolom itu — akurat dan murah untuk 10.000 sampel.
 * - Sumbu y: garis nol di tengah, nilai int16 penuh dipetakan ke 90% tinggi
 *   area, skala tetap tanpa auto-scale.
 * - Grid samar: vertikal tiap 1 detik (berjangkar tepi kanan), horizontal tiap
 *   seperempat tinggi.
 * - Warna dari CSS variables --pcg-stroke/--pcg-grid/--pcg-bg (token desain,
 *   TODO-FIGMA sampai token Figma tersedia).
 * - Tanpa alokasi array per frame: readWindow memakai buffer internal yang
 *   dipakai ulang.
 * - Kembali dari tab tersembunyi: jendela selalu membaca N detik TERAKHIR
 *   sehingga tumpukan data lebih dari jendela otomatis dibuang (fast-forward,
 *   backlog tidak dikejar).
 */
export const PcgWaveform = memo(function PcgWaveform({
  buffer,
  versionRef,
  windowSeconds = 5,
  className,
}: PcgWaveformProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [hasData, setHasData] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let cssW = 0;
    let cssH = 0;
    let resizeDirty = true;
    let lastVersion = -1;
    let raf = 0;
    const colors = { ...FALLBACK_COLORS };

    const readColors = () => {
      const computed = getComputedStyle(container);
      const stroke = computed.getPropertyValue("--pcg-stroke").trim();
      const grid = computed.getPropertyValue("--pcg-grid").trim();
      const bg = computed.getPropertyValue("--pcg-bg").trim();
      if (stroke) colors.stroke = stroke;
      if (grid) colors.grid = grid;
      if (bg) colors.bg = bg;
    };

    const applySize = () => {
      const dpr = window.devicePixelRatio || 1;
      cssW = container.clientWidth;
      cssH = container.clientHeight;
      if (cssW <= 0 || cssH <= 0) return;
      canvas.width = Math.max(1, Math.round(cssW * dpr));
      canvas.height = Math.max(1, Math.round(cssH * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      readColors();
      resizeDirty = true;
    };

    applySize();
    const observer = new ResizeObserver(applySize);
    observer.observe(container);

    const onVisibility = () => {
      // Paksa gambar ulang saat tab kembali terlihat.
      if (document.visibilityState === "visible") resizeDirty = true;
    };
    document.addEventListener("visibilitychange", onVisibility);

    const draw = () => {
      if (cssW <= 0 || cssH <= 0) return;

      // Latar gelap.
      ctx.fillStyle = colors.bg;
      ctx.fillRect(0, 0, cssW, cssH);

      // Grid samar: vertikal tiap 1 detik (berjangkar tepi kanan), horizontal
      // tiap seperempat tinggi.
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      const pxPerSecond = cssW / windowSeconds;
      for (let k = 0; k <= windowSeconds; k++) {
        const x = Math.round(cssW - k * pxPerSecond) + 0.5;
        ctx.moveTo(x, 0);
        ctx.lineTo(x, cssH);
      }
      for (let q = 1; q <= 3; q++) {
        const y = Math.round((cssH * q) / 4) + 0.5;
        ctx.moveTo(0, y);
        ctx.lineTo(cssW, y);
      }
      ctx.stroke();

      // Jendela data (N detik terakhir), digambar right-aligned: sampel
      // terbaru selalu di tepi kanan kanvas.
      const { data, length } = buffer.readWindow(windowSeconds);
      const has = length > 0;
      setHasData((prev) => (prev === has ? prev : has));
      if (!has) return;

      const midY = cssH / 2;
      // Skala tetap: nilai int16 penuh dipetakan ke 90% tinggi area.
      const scale = (0.9 * cssH) / 2 / 32767;
      const columns = Math.max(1, Math.round(cssW));
      const windowSamples = Math.round(windowSeconds * buffer.samplingRate);

      ctx.strokeStyle = colors.stroke;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      for (let x = 0; x < columns; x++) {
        // Posisi virtual dalam jendela (0..windowSamples), lalu dipetakan ke
        // indeks data right-aligned.
        const p0 = Math.floor((windowSamples * x) / columns);
        let p1 = Math.floor((windowSamples * (x + 1)) / columns);
        if (p1 <= p0) p1 = p0 + 1;
        let i0 = length - windowSamples + p0;
        let i1 = length - windowSamples + p1;
        if (i1 <= 0) continue; // kolom kiri belum terisi data
        if (i0 < 0) i0 = 0;
        if (i1 > length) i1 = length;
        if (i0 >= i1) continue;

        let min = Infinity;
        let max = -Infinity;
        for (let i = i0; i < i1; i++) {
          const v = data[i];
          if (v < min) min = v;
          if (v > max) max = v;
        }
        let yTop = midY - max * scale;
        let yBottom = midY - min * scale;
        if (yBottom - yTop < 1) {
          const center = (yTop + yBottom) / 2;
          yTop = center - 0.5;
          yBottom = center + 0.5;
        }
        if (yTop < 0) yTop = 0;
        if (yBottom > cssH) yBottom = cssH;
        ctx.moveTo(x + 0.5, yTop);
        ctx.lineTo(x + 0.5, yBottom);
      }
      ctx.stroke();
    };

    const loop = () => {
      raf = requestAnimationFrame(loop);
      const version = versionRef.current;
      if (!resizeDirty && version === lastVersion) return;
      lastVersion = version;
      resizeDirty = false;
      draw();
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [buffer, versionRef, windowSeconds]);

  return (
    <div
      ref={containerRef}
      className={cn("pcg-scope relative h-full w-full", className)}
    >
      <canvas
        ref={canvasRef}
        className="block h-full w-full"
        role="img"
        aria-label="Gelombang fonokardiogram (PCG) bergulir, jendela 5 detik terakhir"
      />
      {!hasData && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-400">
            Menunggu data dari perangkat…
          </span>
        </div>
      )}
    </div>
  );
});
