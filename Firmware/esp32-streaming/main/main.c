/* Wi-Fi access-point transport example. No invented pins or synthetic microphone. */
#include <string.h>
#include "nvs_flash.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "auriscore_stream.h"

void app_main(void) {
    if (strlen(CONFIG_AURISCORE_AP_PASSWORD) < 8 || strlen(CONFIG_AURISCORE_AP_PASSWORD) > 63
        || !strlen(CONFIG_AURISCORE_AP_SSID) || strlen(CONFIG_AURISCORE_AP_SSID) > 32 || strlen(CONFIG_AURISCORE_PAIRING_TOKEN) < 16
        || !strlen(CONFIG_AURISCORE_GATEWAY_URI)) {
        ESP_LOGE("auriscore", "Configure Wi-Fi password, gateway URI and pairing token in menuconfig");
        return;
    }
    esp_err_t status = nvs_flash_init();
    if (status == ESP_ERR_NVS_NO_FREE_PAGES || status == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase()); status = nvs_flash_init();
    }
    ESP_ERROR_CHECK(status);
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_ap();
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    wifi_config_t config = { .ap = { .max_connection = 4, .authmode = WIFI_AUTH_WPA2_PSK } };
    strlcpy((char *)config.ap.ssid, CONFIG_AURISCORE_AP_SSID, sizeof(config.ap.ssid));
    strlcpy((char *)config.ap.password, CONFIG_AURISCORE_AP_PASSWORD, sizeof(config.ap.password));
    config.ap.ssid_len = strlen(CONFIG_AURISCORE_AP_SSID);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
    const auriscore_stream_config_t stream = { .uri = CONFIG_AURISCORE_GATEWAY_URI,
        .token = CONFIG_AURISCORE_PAIRING_TOKEN, .device = CONFIG_AURISCORE_DEVICE_ID, .firmware = "0.1.0-network" };
    ESP_ERROR_CHECK(auriscore_stream_start(&stream));
    ESP_LOGW("auriscore", "Network initialized. Audio acquisition is NOT installed; connect real PCM producer to auriscore_stream_push.");
    /* Future acquisition task: when auriscore_stream_enabled() is true, pass each
       real 400-sample mono PCM16 block at 8 kHz to auriscore_stream_push().
       This example never synthesizes sound or reports capture success. */
}
