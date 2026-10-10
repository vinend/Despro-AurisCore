#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"
typedef struct { const char *uri; const char *token; const char *device; const char *firmware; } auriscore_stream_config_t;
/* One instance. Config string storage must remain valid for the device lifetime. */
esp_err_t auriscore_stream_start(const auriscore_stream_config_t *config);
bool auriscore_stream_enabled(void);
/* Call from capture task (not ISR), only with real 400-sample PCM16 mono @ 8 kHz.
   Zero-wait enqueue; overflow is reported to the gateway and invalidates stream. */
esp_err_t auriscore_stream_push(const int16_t samples[400]);
