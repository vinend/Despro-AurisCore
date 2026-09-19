/**
 * Buffer melingkar untuk sampel PCG + penanganan nomor urut (seq).
 *
 * Logika gap/duplikat sengaja diletakkan di sini (bukan di transport)
 * agar dapat diuji unit tanpa WebSocket:
 * - seq melompat maju   → sisipkan sampel hening sepanjang durasi yang hilang.
 * - seq <= seq terakhir → paket duplikat/telat, dibuang tanpa mengubah isi.
 */

export class RingBuffer {
  readonly capacity: number;
  readonly samplingRate: number;

  private readonly data: Float32Array;
  /**
   * Buffer hasil readWindow — sengaja dipakai ulang antar panggilan supaya
   * loop render tidak mengalokasikan array baru per frame (target 60 fps).
   */
  private readonly scratch: Float32Array;
  private writeIndex = 0;
  private count = 0;
  private lastSeq: number | null = null;

  constructor(samplingRate = 8000, capacity = 80000) {
    // 80.000 sampel @ 8000 Hz = 10 detik (spesifikasi PDS dan pipeline AI).
    this.samplingRate = samplingRate;
    this.capacity = capacity;
    this.data = new Float32Array(capacity);
    this.scratch = new Float32Array(capacity);
  }

  /**
   * Terima satu paket PCG (seq + sampel). Menangani gap dan duplikat:
   * - seq <= lastSeq            → buang (duplikat/telat).
   * - seq > lastSeq + 1         → sisipkan hening untuk durasi hilang.
   * - lastSeq null (awal/reset) → terima apa adanya tanpa gap fill.
   */
  pushPacket(seq: number, samples: ArrayLike<number>, samplingRate: number): void {
    if (this.lastSeq !== null) {
      if (seq <= this.lastSeq) {
        // Duplikat atau telat: paket dibuang, isi buffer tidak berubah.
        return;
      }
      const gapPackets = seq - this.lastSeq - 1;
      if (gapPackets > 0) {
        // Durasi hilang = jumlah paket × durasi satu paket, dikonversi ke
        // laju sampling buffer.
        const gapSamples = Math.round(
          gapPackets * samples.length * (this.samplingRate / samplingRate)
        );
        this.insertSilence(gapSamples);
      }
    }
    this.pushValues(samples);
    this.lastSeq = seq;
  }

  /**
   * Kosongkan data gelombang (dipakai setelah mode_ack diterima).
   * Penomoran seq dipertahankan agar logika gap/duplikat tetap konsisten.
   */
  clear(): void {
    this.writeIndex = 0;
    this.count = 0;
  }

  /**
   * Reset penomoran urut yang diharapkan (dipakai saat reconnect berhasil —
   * server memulai ulang seq dari 0, jadi paket pertama harus diterima
   * meskipun angkanya "mundur" dari koneksi sebelumnya).
   */
  resetSequence(): void {
    this.lastSeq = null;
  }

  /**
   * Ambil jendela `seconds` detik TERAKHIR.
   * Mengembalikan { data, length }: `data` adalah buffer internal yang dipakai
   * ulang — jangan menyimpan referensinya di luar loop render.
   */
  readWindow(seconds: number): { data: Float32Array; length: number } {
    const n = Math.min(this.count, Math.round(seconds * this.samplingRate));
    if (n <= 0) return { data: this.scratch, length: 0 };
    const start = (this.writeIndex - n + this.capacity) % this.capacity;
    if (start + n <= this.capacity) {
      this.scratch.set(this.data.subarray(start, start + n));
    } else {
      const first = this.capacity - start;
      this.scratch.set(this.data.subarray(start, this.capacity), 0);
      this.scratch.set(this.data.subarray(0, n - first), first);
    }
    return { data: this.scratch, length: n };
  }

  /** Jumlah sampel yang tersedia di buffer. */
  availableSamples(): number {
    return this.count;
  }

  /** Durasi data yang tersedia (detik). */
  availableSeconds(): number {
    return this.count / this.samplingRate;
  }

  private insertSilence(n: number): void {
    if (n <= 0) return;
    if (n >= this.capacity) {
      // Keheningan lebih panjang dari kapasitas → seluruh buffer hening.
      this.data.fill(0);
      this.writeIndex = 0;
      this.count = this.capacity;
      return;
    }
    for (let i = 0; i < n; i++) {
      this.data[this.writeIndex] = 0;
      this.writeIndex = (this.writeIndex + 1) % this.capacity;
      if (this.count < this.capacity) this.count += 1;
    }
  }

  private pushValues(values: ArrayLike<number>): void {
    for (let i = 0; i < values.length; i++) {
      this.data[this.writeIndex] = values[i];
      this.writeIndex = (this.writeIndex + 1) % this.capacity;
      if (this.count < this.capacity) this.count += 1;
    }
  }
}
