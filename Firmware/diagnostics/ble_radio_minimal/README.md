# ESP32-S3 BLE radio bench test

Build with Espressif Arduino core 3.3.12, FQBN
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=default.

The sketch disables brownout at setup as explicitly requested by the user.
It uses the default CPU clock and SDK PHY table. It starts BLE after five seconds,
then requests -12 dBm transmit power and advertises AurisCore-BLE-Test with a
500-1000 ms advertising interval. The low power request applies after successful
BLE initialization. It does not prove the radio startup surge is reduced.

Service UUID dce83010-8196-4ef1-ae1b-13b634324624.
TX UUID dce83011-8196-4ef1-ae1b-13b634324624 supports read/notify.
RX UUID dce83012-8196-4ef1-ae1b-13b634324624 supports write.
Write ASCII PING to RX to receive ASCII PONG on TX. Synthetic BEAT counters
are emitted once per second while connected. They are connection-test data.
There is no audio acquisition, physiological measurement, inference or website
audio publishing in this sketch. The bench characteristics contain public
synthetic data and have no authentication requirement.

Serial USB-UART is 115200 baud. S returns readiness and connection state.
The server advertises again after a client disconnects. Saved Wi-Fi profiles
are never accessed. Prior AurisCore source/ELF/image/restore script remain in
.runtime/hardware/saved-auriscore-before-radio-minimal/.
