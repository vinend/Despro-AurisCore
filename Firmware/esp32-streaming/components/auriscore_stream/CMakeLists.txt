idf_component_register(SRCS "auriscore_stream.c" INCLUDE_DIRS "include"
    REQUIRES esp_websocket_client esp_event json mbedtls esp_timer esp_hw_support)
