/* Local Wi-Fi engineering capture. Original USB-v4 sketch remains unchanged.
 * INMP441 stereo wiring: BCLK16 WS18 SD17; organ slot0, noise slot1.
 * Publishes ONLY organ PCM16 8kHz v2. No ANC, ECG forwarding or diagnosis.
 * Provision credentials over USB once; USB never carries audio in this sketch.
 */
#include <Arduino.h>
#include <WiFi.h>
#include <Preferences.h>
#include <WebSocketsClient.h>
#include <driver/i2s.h>
#include <esp_timer.h>
#include <esp_system.h>
#include <soc/soc.h>
#include <soc/rtc_cntl_reg.h>
#ifndef AURISCORE_DISABLE_BROWNOUT
#define AURISCORE_DISABLE_BROWNOUT 0
#endif
#if AURISCORE_DISABLE_BROWNOUT
#include <esp_private/brownout.h>
#endif
#include <cJSON.h>
#include "audio_codec.h"
#include "status_led.h"
static StatusLed statusLed;

struct AudioBlock { int16_t samples[400]; int64_t queued; uint32_t generation; };
static Preferences prefs;
static WebSocketsClient ws;
static QueueHandle_t blocks;
static QueueHandle_t i2sEvents;
static portMUX_TYPE guard = portMUX_INITIALIZER_UNLOCKED;
static bool enabled=false, failed=false;
static uint32_t generation=0, streamId=1, sequence=0;
static uint64_t sampleIndex=0;
static String ssid, password, host, token, input;
struct NetworkProfile { String ssid, password, host, kind; };
static NetworkProfile profiles[4];
static unsigned profileCount=0, activeProfile=0;
static uint32_t attemptAt=0, bootAt=0;
static bool radioStarted=false, radioHold=false, wasAssociated=false;
static uint16_t gatewayPort=8082;
static bool configured=false, networkStarted=false;
static bool captureReady=false;
static unsigned fallbackProfile(unsigned current,unsigned count) { return count?(current+1)%count:0; }
static bool attemptExpired(uint32_t now,uint32_t started) { return (uint32_t)(now-started)>=15000; }

static void haltCapture() {
  portENTER_CRITICAL(&guard); enabled=false; generation++; portEXIT_CRITICAL(&guard);
  xQueueReset(blocks);
}
static void sendJson(cJSON *json) {
  char *value=cJSON_PrintUnformatted(json);
  if(value) { ws.sendTXT(value); free(value); }
  cJSON_Delete(json);
}
static void networkEvent(WStype_t type, uint8_t *payload, size_t length) {
  if(type==WStype_DISCONNECTED) { statusLed.disconnect(); haltCapture(); Serial.println("GATEWAY_DISCONNECTED"); return; }
  if(type==WStype_CONNECTED) {
    haltCapture(); streamId=esp_random(); if(!streamId)streamId=1;
    cJSON *j=cJSON_CreateObject(); cJSON_AddStringToObject(j,"type","authenticate");
    cJSON_AddStringToObject(j,"token",token.c_str()); sendJson(j); return;
  }
  if(type!=WStype_TEXT || length>2048) return;
  cJSON *j=cJSON_ParseWithLength((const char*)payload,length);
  if(!j) { ws.disconnect(); return; }
  const cJSON *t=cJSON_GetObjectItemCaseSensitive(j,"type");
  if(cJSON_IsString(t) && !strcmp(t->valuestring,"authenticated")) {
    cJSON *h=cJSON_CreateObject(); cJSON_AddStringToObject(h,"type","device_hello");
    cJSON_AddNumberToObject(h,"protocol",2); cJSON_AddStringToObject(h,"device","ESP32S3-INMP441-WIFI");
    cJSON_AddStringToObject(h,"fw","wifi-capture-0.2.0"); cJSON_AddStringToObject(h,"source","hardware");
    cJSON_AddNumberToObject(h,"streamId",streamId); cJSON_AddNumberToObject(h,"samplingRate",8000);
    cJSON_AddNumberToObject(h,"indicatorProtocol",1);
    cJSON_AddNumberToObject(h,"channels",1); cJSON_AddStringToObject(h,"encoding","pcm16le"); sendJson(h);
    Serial.println("GATEWAY_AUTHENTICATED");
  } else if(cJSON_IsString(t) && !strcmp(t->valuestring,"indicator")) {
    const cJSON *m=cJSON_GetObjectItemCaseSensitive(j,"mode"), *p=cJSON_GetObjectItemCaseSensitive(j,"phase");
    if(cJSON_IsString(m) && cJSON_IsString(p)) {
      int mode=!strcmp(m->valuestring,"heart")?1:!strcmp(m->valuestring,"lung")?2:!strcmp(m->valuestring,"abdomen")?3:0;
      int phase=!strcmp(p->valuestring,"recording")?1:!strcmp(p->valuestring,"processing")?2:!strcmp(p->valuestring,"done")?3:0;
      if(mode) statusLed.update(mode,phase,millis());
    }
  } else if(cJSON_IsString(t) && !strcmp(t->valuestring,"command")) {
    const cJSON *cmd=cJSON_GetObjectItemCaseSensitive(j,"command"), *id=cJSON_GetObjectItemCaseSensitive(j,"id");
    if(cJSON_IsString(cmd) && cJSON_IsString(id) && strlen(id->valuestring)<=64) {
      bool start=!strcmp(cmd->valuestring,"start_stream"), stop=!strcmp(cmd->valuestring,"stop_stream");
      haltCapture();
      cJSON *ack=cJSON_CreateObject(); cJSON_AddStringToObject(ack,"type","command_ack");
      cJSON_AddStringToObject(ack,"command",cmd->valuestring); cJSON_AddStringToObject(ack,"id",id->valuestring);
      cJSON_AddBoolToObject(ack,"ok",start||stop); sendJson(ack);
      if(start) {
        statusLed.update(0,0,millis());
        sequence=0; sampleIndex=0;
        portENTER_CRITICAL(&guard); failed=false; enabled=true; portEXIT_CRITICAL(&guard);
        Serial.println("AUDIO_START_WIFI_ONLY");
      }
    }
  }
  cJSON_Delete(j);
}
static bool readConfig(cJSON *j) {
  const cJSON *s=cJSON_GetObjectItemCaseSensitive(j,"ssid"), *p=cJSON_GetObjectItemCaseSensitive(j,"password"),
    *h=cJSON_GetObjectItemCaseSensitive(j,"host"), *k=cJSON_GetObjectItemCaseSensitive(j,"token");
  if(!cJSON_IsString(s)||!cJSON_IsString(p)||!cJSON_IsString(h)||!cJSON_IsString(k)
    ||strlen(s->valuestring)<1||strlen(s->valuestring)>32||strlen(p->valuestring)>63
    ||strlen(h->valuestring)<1||strlen(h->valuestring)>253||strlen(k->valuestring)<16||strlen(k->valuestring)>128) return false;
  const cJSON *kind=cJSON_GetObjectItemCaseSensitive(j,"kind");
  String networkKind=cJSON_IsString(kind)?kind->valuestring:"wifi";
  if(networkKind!="wifi" && networkKind!="hotspot")return false;
  unsigned index=profileCount;
  for(unsigned n=0;n<profileCount;n++)if(profiles[n].ssid==s->valuestring)index=n;
  if(index==profileCount && profileCount>=4)return false;
  NetworkProfile next={s->valuestring,p->valuestring,h->valuestring,networkKind};
  if(index==profileCount)profileCount++;
  profiles[index]=next;
  if(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(j,"primary"))) {
    for(unsigned n=index;n>0;n--)profiles[n]=profiles[n-1];
    profiles[0]=next;
  }
  token=k->valuestring;
  return true;
}
static bool saveProfiles() {
  cJSON *array=cJSON_CreateArray();
  for(unsigned n=0;n<profileCount;n++) {
    cJSON *j=cJSON_CreateObject();
    cJSON_AddStringToObject(j,"ssid",profiles[n].ssid.c_str());
    cJSON_AddStringToObject(j,"password",profiles[n].password.c_str());
    cJSON_AddStringToObject(j,"host",profiles[n].host.c_str());
    cJSON_AddStringToObject(j,"kind",profiles[n].kind.c_str()); cJSON_AddItemToArray(array,j);
  }
  char *packed=cJSON_PrintUnformatted(array);
  bool saved=false;
  if(packed) {
    prefs.putString("networks",packed); saved=prefs.getString("networks","")==packed; free(packed);
  }
  cJSON_Delete(array); prefs.putString("token",token);
  return saved && prefs.getString("token","")==token;
}
static void loadProfiles() {
  String packed=prefs.getString("networks","");
  cJSON *array=cJSON_Parse(packed.c_str());
  if(cJSON_IsArray(array)) {
    for(int n=0;n<cJSON_GetArraySize(array) && profileCount<4;n++) {
      cJSON *j=cJSON_GetArrayItem(array,n);
      cJSON_AddStringToObject(j,"token",token.c_str());
      if(!readConfig(j)) { profileCount=0; break; }
    }
  }
  cJSON_Delete(array);
  if(!profileCount) {
    // Preserve the first working single-network configuration, without erasing it.
    ssid=prefs.getString("ssid",""); password=prefs.getString("pass",""); host=prefs.getString("host","");
    if(ssid.length() && host.length() && token.length()>=16) {
      profiles[0]={ssid,password,host,"wifi"}; profileCount=1;
    }
  }
}
static uint32_t fnv(uint32_t value,uint8_t byte) { return (value^byte)*16777619u; }
static void selfTest() {
  StatusLed led; led.begin(0);
  bool ledPass=led.color(0).r==32 && led.color(300).g==32 && led.color(600).b==32;
  ledPass=ledPass && led.color(2000).r==16 && led.color(2500).r==0;
  led.update(0,0,3000); ledPass=ledPass && led.color(3000).r==8;
  led.update(1,0,4000); ledPass=ledPass && led.color(4000).r==32 && led.color(4100).r==0 && led.color(4400).r==32;
  led.update(2,1,5000); ledPass=ledPass && led.color(6000).b==4 && led.color(7000).b==32;
  led.update(3,3,8000); ledPass=ledPass && led.color(8500).g==0 && led.color(8600).g==32;
  led.disconnect(); ledPass=ledPass && led.color(10000).r==16;
  Serial.println(ledPass?"SELFTEST_LED_PASS":"SELFTEST_LED_FAIL");
  // Exercise the ACTUAL profile binding without NVS writes or real credentials.
  NetworkProfile saved[4]; for(unsigned n=0;n<4;n++)saved[n]=profiles[n];
  unsigned savedCount=profileCount; String savedToken=token; profileCount=0;
  bool pass=true;
  for(unsigned n=0;n<4;n++) {
    cJSON *j=cJSON_CreateObject(); String name=String("synthetic-")+n;
    cJSON_AddStringToObject(j,"ssid",name.c_str()); cJSON_AddStringToObject(j,"password","fixture-password");
    cJSON_AddStringToObject(j,"host","192.0.2.10"); cJSON_AddStringToObject(j,"token","fixture-only-token-1234");
    cJSON_AddStringToObject(j,"kind",n==1?"hotspot":"wifi");
    pass=readConfig(j)&&pass; cJSON_Delete(j);
  }
  pass=pass && profileCount==4 && profiles[1].kind=="hotspot";
  cJSON *j=cJSON_CreateObject();
  cJSON_AddStringToObject(j,"ssid","synthetic-1"); cJSON_AddStringToObject(j,"password","fixture-updated");
  cJSON_AddStringToObject(j,"host","192.0.2.11"); cJSON_AddStringToObject(j,"token","fixture-only-token-1234");
  cJSON_AddStringToObject(j,"kind","hotspot"); cJSON_AddBoolToObject(j,"primary",true);
  pass=readConfig(j)&&pass; cJSON_Delete(j);
  pass=pass && profileCount==4 && profiles[0].ssid=="synthetic-1" && profiles[1].ssid=="synthetic-0";
  j=cJSON_CreateObject();
  cJSON_AddStringToObject(j,"ssid","fifth-network"); cJSON_AddStringToObject(j,"password","fixture-only");
  cJSON_AddStringToObject(j,"host","192.0.2.12"); cJSON_AddStringToObject(j,"token","fixture-only-token-1234");
  pass=!readConfig(j)&&pass; cJSON_Delete(j);
  for(unsigned n=0;n<4;n++)profiles[n]=saved[n]; profileCount=savedCount; token=savedToken;
  Serial.println(pass?"SELFTEST_PROFILES_PASS":"SELFTEST_PROFILES_FAIL");
  bool fallback=fallbackProfile(0,2)==1 && fallbackProfile(1,2)==0 && fallbackProfile(0,1)==0
    && !attemptExpired(14999,0) && attemptExpired(15000,0)
    && !attemptExpired(14983,0xfffffff0u) && attemptExpired(14984,0xfffffff0u);
  Serial.println(fallback?"SELFTEST_FALLBACK_PASS":"SELFTEST_FALLBACK_FAIL");
  int16_t samples[400]; uint8_t frame[832];
  for(int n=0;n<400;n++)samples[n]=(int16_t)((n*123)%65536-32768);
  encodeAudio(frame,samples,0x12345678,0xfffffffe,((uint64_t)0xfffffffe)*400);
  uint32_t hash=2166136261u; for(unsigned n=0;n<832;n++)hash=fnv(hash,frame[n]);
  Serial.print("SELFTEST_FRAME="); Serial.println(hash,HEX);
  AudioCodec codec; hash=2166136261u; int16_t out;
  for(int n=0;n<1600;n++)if(codec.push((int16_t)((n*97)%32000-16000),out)) {
    hash=fnv(hash,(uint16_t)out&255); hash=fnv(hash,((uint16_t)out)>>8);
  }
  Serial.print("SELFTEST_FIR="); Serial.println(hash,HEX);
}
static void provision() {
  while(Serial.available()) {
    char c=Serial.read();
    if(c=='\n') {
      if(input=="STATUS") {
        input=""; Serial.println("AURISCORE_WIFI_CAPTURE_V1");
        Serial.print("PROFILE_COUNT="); Serial.println(profileCount);
        Serial.print("RADIO_HOLD="); Serial.println(radioHold?1:0); continue;
      }
      if(input=="RETRY") { input=""; radioHold=false; Serial.println("WIFI_RETRY_REQUESTED"); continue; }
      if(input=="SELFTEST") { input=""; selfTest(); continue; }
      cJSON *j=cJSON_Parse(input.c_str()); input="";
      if(j && readConfig(j)) {
        if(!saveProfiles()) { cJSON_Delete(j); Serial.println("CONFIG_SAVE_FAILED"); continue; }
        cJSON_Delete(j); Serial.println("CONFIG_SAVED_REBOOTING"); Serial.flush(); delay(100); ESP.restart();
      }
      cJSON_Delete(j); Serial.println("CONFIG_REJECTED");
    } else if(c!='\r') {
      if(input.length()<768) input+=c;
      else { input=""; Serial.println("CONFIG_TOO_LONG"); }
    }
  }
}
static void captureTask(void*) {
  int32_t raw[1024]; AudioCodec codec; uint32_t localGeneration=0; bool wasEnabled=false;
  AudioBlock block{}; size_t fill=0;
  for(;;) {
    size_t bytes=0;
    esp_err_t status=i2s_read(I2S_NUM_0,raw,sizeof(raw),&bytes,pdMS_TO_TICKS(100));
    i2s_event_t event; bool dmaFault=false;
    while(xQueueReceive(i2sEvents,&event,0)==pdTRUE) {
      if(event.type==I2S_EVENT_RX_Q_OVF || event.type==I2S_EVENT_DMA_ERROR) dmaFault=true;
    }
    bool active; uint32_t current;
    portENTER_CRITICAL(&guard); active=enabled; current=generation; portEXIT_CRITICAL(&guard);
    if(!active) { wasEnabled=false; continue; }
    if(!wasEnabled || current!=localGeneration) {
      codec.reset(); fill=0; localGeneration=current; wasEnabled=true;
      // Capture continuously drains DMA while idle. Discard the crossing block
      // at the generation boundary; never fill gaps with fabricated silence.
      continue;
    }
    if(status!=ESP_OK || bytes!=sizeof(raw) || dmaFault) {
      portENTER_CRITICAL(&guard); failed=true; enabled=false; portEXIT_CRITICAL(&guard); continue;
    }
    for(size_t n=0;n<1024;n+=2) {
      int16_t output;
      if(!codec.push((int16_t)(raw[n]>>16),output))continue;
      block.samples[fill++]=output;
      if(fill==400) {
        block.queued=esp_timer_get_time(); block.generation=current;
        if(xQueueSend(blocks,&block,0)!=pdTRUE) {
          portENTER_CRITICAL(&guard); failed=true; enabled=false; portEXIT_CRITICAL(&guard);
          break;
        }
        fill=0;
      }
    }
  }
}
static void startCapture() {
  Serial.println("I2S_INIT_BEGIN");
  i2s_config_t cfg={};
  cfg.mode=(i2s_mode_t)(I2S_MODE_MASTER|I2S_MODE_RX); cfg.sample_rate=16000;
  cfg.bits_per_sample=I2S_BITS_PER_SAMPLE_32BIT; cfg.channel_format=I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format=I2S_COMM_FORMAT_STAND_I2S; cfg.intr_alloc_flags=ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count=32; cfg.dma_buf_len=256; cfg.use_apll=false;
  i2s_pin_config_t pins={}; pins.bck_io_num=16; pins.ws_io_num=18;
  pins.data_out_num=I2S_PIN_NO_CHANGE; pins.data_in_num=17;
  if(!blocks || i2s_driver_install(I2S_NUM_0,&cfg,8,&i2sEvents)!=ESP_OK || i2s_set_pin(I2S_NUM_0,&pins)!=ESP_OK) {
    Serial.println("I2S_INIT_FAILED"); while(true)delay(1000);
  }
  if(xTaskCreatePinnedToCore(captureTask,"audio",8192,NULL,3,NULL,1)!=pdPASS) {
    Serial.println("CAPTURE_TASK_FAILED"); while(true)delay(1000);
  }
  captureReady=true; Serial.println("I2S_READY");
}
void setup() {
#if AURISCORE_DISABLE_BROWNOUT
  esp_brownout_disable();
#endif
  statusLed.begin(millis());
  Serial.begin(115200); delay(300);
  Serial.printf("RUNTIME_SDK=%s FLASH_BYTES=%u PSRAM_BYTES=%u\n",
    ESP.getSdkVersion(), ESP.getFlashChipSize(), ESP.getPsramSize());
#ifdef BOARD_HAS_PSRAM
  Serial.println("BUILD_PSRAM_ENABLED=1");
#else
  Serial.println("BUILD_PSRAM_ENABLED=0");
#endif
#if AURISCORE_DISABLE_BROWNOUT
  Serial.println("BROWNOUT_DETECTOR_DISABLED");
#endif
  pinMode(7,OUTPUT); digitalWrite(7,LOW); // Keep the original buzzer inactive.
  prefs.begin("auris-wifi",false);
  token=prefs.getString("token",""); loadProfiles();
  configured=profileCount>0 && token.length()>=16;
  blocks=xQueueCreate(8,sizeof(AudioBlock));
  if(!blocks) { Serial.println("CAPTURE_QUEUE_FAILED"); while(true)delay(1000); }
  Serial.println(configured?"CONFIG_PRESENT":"PROVISION_OVER_USB_REQUIRED");
  // A recovery interval permits provisioning before any radio power surge.
  bootAt=millis(); radioHold=esp_reset_reason()==ESP_RST_BROWNOUT;
  Serial.println("USB_CONFIG_WINDOW_5S");
  if(radioHold)Serial.println("RADIO_RECOVERY_REQUIRED");
}
static void beginNetwork(unsigned index) {
  activeProfile=index; ssid=profiles[index].ssid; password=profiles[index].password; host=profiles[index].host;
  attemptAt=millis();
  Serial.print("WIFI_PROFILE_INDEX="); Serial.println(index);
  Serial.print("WIFI_PROFILE_KIND="); Serial.println(profiles[index].kind);
  WiFi.begin(ssid.c_str(),password.c_str()); Serial.println("WIFI_CONNECTING");
}
void loop() {
  statusLed.tick(millis());
  provision();
  if(!configured || radioHold || (uint32_t)(millis()-bootAt)<5000) { delay(10); return; }
  if(!radioStarted) {
    Serial.printf("BROWNOUT_HW_ENABLE=%u\n",
      (unsigned)((REG_READ(RTC_CNTL_BROWN_OUT_REG)&RTC_CNTL_BROWN_OUT_ENA)!=0));
    Serial.println("WIFI_INIT_BEGIN"); Serial.flush();
    if(!WiFi.mode(WIFI_STA)) {
      radioHold=true;
      Serial.println("WIFI_MODE_FAILED");
      return;
    }
    Serial.println("WIFI_MODE_READY"); Serial.flush();
    WiFi.setSleep(false); WiFi.setAutoReconnect(false); radioStarted=true; beginNetwork(0);
  }
  if(WiFi.status()!=WL_CONNECTED) {
    haltCapture();
    if(wasAssociated) {
      ws.disconnect(); networkStarted=false; wasAssociated=false; attemptAt=millis();
      WiFi.disconnect(false,false); beginNetwork(activeProfile);
    } else if(attemptExpired(millis(),attemptAt)) {
      WiFi.disconnect(false,false); beginNetwork(fallbackProfile(activeProfile,profileCount));
    }
    delay(20); return;
  }
  wasAssociated=true;
  if(!captureReady) startCapture();
  if(!networkStarted) {
    Serial.print("WIFI_IP="); Serial.println(WiFi.localIP());
    ws.onEvent(networkEvent); ws.setReconnectInterval(3000);
    ws.begin(host,gatewayPort,"/device",""); networkStarted=true;
  }
  ws.loop();
  bool fault, active; uint32_t current;
  portENTER_CRITICAL(&guard); fault=failed; failed=false; active=enabled; current=generation; portEXIT_CRITICAL(&guard);
  if(fault) { haltCapture(); ws.sendTXT("{\"type\":\"source_error\",\"reason\":\"Audio acquisition/queue overflow\"}"); }
  AudioBlock block;
  if(active && xQueueReceive(blocks,&block,0)==pdTRUE && block.generation==current) {
    if(esp_timer_get_time()-block.queued>250000) { haltCapture(); ws.sendTXT("{\"type\":\"source_error\",\"reason\":\"Audio backlog\"}"); }
    else {
      uint8_t frame[832]; encodeAudio(frame,block.samples,streamId,sequence,sampleIndex);
      if(!ws.sendBIN(frame,sizeof(frame))) { haltCapture(); ws.disconnect(); }
      else { sequence++; sampleIndex+=400; }
    }
  }
  delay(1);
}
