# Hardware team handoff for actual stethoscope streaming

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
