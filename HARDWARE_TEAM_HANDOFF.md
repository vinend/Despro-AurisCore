# Hardware team handoff for actual stethoscope streaming

## Current device preparation — 2026-11-16

Use the main AurisCore website, not `/device-link-test`, for actual organ work.
From the repository root, `powershell -NoProfile -ExecutionPolicy Bypass -File
scripts/start_auriscore.ps1` reuses healthy local services or starts them, detects
the current LAN address, and displays the main URL and local pairing code.
The laptop remains the local gateway/analysis server and must stay reachable.

New S3: ESP32-S3 N16R8, USB-UART COM7 in this session. Capture firmware keeps
16 kHz dual-slot I2S on BCLK16 / WS18 / DATA17 and publishes organ-slot mono 8 kHz.
Power off before connecting the microphone wiring. The expected organ slot is
left and noise slot is right; verify the physical L/R straps with the hardware
team. Sensor presence cannot be proved from I2S driver initialization alone.
ANC and ECG forwarding are not implemented by this Wi-Fi path.

For saved networks the device reconnects automatically. For a new router/hotspot,
hold BOOT for 3 seconds AFTER normal boot, join its AurisCore-Setup Wi-Fi using
the per-device setup key, and open http://192.168.4.1/setup. Save the network once;
the device retains older profiles and reboots into the new priority profile.
Return the phone to the chosen network and reopen the main AurisCore website.
The main connection form includes these instructions. Do not hold BOOT during
power-on, which selects the ROM upload mode. Setup credentials remain private.

On the main website, pair once per browser session; waveform follows received PCM.
Choose the actual organ, then use recording or Prediksi langsung. Context windows
remain Heart 10 s, Lung 30 s, Abdomen 5 s. No signal does not mean normal findings.
GPIOs, microphone supply, real sound, continuity and loading with the attached
microphones must still be checked on the assembled device. Development model
results are not clinical validation or Murmur onset/offset ground truth.

## Current handoff — 2026-11-14

`codex/hardware-esp32` contains capture firmware, provisioning, serial bridge and
radio diagnostics. `codex/device-integration` contains the companion WebApp,
gateway, engineering inference and hosting starter. Both branches start from
`origin/master` commit `03da32a`; review both when assembling the full prototype.
Neither branch is a deployment acceptance or a model promotion.

The S3 is ESP32-S3-WROOM-1 N16R8, with two INMP441 slots on BCLK16/WS18/DATA17.
The supplied serial-v4 capture firmware is preserved. The Wi-Fi prototype forwards
the organ slot only; it does not implement ANC or ECG forwarding. External RGB
wiring remains unconfirmed, so physical RGB output defaults to disabled.

Latest isolated observation: driver initialization and station-mode setup return
ESP_OK; manual `R` reaches `esp_wifi_start` and resets with a brownout message.
Wi-Fi/BLE radio operation remains blocked; the reset cause is not fully isolated.
Brownout-off bench variants also reset and do not establish electrical stability.
Do not treat successful compilation, a gateway heartbeat or supplied current
capacity as proof of working device audio.

For Python hardware tools, install into the chosen local environment with
`python -m pip install -e "./AI-Pipeline[hardware]"` from the repository root.
This adds pyserial and websocket-client; a Python runtime is not included in Git.
Install WebApp/gateway dependencies with their existing npm lockfiles separately.
`monitor_auriscore.ps1` targets AurisCore capture firmware; the init-only diagnostic
uses serial 115200 and single-character `R`/`S`, rather than capture commands.
Build scripts compile only and never upload automatically. Keep credentials,
logs, flash backups, caches and private model assets outside tracked files.

The questionnaire below is retained for other boards and unresolved peripherals;
its original statement that no capture firmware exists is historical.

Pins are required for acquisition firmware, not for the Wi-Fi/WebSocket module.

| Item | Required details |
| --- | --- |
| ESP32-S3 board | Exact board/module, flash/PSRAM, schematic, flashing/USB connection |
| Audio sensor | Part number/datasheet, chestpiece coupling and microphone/contact sensor |
| Analog front end | Amplifier/filter/ADC/codec parts, schematic, supply, gain, DC bias and safe input range |
| ADC wiring | GPIO, ADC unit/channel, reference/full-scale/attenuation and resolution |
| Digital audio wiring | I2S BCLK, WS/LRCLK, DIN, MCLK if used; PDM clock/data if applicable |
| Codec control | I2C SDA/SCL, device address, reset/enable, power sequencing |
| Other pins | Battery sense, buttons, LEDs and any shared/reserved pins |
| Audio format | Input word width/alignment/signedness, channel selection, supported sample rates; continuous 8 kHz capability or required resampling |
| Wi-Fi | AP versus router/STA, SSID/password provisioning, IP assignment and laptop endpoint configuration |
| Bring-up data | Short real chestpiece capture with format, known-tone capture, expected levels and known noise/clipping |
| Physical testing | Board/sensor access, power requirements, firmware build/flash support and bench test contact |

First priority: exact board, sensor/ADC datasheets and wiring diagram. There is
currently no capture firmware; these enable the acquisition driver. Do not send
Wi-Fi passwords or pairing secrets through tracked repository files.

For the current Windows laptop bring-up and hardware questionnaire, see
[HARDWARE_BRINGUP_2026-11-14.md](HARDWARE_BRINGUP_2026-11-14.md).
