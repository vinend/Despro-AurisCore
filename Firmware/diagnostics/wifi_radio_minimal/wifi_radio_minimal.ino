/* Standalone ESP32-S3 bench radio test. No sensors, audio, gateway or credentials. */
#include <Arduino.h>
#include <WiFi.h>
#include <esp_system.h>
#include <esp_private/brownout.h>

static bool attempted = false;
static uint32_t bootAt = 0;

static void testRadio() {
  attempted = true;
  Serial.println("WIFI_INIT_BEGIN");
  Serial.flush();
  if (!WiFi.mode(WIFI_STA)) {
    Serial.println("WIFI_MODE_FAILED");
    return;
  }
  Serial.println("WIFI_MODE_READY");
  const bool powerOk = WiFi.setTxPower(WIFI_POWER_8_5dBm);
  Serial.println(powerOk ? "RUNTIME_TX_LIMIT_ACCEPTED" : "RUNTIME_TX_LIMIT_FAILED");
  // PHY startup table caps all rates at 10 dBm. Passive scan only receives.
  Serial.println("PASSIVE_SCAN_BEGIN");
  Serial.flush();
  const int count = WiFi.scanNetworks(false, false, true, 120);
  if (count >= 0) {
    Serial.printf("PASSIVE_SCAN_PASS NETWORK_COUNT=%d\n", count);
  } else {
    Serial.printf("PASSIVE_SCAN_FAILED CODE=%d\n", count);
  }
  WiFi.scanDelete();
  WiFi.mode(WIFI_OFF);
  Serial.println("RADIO_OFF_TEST_FINISHED");
}

void setup() {
  esp_brownout_disable();
  setCpuFrequencyMhz(80);
  Serial.begin(115200);
  delay(300);
  Serial.println("STANDALONE_WIFI_RADIO_TEST_V1");
  Serial.println("BROWNOUT_DETECTOR_DISABLED");
  Serial.println("STARTUP_PHY_CAP_DBM=10");
  Serial.printf("CPU_MHZ=%u RESET_REASON=%d\n", getCpuFrequencyMhz(), (int)esp_reset_reason());
  Serial.println("AUTO_TEST_IN_5S; R=RETRY; S=STATUS");
  Serial.flush();
  bootAt = millis();
}

void loop() {
  while (Serial.available()) {
    char command = Serial.read();
    if (command == 'r' || command == 'R') {
      testRadio();
    } else if (command == 's' || command == 'S') {
      Serial.printf("STANDALONE_WIFI_RADIO_TEST_V1 ATTEMPTED=%d\n", attempted);
    }
  }
  if (!attempted && (uint32_t)(millis() - bootAt) >= 5000) testRadio();
  delay(20);
}
