#pragma once
#include <stdint.h>
#include <Arduino.h>

// Common anode to 3V3. Each cathode connects through its own resistor.
#ifndef AURISCORE_LED_R_PIN
#define AURISCORE_LED_R_PIN 4
#endif
#ifndef AURISCORE_LED_G_PIN
#define AURISCORE_LED_G_PIN 5
#endif
#ifndef AURISCORE_LED_B_PIN
#define AURISCORE_LED_B_PIN 6
#endif
#ifndef AURISCORE_LED_PWM_HZ
#define AURISCORE_LED_PWM_HZ 5000
#endif
#ifndef AURISCORE_LED_GAIN
#define AURISCORE_LED_GAIN 7
#endif
struct LedColor { uint8_t r, g, b; };
class StatusLed {
  bool connected = false;
  int mode = 0, phase = 0;
  uint32_t boot = 0, flashAt = 0;
  unsigned flashes = 0;
  int8_t hardware = 0;
  LedColor previous = {0,0,0};
 public:
  void begin(uint32_t now) { boot = now; }
  void disconnect() { connected = false; mode = 0; phase = 0; flashes = 0; }
  void update(int nextMode, int nextPhase, uint32_t now) {
    connected = true;
    if (nextMode != mode) { flashes = 2; flashAt = now; }
    if (nextPhase == 3 && phase != 3) { flashes = 3; flashAt = now; }
    mode = nextMode; phase = nextPhase;
  }
  LedColor color(uint32_t now) const {
    uint32_t age = now - boot;
    if (age < 900) {
      if (age < 300) return {32,0,0};
      if (age < 600) return {0,32,0};
      return {0,0,32};
    }
    if (!connected) {
      uint8_t v = (age % 2000 < 300) ? 16 : 0;
      return {v,v,v};
    }
    if (!mode) return {8,8,8};
    uint8_t v = 32;
    uint32_t elapsed = now - flashAt;
    if (flashes && elapsed < flashes * 200) v = elapsed % 200 < 100 ? 32 : 0;
    else if (phase == 1) {
      unsigned cycle = age % 2000;
      unsigned ramp = cycle < 1000 ? cycle : 2000 - cycle;
      v = 4 + ramp * 28 / 1000;
    }
    if (mode == 1) return {v,0,0};
    if (mode == 2) return {0,0,v};
    // Add red to blue for Abdomen's purple, scaled with the same animation.
    return {static_cast<uint8_t>((v * 3 + 2) / 4),0,v};
  }
  void tick(uint32_t now) {
    if (hardware == 0) initOutput();
    if (hardware < 0) return;
    const LedColor next = color(now);
    if (next.r != previous.r) write(AURISCORE_LED_R_PIN, next.r);
    if (next.g != previous.g) write(AURISCORE_LED_G_PIN, next.g);
    if (next.b != previous.b) write(AURISCORE_LED_B_PIN, next.b);
    previous = next;
  }

 private:
  void initOutput() {
    const int pins[] = {AURISCORE_LED_R_PIN, AURISCORE_LED_G_PIN, AURISCORE_LED_B_PIN};
    unsigned attached = 0;
    for (int pin : pins) {
      digitalWrite(pin, HIGH);
      pinMode(pin, OUTPUT);
      if (!ledcAttach(pin, AURISCORE_LED_PWM_HZ, 8)) break;
      ledcWrite(pin, 255);
      ++attached;
    }
    if (attached == 3) {
      hardware = 1;
      Serial.println("LED_PWM_READY");
      return;
    }
    for (unsigned index = 0; index < attached; ++index) ledcDetach(pins[index]);
    for (int pin : pins) {
      pinMode(pin, OUTPUT);
      digitalWrite(pin, HIGH);
    }
    hardware = -1;
    Serial.println("LED_PWM_INIT_FAILED");
  }

  static void write(int pin, uint8_t intensity) {
    const uint32_t duty = static_cast<uint32_t>(intensity) * AURISCORE_LED_GAIN;
    ledcWrite(pin, 255 - min<uint32_t>(duty, 255));
  }
};
