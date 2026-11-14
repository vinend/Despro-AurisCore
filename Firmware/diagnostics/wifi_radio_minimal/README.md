# Standalone ESP32-S3 radio bench test

This sketch isolates radio startup from microphone capture and gateway code.
It disables the brownout detector at setup, uses CPU 80 MHz, caps the SDK 5.5.5
PHY startup power table at 10 dBm, requests an 8.5 dBm runtime TX limit after
startup and performs a passive scan five seconds after
boot. A successful scan turns the radio off. R repeats one scan, S prints status.
No network names, passwords or saved profile values are printed or modified.

The table definition comes from the pinned Espressif ESP-IDF source recorded in
phy_init_10dbm.c. It overrides the default data object at link time. Verify the
packaged table and link map before flashing. The external RF output and electrical
current require separate measurements.

Compile using Espressif Arduino 3.3.12 and FQBN
esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=default,CPUFreq=80.
Serial output uses the CH343 USB-UART connector at 115200 baud. Website controls
are unavailable while this standalone sketch is installed.

The user's previous combined AurisCore image and source snapshot are retained
locally in .runtime/hardware/saved-auriscore-before-radio-minimal/. Its restore.py
checks the image SHA256 and original board MAC before flashing the app partition.
Historical models and saved Wi-Fi credentials are outside this sketch's writes.
