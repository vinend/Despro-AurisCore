/*
 * AurisCore - I2S DUAL mic (organ + noise) + EKG AD8232 + klik sinkron -> Serial (biner)
 * Board target: ESP32-S3
 * FIRMWARE v4 "ecg"  (turunan LANGSUNG dari ..._v3_blockseq.ino)
 *
 * TUJUAN: uji auskultasi jantung BERSAMAAN dengan EKG pada SATU jam (esp_timer),
 * sehingga posisi R-peak (EKG) dan S1/S2 (audio) dapat dibandingkan dalam milidetik.
 * Jalur audio (pin, I2S, DMA 32x256, 32->16 bit, urutan L,R, baud 921600) TIDAK DISENTUH.
 *
 * YANG BARU dibanding v3
 * ---------------------------------------------------------------------------
 * 1) EKG: esp_timer periodik 500 Hz (tiap 2000 us) membaca ADC1 (rata-rata 4 bacaan,
 *    12 bit) + status LO+/LO-, memberi CAP WAKTU PER SAMPEL (esp_timer, mikrodetik).
 *    Sampel disimpan di ring buffer lalu dikirim di blok audio berikutnya.
 *    Bit 12 = LO+ (elektroda lepas), bit 13 = LO-. Bit 0-11 = nilai ADC (0..4095).
 * 2) KLIK SINKRON: Python mengirim byte 'B' lewat serial -> buzzer di BUZZ_PIN berbunyi
 *    100 ms. Waktu esp_timer saat pin dinaikkan dicatat dan dikirim di header blok.
 *    Bunyinya tertangkap mic -> menera hubungan "waktu audio" <-> "waktu esp_timer"
 *    (verifikasi independen atas estimasi perangkat lunak).
 * 3) FORMAT BLOK v4 (little-endian), header 24 byte:
 *      [0..3]   magic  A5 5A C3 4C  (SENGAJA beda dari v3 ...3C dan v2)
 *      [4]      versi = 4
 *      [5]      flags: bit0 = Serial.write blok SEBELUMNYA terpotong
 *                      bit1 = ring EKG meluap sejak blok sebelumnya (sampel EKG hilang)
 *                      bit2 = ada klik sinkron: field [18..21] berisi waktunya
 *      [6..7]   jumlah int16 audio (L+R terpisah; normal 1024)
 *      [8..11]  nomor blok uint32
 *      [12..15] cap waktu uint32 us (esp_timer, segera setelah i2s_read selesai)
 *      [16..17] jumlah sampel EKG dalam blok (normal ~16)
 *      [18..21] cap waktu klik sinkron uint32 us (0 bila bit2 = 0)
 *      [22..23] CRC-16/CCITT-FALSE atas byte [4..21] + SELURUH payload
 *    Payload: audio int16 (L,R,...) lalu rekaman EKG: {uint32 t_us, uint16 nilai} x n.
 *    Overhead: ~16 rekaman x 6 byte + 24 = ~120 byte per blok (utilisasi serial
 *    ~70% -> ~73,5% pada 921600 baud).
 *
 * WIRING (tambahan; mic TIDAK diubah):
 *   AD8232  GND -> GND | 3.3V -> 3V3 (+0.1uF dekat modul) | OUTPUT -> GPIO4
 *           LO+ -> GPIO5 | LO- -> GPIO6 | SDN -> 3V3
 *   Buzzer aktif 3V: GPIO7 -> 1k -> basis NPN (BC547/2N2222/S8050), emitor GND,
 *           kolektor -> buzzer(-), buzzer(+) -> 3V3. (Buzzer <=15 mA boleh langsung dari GPIO.)
 *   Letakkan buzzer 5-10 cm dari chestpiece dan mic noise (mic noise yang terbuka ke udara
 *   mendengarnya paling jelas).
 *   Mic: SCK->GPIO16, WS->GPIO18, SD (digabung)->GPIO17, organ L/R->GND, noise L/R->3V3.
 *
 * PASANGAN PYTHON: record_from_esp32_v6_2mic_ecg.py. Setelah upload JANGAN buka Serial Monitor.
 *
 * CATATAN YANG JUJUR: pembuatan frame (CRC, urutan byte, rekaman EKG) diuji di komputer dengan
 * mengompilasi LANGSUNG blok di antara penanda BEGIN/END FRAMING. Pembacaan ADC, timer, GPIO,
 * buzzer dan I2S/DMA di board BELUM bisa diuji dari sini: cek "Ringkasan integritas EKG" dan
 * "Verifikasi sinkron" pada rekaman pertama sebelum mempercayai angka apa pun.
 */

#include <driver/i2s.h>
#include <WiFi.h>
#include <esp_bt.h>
#include <esp_timer.h>
#include <string.h>

// ===================== GANTI SESUAI WIRING =====================
#define I2S_WS_PIN    18
#define I2S_SD_PIN    17
#define I2S_SCK_PIN   16
#define ECG_PIN       4      // ADC1_CH3 (JANGAN pakai pin ADC2)
#define ECG_LOP_PIN   5      // AD8232 LO+
#define ECG_LON_PIN   6      // AD8232 LO-
#define BUZZ_PIN      7
// ===============================================================

#define SAMPLE_RATE      16000
#define I2S_PORT         I2S_NUM_0
#define BUF_LEN          1024
#define DMA_BUF_COUNT    32
#define DMA_BUF_LEN      256
#define SERIAL_BAUD      921600
#define DIAG_LED_PIN     2

#define ECG_PERIOD_US    2000      // 500 Hz
#define ECG_OVERSAMPLE   4
#define ECG_RING         512       // pangkat dua; 1,02 s
#define ECG_MAX_PER_BLOCK 64
#define BUZZ_DURATION_US 100000

// ---- BEGIN FRAMING (bagian ini diuji di host; jangan taruh kode Arduino di dalamnya) ----
static const uint8_t SYNC_MAGIC[4] = { 0xA5, 0x5A, 0xC3, 0x4C };
#define FMT_VERSION   4
#define HDR_LEN       24
#define ECG_REC_BYTES 6
#define FLAG_PREV_SHORT_WRITE 0x01
#define FLAG_ECG_OVERFLOW     0x02
#define FLAG_SYNC_EVENT       0x04

static uint16_t crcTable[256];

static void crcInit(void) {
  for (int i = 0; i < 256; i++) {
    uint16_t c = (uint16_t)(i << 8);
    for (int k = 0; k < 8; k++) c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
    crcTable[i] = c;
  }
}

// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, tanpa refleksi/xorout)
static uint16_t crc16(uint16_t crc, const uint8_t *d, size_t n) {
  while (n--) crc = (uint16_t)((crc << 8) ^ crcTable[((crc >> 8) ^ *d++) & 0xFF]);
  return crc;
}

// Susun satu frame ke tx[]. raw = hasil i2s_read (int32 interleaved L,R,...), nInt32 genap.
// ecgT/ecgV = nEcg rekaman EKG (cap waktu us, nilai 16 bit). tEvt = waktu klik sinkron
// (hanya bermakna bila flags memuat FLAG_SYNC_EVENT). Mengembalikan panjang total byte.
static size_t buildFrame(uint8_t *tx, const int32_t *raw, size_t nInt32,
                         uint32_t seq, uint32_t tUs, uint8_t flags,
                         const uint32_t *ecgT, const uint16_t *ecgV, size_t nEcg,
                         uint32_t tEvt) {
  memcpy(tx, SYNC_MAGIC, 4);
  tx[4]  = FMT_VERSION;
  tx[5]  = flags;
  tx[6]  = (uint8_t)(nInt32 & 0xFF);
  tx[7]  = (uint8_t)((nInt32 >> 8) & 0xFF);
  tx[8]  = (uint8_t)(seq & 0xFF);
  tx[9]  = (uint8_t)((seq >> 8) & 0xFF);
  tx[10] = (uint8_t)((seq >> 16) & 0xFF);
  tx[11] = (uint8_t)((seq >> 24) & 0xFF);
  tx[12] = (uint8_t)(tUs & 0xFF);
  tx[13] = (uint8_t)((tUs >> 8) & 0xFF);
  tx[14] = (uint8_t)((tUs >> 16) & 0xFF);
  tx[15] = (uint8_t)((tUs >> 24) & 0xFF);
  tx[16] = (uint8_t)(nEcg & 0xFF);
  tx[17] = (uint8_t)((nEcg >> 8) & 0xFF);
  tx[18] = (uint8_t)(tEvt & 0xFF);
  tx[19] = (uint8_t)((tEvt >> 8) & 0xFF);
  tx[20] = (uint8_t)((tEvt >> 16) & 0xFF);
  tx[21] = (uint8_t)((tEvt >> 24) & 0xFF);
  uint8_t *p = tx + HDR_LEN;
  for (size_t i = 0; i < nInt32; i++) {
    int16_t s = (int16_t)(raw[i] >> 16);          // sama dgn v2/v3: 16 bit teratas
    p[2 * i]     = (uint8_t)((uint16_t)s & 0xFF);
    p[2 * i + 1] = (uint8_t)(((uint16_t)s >> 8) & 0xFF);
  }
  uint8_t *e = p + 2 * nInt32;
  for (size_t i = 0; i < nEcg; i++) {
    uint32_t t = ecgT[i]; uint16_t v = ecgV[i];
    e[6 * i]     = (uint8_t)(t & 0xFF);
    e[6 * i + 1] = (uint8_t)((t >> 8) & 0xFF);
    e[6 * i + 2] = (uint8_t)((t >> 16) & 0xFF);
    e[6 * i + 3] = (uint8_t)((t >> 24) & 0xFF);
    e[6 * i + 4] = (uint8_t)(v & 0xFF);
    e[6 * i + 5] = (uint8_t)((v >> 8) & 0xFF);
  }
  size_t payload = nInt32 * 2 + nEcg * ECG_REC_BYTES;
  uint16_t crc = crc16(0xFFFF, tx + 4, 18);
  crc = crc16(crc, p, payload);
  tx[22] = (uint8_t)(crc & 0xFF);
  tx[23] = (uint8_t)(crc >> 8);
  return HDR_LEN + payload;
}
// ---- END FRAMING ----

int32_t i2sBuffer[BUF_LEN];
uint8_t txBuffer[HDR_LEN + 2 * BUF_LEN + ECG_REC_BYTES * ECG_MAX_PER_BLOCK];
static uint32_t blockSeq = 0;
static uint8_t  nextFlags = 0;

// ---- EKG: ring buffer 1 produsen (callback timer) / 1 konsumen (loop) ----
typedef struct { uint32_t t; uint16_t v; } ecg_rec_t;
static ecg_rec_t ecgRing[ECG_RING];
static volatile uint32_t ecgHead = 0;        // hanya ditulis callback
static volatile uint32_t ecgTail = 0;        // hanya ditulis loop
static volatile uint8_t  ecgOverflow = 0;
static portMUX_TYPE evtMux = portMUX_INITIALIZER_UNLOCKED;
static volatile bool     buzzReq = false;
static bool              buzzOn = false;
static uint32_t          buzzOffAt = 0;
static uint32_t          evtT = 0;
static bool              evtPending = false;

static void ecgTimerCb(void *arg) {
  uint32_t t = (uint32_t)esp_timer_get_time();
  uint32_t acc = 0;
  for (int k = 0; k < ECG_OVERSAMPLE; k++) acc += (uint32_t)analogRead(ECG_PIN);
  uint16_t v = (uint16_t)((acc + ECG_OVERSAMPLE / 2) / ECG_OVERSAMPLE) & 0x0FFF;
  if (digitalRead(ECG_LOP_PIN)) v |= 0x1000;
  if (digitalRead(ECG_LON_PIN)) v |= 0x2000;
  if ((uint32_t)(ecgHead - ecgTail) >= ECG_RING) {
    ecgOverflow = 1;                          // sampel ini dibuang (ring penuh)
  } else {
    ecgRing[ecgHead & (ECG_RING - 1)].t = t;
    ecgRing[ecgHead & (ECG_RING - 1)].v = v;
    ecgHead = ecgHead + 1;
  }
  if (buzzReq && !buzzOn) {                   // klik sinkron
    uint32_t tb = (uint32_t)esp_timer_get_time();
    digitalWrite(BUZZ_PIN, HIGH);
    buzzOn = true; buzzReq = false;
    buzzOffAt = tb + BUZZ_DURATION_US;
    portENTER_CRITICAL(&evtMux); evtT = tb; evtPending = true; portEXIT_CRITICAL(&evtMux);
  } else if (buzzOn && (int32_t)((uint32_t)esp_timer_get_time() - buzzOffAt) >= 0) {
    digitalWrite(BUZZ_PIN, LOW);
    buzzOn = false;
  }
}

static void fatalBlink(void) {          // ~5 Hz selamanya = inisialisasi gagal
  for (;;) { digitalWrite(DIAG_LED_PIN, !digitalRead(DIAG_LED_PIN)); delay(100); }
}

void setup() {
  WiFi.mode(WIFI_OFF);
  btStop();
  esp_bt_controller_disable();

  pinMode(DIAG_LED_PIN, OUTPUT);
  digitalWrite(DIAG_LED_PIN, LOW);
  pinMode(BUZZ_PIN, OUTPUT);
  digitalWrite(BUZZ_PIN, LOW);
  pinMode(ECG_LOP_PIN, INPUT);
  pinMode(ECG_LON_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(ECG_PIN, ADC_11db);

  crcInit();
  Serial.begin(SERIAL_BAUD);
  delay(500);

  i2s_config_t i2s_config = {
    .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
    .sample_rate = SAMPLE_RATE,
    .bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT,
    .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
    .communication_format = I2S_COMM_FORMAT_STAND_I2S,
    .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
    .dma_buf_count = DMA_BUF_COUNT,
    .dma_buf_len = DMA_BUF_LEN,
    .use_apll = false
  };
  i2s_pin_config_t pin_config = {
    .bck_io_num = I2S_SCK_PIN,
    .ws_io_num = I2S_WS_PIN,
    .data_out_num = I2S_PIN_NO_CHANGE,
    .data_in_num = I2S_SD_PIN
  };
  if (i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL) != ESP_OK) fatalBlink();
  if (i2s_set_pin(I2S_PORT, &pin_config) != ESP_OK) fatalBlink();

  esp_timer_create_args_t ta;
  memset(&ta, 0, sizeof(ta));
  ta.callback = &ecgTimerCb;
  ta.name = "ecg";
  esp_timer_handle_t h;
  if (esp_timer_create(&ta, &h) != ESP_OK) fatalBlink();
  if (esp_timer_start_periodic(h, ECG_PERIOD_US) != ESP_OK) fatalBlink();
}

void loop() {
  while (Serial.available()) {                         // perintah dari Python
    int c = Serial.read();
    if (c == 'B') buzzReq = true;
  }

  size_t bytesRead = 0;
  i2s_read(I2S_PORT, i2sBuffer, sizeof(i2sBuffer), &bytesRead, portMAX_DELAY);
  uint32_t tUs = (uint32_t)esp_timer_get_time();       // segera setelah baca selesai

  size_t n = bytesRead / sizeof(int32_t);
  n &= ~(size_t)1;
  if (n == 0) return;

  digitalWrite(DIAG_LED_PIN, !digitalRead(DIAG_LED_PIN));

  uint32_t eT[ECG_MAX_PER_BLOCK]; uint16_t eV[ECG_MAX_PER_BLOCK]; size_t nE = 0;
  uint32_t head = ecgHead;
  while (ecgTail != head && nE < ECG_MAX_PER_BLOCK) {
    uint32_t idx = ecgTail & (ECG_RING - 1);
    eT[nE] = ecgRing[idx].t; eV[nE] = ecgRing[idx].v; nE++;
    ecgTail = ecgTail + 1;
  }
  uint8_t flags = nextFlags;
  if (ecgOverflow) { flags |= FLAG_ECG_OVERFLOW; ecgOverflow = 0; }
  uint32_t tEvt = 0;
  portENTER_CRITICAL(&evtMux);
  if (evtPending) { tEvt = evtT; evtPending = false; flags |= FLAG_SYNC_EVENT; }
  portEXIT_CRITICAL(&evtMux);

  size_t len = buildFrame(txBuffer, i2sBuffer, n, blockSeq, tUs, flags, eT, eV, nE, tEvt);
  size_t w = Serial.write(txBuffer, len);
  nextFlags = (w != len) ? FLAG_PREV_SHORT_WRITE : 0;
  blockSeq++;
}

/*
 * BUDGET BAUD: tiap blok 2048 byte audio + 24 header + ~16 x 6 EKG = ~2168 byte per 32 ms
 *   = ~67.750 byte/s. Baud 921600 (8N1) = 92.160 byte/s -> utilisasi ~73,5%.
 * Bila celah serial meningkat dibanding v3, naikkan SERIAL_BAUD dan --baud Python bersama-sama.
 */
