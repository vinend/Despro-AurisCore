#pragma once
#include <stdint.h>

// No GPIO is selected until the actual LED wiring is confirmed.
#ifndef AURISCORE_RGB_DATA_PIN
#define AURISCORE_RGB_DATA_PIN -1
#endif
struct LedColor { uint8_t r, g, b; };
class StatusLed {
  bool connected = false;
  int mode = 0, phase = 0;
  uint32_t boot = 0, flashAt = 0;
  unsigned flashes = 0;
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
    return {0,v,0};
  }
  void tick(uint32_t now) const {
#if AURISCORE_RGB_DATA_PIN >= 0
    LedColor c = color(now);
    rgbLedWrite(AURISCORE_RGB_DATA_PIN,c.r,c.g,c.b);
#endif
  }
};
