#include "auriscore_stream.h"
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_websocket_client.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_crt_bundle.h"
#include "cJSON.h"

typedef struct { uint8_t bytes[832]; int64_t queued_us; } audio_block_t;
static QueueHandle_t audio_queue;
static esp_websocket_client_handle_t client;
static auriscore_stream_config_t settings;
static portMUX_TYPE guard = portMUX_INITIALIZER_UNLOCKED;
static bool connected, enabled, overflow;
static uint32_t stream_id, sequence;
static uint64_t sample_index;
static char incoming[2049];
static void put16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = v >> (8 * i); }
static void text(cJSON *json) {
    char *payload = cJSON_PrintUnformatted(json);
    if (payload) { esp_websocket_client_send_text(client, payload, strlen(payload), pdMS_TO_TICKS(250)); free(payload); }
    cJSON_Delete(json);
}
static cJSON *message(const char *type) { cJSON *json = cJSON_CreateObject(); cJSON_AddStringToObject(json, "type", type); return json; }
static void hello(void) {
    cJSON *json = message("device_hello"); cJSON_AddNumberToObject(json, "protocol", 2);
    cJSON_AddStringToObject(json, "device", settings.device); cJSON_AddStringToObject(json, "fw", settings.firmware);
    cJSON_AddStringToObject(json, "source", "hardware"); cJSON_AddNumberToObject(json, "streamId", stream_id);
    cJSON_AddNumberToObject(json, "samplingRate", 8000); cJSON_AddNumberToObject(json, "channels", 1);
    cJSON_AddStringToObject(json, "encoding", "pcm16le"); text(json);
}
static void handle_message(const char *data) {
    cJSON *json = cJSON_Parse(data); if (!json) return;
    const cJSON *type = cJSON_GetObjectItemCaseSensitive(json, "type");
    if (cJSON_IsString(type) && strcmp(type->valuestring, "authenticated") == 0) hello();
    else if (cJSON_IsString(type) && strcmp(type->valuestring, "command") == 0) {
        cJSON *command = cJSON_GetObjectItemCaseSensitive(json, "command"), *id = cJSON_GetObjectItemCaseSensitive(json, "id");
        if (cJSON_IsString(command) && cJSON_IsString(id) && strlen(id->valuestring) <= 64) {
            bool start = strcmp(command->valuestring, "start_stream") == 0;
            bool stop = strcmp(command->valuestring, "stop_stream") == 0;
            portENTER_CRITICAL(&guard); enabled = false; portEXIT_CRITICAL(&guard);
            xQueueReset(audio_queue);
            cJSON *ack = message("command_ack"); cJSON_AddStringToObject(ack, "id", id->valuestring);
            cJSON_AddStringToObject(ack, "command", command->valuestring); cJSON_AddBoolToObject(ack, "ok", start || stop); text(ack);
            portENTER_CRITICAL(&guard);
            if (start) { sequence = 0; sample_index = 0; overflow = false; enabled = true; }
            portEXIT_CRITICAL(&guard);
        }
    }
    cJSON_Delete(json);
}
static void websocket_event(void *arg, esp_event_base_t base, int32_t event, void *event_data) {
    (void)arg; (void)base;
    if (event == WEBSOCKET_EVENT_CONNECTED) {
        portENTER_CRITICAL(&guard); connected = true; enabled = false; overflow = false;
        stream_id = esp_random(); if (!stream_id) stream_id = 1; portEXIT_CRITICAL(&guard);
        xQueueReset(audio_queue);
        cJSON *auth = message("authenticate"); cJSON_AddStringToObject(auth, "token", settings.token); text(auth);
    } else if (event == WEBSOCKET_EVENT_DISCONNECTED || event == WEBSOCKET_EVENT_ERROR) {
        portENTER_CRITICAL(&guard); connected = false; enabled = false; portEXIT_CRITICAL(&guard); xQueueReset(audio_queue);
    } else if (event == WEBSOCKET_EVENT_DATA) {
        esp_websocket_event_data_t *data = event_data;
        if ((data->op_code != 1 && data->op_code != 0) || data->payload_len > 2048 || data->payload_offset < 0
            || data->data_len < 0 || data->payload_offset + data->data_len > data->payload_len) return;
        if (data->payload_offset == 0) memset(incoming, 0, sizeof(incoming));
        memcpy(incoming + data->payload_offset, data->data_ptr, data->data_len);
        if (data->payload_offset + data->data_len == data->payload_len) handle_message(incoming);
    }
}
bool auriscore_stream_enabled(void) {
    portENTER_CRITICAL(&guard); bool value = connected && enabled && !overflow; portEXIT_CRITICAL(&guard); return value;
}
esp_err_t auriscore_stream_push(const int16_t samples[400]) {
    if (!samples || !audio_queue) return ESP_ERR_INVALID_ARG;
    audio_block_t block = { .queued_us = esp_timer_get_time() };
    portENTER_CRITICAL(&guard);
    if (!connected || !enabled || overflow) { portEXIT_CRITICAL(&guard); return ESP_ERR_INVALID_STATE; }
    uint32_t seq = sequence++; uint64_t first = sample_index; sample_index += 400; uint32_t sid = stream_id;
    portEXIT_CRITICAL(&guard);
    memcpy(block.bytes, "AURI", 4); block.bytes[4] = 2; put16(block.bytes + 6, 32);
    put32(block.bytes + 8, sid); put32(block.bytes + 12, seq); put32(block.bytes + 16, first); put32(block.bytes + 20, first >> 32);
    put32(block.bytes + 24, 8000); put16(block.bytes + 28, 400); block.bytes[30] = 1; block.bytes[31] = 1;
    for (int i = 0; i < 400; i++) put16(block.bytes + 32 + 2 * i, (uint16_t)samples[i]);
    if (xQueueSend(audio_queue, &block, 0) != pdTRUE) {
        portENTER_CRITICAL(&guard); overflow = true; portEXIT_CRITICAL(&guard); return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
static void sender(void *arg) {
    (void)arg; audio_block_t block;
    for (;;) {
        bool full;
        portENTER_CRITICAL(&guard); full = overflow && connected; if (full) { enabled = false; overflow = false; } portEXIT_CRITICAL(&guard);
        if (full) { text(message("source_error")); xQueueReset(audio_queue); }
        if (xQueueReceive(audio_queue, &block, pdMS_TO_TICKS(100)) == pdTRUE && auriscore_stream_enabled()) {
            if (esp_timer_get_time() - block.queued_us > 250000
                || esp_websocket_client_send_bin(client, (const char *)block.bytes, sizeof(block.bytes), pdMS_TO_TICKS(100)) != sizeof(block.bytes)) {
                portENTER_CRITICAL(&guard); enabled = false; portEXIT_CRITICAL(&guard);
                text(message("source_error")); xQueueReset(audio_queue);
            }
        }
    }
}
esp_err_t auriscore_stream_start(const auriscore_stream_config_t *config) {
    if (client) return ESP_ERR_INVALID_STATE;
    if (!config || !config->uri || !config->token || strlen(config->token) < 16 || !config->device || !config->firmware) return ESP_ERR_INVALID_ARG;
    settings = *config; audio_queue = xQueueCreate(8, sizeof(audio_block_t)); if (!audio_queue) return ESP_ERR_NO_MEM;
    const esp_websocket_client_config_t transport = { .uri = config->uri, .reconnect_timeout_ms = 3000,
        .network_timeout_ms = 1000, .buffer_size = 2048, .crt_bundle_attach = esp_crt_bundle_attach };
    client = esp_websocket_client_init(&transport); if (!client) { vQueueDelete(audio_queue); audio_queue = NULL; return ESP_ERR_NO_MEM; }
    ESP_ERROR_CHECK(esp_websocket_register_events(client, WEBSOCKET_EVENT_ANY, websocket_event, NULL));
    if (xTaskCreate(sender, "auriscore_tx", 4096, NULL, 5, NULL) != pdPASS) return ESP_ERR_NO_MEM;
    return esp_websocket_client_start(client);
}
