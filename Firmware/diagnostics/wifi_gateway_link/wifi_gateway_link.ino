/* No-microphone Wi-Fi/gateway bench test. No audio, sensor GPIO or inference.
 * Uses gateway v2 engineering identity; never claims physical audio readiness.
 * Provision over USB JSON; no credentials are compiled or printed.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <cJSON.h>
#include <esp_system.h>
#include <soc/soc.h>
#include <soc/rtc_cntl_reg.h>
#if !CONFIG_IDF_TARGET_ESP32S3
#error "This bench test targets ESP32-S3"
#endif

static Preferences prefs;
static WebSocketsClient ws;
static String ssid, password, host, token, serialInput;
static bool attempted=false, networkStarted=false, authenticated=false, radioHeld=false;
static uint32_t attemptAt=0, heartbeatAt=0, streamId=1;

static void sendJson(cJSON *value) {
  char *packed=cJSON_PrintUnformatted(value);
  if(packed) { ws.sendTXT(packed); free(packed); }
  cJSON_Delete(value);
}

static void gatewayEvent(WStype_t type, uint8_t *payload, size_t length) {
  if(type==WStype_DISCONNECTED) { authenticated=false; Serial.println("GATEWAY_DISCONNECTED"); return; }
  if(type==WStype_CONNECTED) {
    Serial.println("GATEWAY_SOCKET_CONNECTED");
    cJSON *auth=cJSON_CreateObject();
    cJSON_AddStringToObject(auth,"type","authenticate");
    cJSON_AddStringToObject(auth,"token",token.c_str()); sendJson(auth); return;
  }
  if(type!=WStype_TEXT || length>2048) return;
  cJSON *message=cJSON_ParseWithLength((const char*)payload,length);
  if(!message) return;
  const cJSON *kind=cJSON_GetObjectItemCaseSensitive(message,"type");
  const cJSON *role=cJSON_GetObjectItemCaseSensitive(message,"role");
  if(cJSON_IsString(kind) && strcmp(kind->valuestring,"authenticated")==0 &&
     cJSON_IsString(role) && strcmp(role->valuestring,"device")==0) {
    authenticated=true;
    cJSON *hello=cJSON_CreateObject();
    cJSON_AddStringToObject(hello,"type","device_hello"); cJSON_AddNumberToObject(hello,"protocol",2);
    cJSON_AddStringToObject(hello,"device","ESP32S3-NO-MIC-LINK-TEST");
    cJSON_AddStringToObject(hello,"fw","wifi-link-test-1");
    cJSON_AddStringToObject(hello,"source","engineering");
    cJSON_AddNumberToObject(hello,"streamId",streamId);
    // Required v2 envelope metadata only: this sketch emits NO audio frames.
    cJSON_AddNumberToObject(hello,"samplingRate",8000); cJSON_AddNumberToObject(hello,"channels",1);
    cJSON_AddStringToObject(hello,"encoding","pcm16le"); sendJson(hello);
    Serial.println("GATEWAY_AUTHENTICATED_NO_AUDIO");
  } else if(cJSON_IsString(kind) && strcmp(kind->valuestring,"command")==0) {
    const cJSON *id=cJSON_GetObjectItemCaseSensitive(message,"id");
    const cJSON *command=cJSON_GetObjectItemCaseSensitive(message,"command");
    if(cJSON_IsString(id) && strlen(id->valuestring)<=64 && cJSON_IsString(command)) {
      cJSON *ack=cJSON_CreateObject(); cJSON_AddStringToObject(ack,"type","command_ack");
      cJSON_AddStringToObject(ack,"id",id->valuestring);
      cJSON_AddStringToObject(ack,"command",command->valuestring);
      cJSON_AddBoolToObject(ack,"ok",strcmp(command->valuestring,"stop_stream")==0);
      sendJson(ack); Serial.println("AUDIO_UNAVAILABLE_NO_MIC_TEST");
    }
  }
  cJSON_Delete(message);
}

static bool configured() { return ssid.length()>0 && host.length()>0 && token.length()>=16; }
static void status() {
  Serial.println("AURISCORE_WIFI_LINK_TEST_V1");
  Serial.printf("LINK_STATUS CONFIGURED=%d WIFI=%d GATEWAY=%d NO_MIC=1 UPTIME_MS=%lu RSSI=%d\n",
    configured(),WiFi.status()==WL_CONNECTED,authenticated,(unsigned long)millis(),
    WiFi.status()==WL_CONNECTED?WiFi.RSSI():0);
}
static void startWifi() {
  if(!configured() || attempted) return;
  attempted=true; attemptAt=millis();
  Serial.println("WIFI_INIT_BEGIN"); Serial.flush();
  if(!WiFi.mode(WIFI_STA)) { Serial.println("WIFI_MODE_FAILED"); return; }
  Serial.println("WIFI_MODE_READY");
  WiFi.setAutoReconnect(false);
  WiFi.begin(ssid.c_str(),password.c_str()); Serial.println("WIFI_CONNECTING");
}

static void configure(const String &line) {
  cJSON *j=cJSON_Parse(line.c_str());
  const cJSON *s=cJSON_GetObjectItemCaseSensitive(j,"ssid");
  const cJSON *p=cJSON_GetObjectItemCaseSensitive(j,"password");
  const cJSON *h=cJSON_GetObjectItemCaseSensitive(j,"host");
  const cJSON *t=cJSON_GetObjectItemCaseSensitive(j,"token");
  bool valid=cJSON_IsString(s)&&strlen(s->valuestring)>0&&strlen(s->valuestring)<=32&&
    cJSON_IsString(p)&&strlen(p->valuestring)<=63&&cJSON_IsString(h)&&strlen(h->valuestring)>0&&
    strlen(h->valuestring)<=253&&!strpbrk(h->valuestring,"/:?@# \t\r\n")&&
    cJSON_IsString(t)&&strlen(t->valuestring)>=16&&strlen(t->valuestring)<=128;
  if(valid) {
    ssid=s->valuestring; password=p->valuestring; host=h->valuestring; token=t->valuestring;
    String packed=line;
    bool saved=prefs.putString("config",packed)>0 && prefs.getString("config","")==packed;
    cJSON_Delete(j);
    if(saved) { Serial.println("CONFIG_SAVED_REBOOTING"); Serial.flush(); delay(100); ESP.restart(); }
    else Serial.println("CONFIG_SAVE_FAILED");
  } else { cJSON_Delete(j); Serial.println("CONFIG_REJECTED"); }
}

void setup() {
  Serial.begin(115200); delay(300);
  Serial.println("AURISCORE_WIFI_LINK_TEST_V1");
  Serial.printf("BROWNOUT_HW_ENABLE=%u RESET_REASON=%d NO_MIC=1\n",
    (unsigned)((REG_READ(RTC_CNTL_BROWN_OUT_REG)&RTC_CNTL_BROWN_OUT_ENA)!=0),(int)esp_reset_reason());
  radioHeld=esp_reset_reason()==ESP_RST_BROWNOUT;
  if(radioHeld) Serial.println("RADIO_HELD_AFTER_BROWNOUT_RETRY_MANUALLY");
  prefs.begin("auris-linktest",false);
  cJSON *j=cJSON_Parse(prefs.getString("config","").c_str());
  const cJSON *s=cJSON_GetObjectItemCaseSensitive(j,"ssid"), *p=cJSON_GetObjectItemCaseSensitive(j,"password");
  const cJSON *h=cJSON_GetObjectItemCaseSensitive(j,"host"), *t=cJSON_GetObjectItemCaseSensitive(j,"token");
  if(cJSON_IsString(s)&&cJSON_IsString(p)&&cJSON_IsString(h)&&cJSON_IsString(t)) {
    ssid=s->valuestring; password=p->valuestring; host=h->valuestring; token=t->valuestring;
  }
  cJSON_Delete(j); streamId=esp_random(); if(!streamId)streamId=1;
  Serial.println(configured()?"CONFIG_PRESENT":"CONFIG_REQUIRED");
  Serial.println("NO_MIC_NO_AUDIO_NO_INFERENCE");
}

void loop() {
  while(Serial.available()) {
    char c=Serial.read();
    if(c=='\n') {
      serialInput.trim();
      if(serialInput=="STATUS"||serialInput=="s"||serialInput=="S") status();
      else if(serialInput=="RETRY"||serialInput=="r"||serialInput=="R") {
        if(WiFi.status()==WL_CONNECTED) status();
        else { radioHeld=false; attempted=false; startWifi(); }
      } else if(serialInput.startsWith("{")) configure(serialInput);
      serialInput="";
    } else if(serialInput.length()<768) serialInput+=c;
    else { serialInput=""; Serial.println("CONFIG_LINE_TOO_LONG"); }
  }
  if(!radioHeld && !attempted && configured() && millis()>5000) startWifi();
  if(WiFi.status()==WL_CONNECTED) {
    if(!networkStarted) {
      Serial.print("WIFI_CONNECTED IP="); Serial.println(WiFi.localIP());
      ws.onEvent(gatewayEvent); ws.setReconnectInterval(3000);
      ws.begin(host,8082,"/device",""); networkStarted=true;
    }
    ws.loop();
    if(authenticated && millis()-heartbeatAt>2000) {
      heartbeatAt=millis(); ws.sendTXT("{\"type\":\"heartbeat\"}");
    }
  } else {
    if(networkStarted) { ws.disconnect(); networkStarted=false; authenticated=false; Serial.println("WIFI_LOST_RETRY_MANUALLY"); }
    if(attempted && attemptAt && millis()-attemptAt>30000) {
      attemptAt=0; WiFi.disconnect(true,false); Serial.println("WIFI_CONNECT_TIMEOUT_RETRY_MANUALLY");
    }
  }
  delay(2);
}
