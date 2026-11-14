/* ESP32-S3 Wi-Fi driver initialization and manual radio-start diagnostic. */
#include <Arduino.h>
#include <esp_wifi.h>
#include <esp_netif.h>
#include <esp_event.h>
#include <nvs_flash.h>
#include <soc/soc.h>
#include <soc/rtc_cntl_reg.h>
#if !CONFIG_IDF_TARGET_ESP32S3
#error "Build for ESP32-S3"
#endif

static bool driverReady = false;
static bool attempted = false;
static bool radioStarted = false;

static bool checked(const char *stage, esp_err_t error) {
  Serial.printf("%s RESULT=%s CODE=0x%x\n", stage, esp_err_to_name(error), (unsigned)error);
  Serial.flush();
  return error == ESP_OK;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("WIFI_INIT_ONLY_V1");
  Serial.printf("BROWNOUT_HW_ENABLE=%u\n",
    (unsigned)((REG_READ(RTC_CNTL_BROWN_OUT_REG) & RTC_CNTL_BROWN_OUT_ENA) != 0));
  if (!checked("NVS_INIT", nvs_flash_init())) return;
  if (!checked("NETIF_INIT", esp_netif_init())) return;
  esp_err_t eventResult = esp_event_loop_create_default();
  if (eventResult != ESP_ERR_INVALID_STATE && !checked("EVENT_LOOP_INIT", eventResult)) return;
  Serial.println("STA_INTERFACE_BEGIN");
  Serial.flush();
  if (!esp_netif_create_default_wifi_sta()) {
    Serial.println("STA_INTERFACE_FAILED");
    return;
  }
  wifi_init_config_t config = WIFI_INIT_CONFIG_DEFAULT();
  Serial.println("WIFI_DRIVER_INIT_BEGIN");
  Serial.flush();
  if (!checked("WIFI_DRIVER_INIT", esp_wifi_init(&config))) return;
  Serial.println("WIFI_SET_MODE_BEGIN");
  Serial.flush();
  if (!checked("WIFI_SET_MODE", esp_wifi_set_mode(WIFI_MODE_STA))) return;
  driverReady = true;
  Serial.println("WIFI_DRIVER_READY_WAITING_FOR_R");
}

void loop() {
  while (Serial.available()) {
    char command = Serial.read();
    if (command == 's' || command == 'S') {
      Serial.printf("WIFI_INIT_ONLY_V1 DRIVER_READY=%d RADIO_STARTED=%d ATTEMPTED=%d UPTIME_MS=%lu\n",
        driverReady, radioStarted, attempted, (unsigned long)millis());
    }
    if (command == 'r' || command == 'R') {
      if (driverReady && !attempted) {
        attempted = true;
        Serial.println("WIFI_RADIO_START_BEGIN");
        Serial.flush();
        radioStarted = checked("WIFI_RADIO_START", esp_wifi_start());
      } else {
        Serial.println("WIFI_RADIO_REQUEST_REJECTED");
      }
    }
  }
  delay(20);
}
