# Hardware team handoff for actual stethoscope streaming

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
