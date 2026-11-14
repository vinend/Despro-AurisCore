/* ESP32-S3 BLE bench test: public synthetic text only. */
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <esp_private/brownout.h>
#include <atomic>
#if !CONFIG_IDF_TARGET_ESP32S3
#error "Build for ESP32-S3"
#endif

static constexpr char SERVICE[] = "dce83010-8196-4ef1-ae1b-13b634324624";
static constexpr char TX_UUID[] = "dce83011-8196-4ef1-ae1b-13b634324624";
static constexpr char RX_UUID[] = "dce83012-8196-4ef1-ae1b-13b634324624";
static std::atomic<bool> connected{false};
static std::atomic<bool> pingPending{false};
static BLECharacteristic *output = nullptr;
static bool ready = false;
static bool attempted = false;
static uint32_t lastSent = 0, count = 0;

class ConnectionEvents : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    connected.store(true);
    Serial.println("BLE_CLIENT_CONNECTED");
  }
  void onDisconnect(BLEServer *) override {
    connected.store(false);
    pingPending.store(false);
    Serial.println("BLE_CLIENT_DISCONNECTED");
  }
};
class InputEvents : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *input) override {
    if (input->getValue() == "PING") pingPending.store(true);
  }
};
static ConnectionEvents connectionEvents;
static InputEvents inputEvents;

void setup() {
  esp_brownout_disable();
  Serial.begin(115200);
  delay(300);
  Serial.println("STANDALONE_BLE_RADIO_TEST_V2_MANUAL");
  Serial.println("BROWNOUT_DETECTOR_DISABLED");
  Serial.printf("CPU_MHZ=%u\n", getCpuFrequencyMhz());
  Serial.println("RADIO_IDLE_WAITING_FOR_R");
}

static void startBle() {
  attempted = true;
  Serial.printf("TRIAL_BEGIN UPTIME_MS=%lu\n", (unsigned long)millis());
  Serial.println("BLE_INIT_BEGIN");
  Serial.flush();
  if (!BLEDevice::init("AurisCore-BLE-Test")) {
    Serial.println("BLE_INIT_FAILED");
    return;
  }
  Serial.println("BLE_INIT_READY");
  BLEDevice::setPower(ESP_PWR_LVL_N12);
  Serial.println("BLE_TX_REQUEST_DBM=-12");
  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(&connectionEvents);
  server->advertiseOnDisconnect(true);
  BLEService *service = server->createService(SERVICE);
  output = service->createCharacteristic(TX_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
  output->addDescriptor(new BLE2902());
  output->setValue("BLE_READY");
  BLECharacteristic *input = service->createCharacteristic(RX_UUID, BLECharacteristic::PROPERTY_WRITE);
  input->setCallbacks(&inputEvents);
  service->start();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(SERVICE);
  advertising->setScanResponse(true);
  advertising->setMinInterval(800);
  advertising->setMaxInterval(1600);
  BLEDevice::startAdvertising();
  ready = true;
  Serial.println("BLE_ADVERTISING AurisCore-BLE-Test");
}

void loop() {
  while (Serial.available()) {
    char command = Serial.read();
    if (command == 'r' || command == 'R') {
      if (!attempted) startBle();
      else Serial.println("RADIO_ALREADY_ATTEMPTED_REBOOT_TO_REPEAT");
    }
    if (command == 's' || command == 'S') {
      Serial.printf("STANDALONE_BLE_RADIO_TEST_V2_MANUAL READY=%d CONNECTED=%d ATTEMPTED=%d UPTIME_MS=%lu\n", ready, connected.load(), attempted, (unsigned long)millis());
    }
  }
  if (ready && connected.load()) {
    const bool pong = pingPending.exchange(false);
    if (pong || (uint32_t)(millis() - lastSent) >= 1000) {
      char message[20];
      if (pong) snprintf(message, sizeof(message), "PONG");
      else snprintf(message, sizeof(message), "BEAT %lu", (unsigned long)++count);
      output->setValue(message);
      output->notify();
      lastSent = millis();
      if (pong) Serial.println("BLE_PONG_SENT");
    }
  }
  delay(20);
}
