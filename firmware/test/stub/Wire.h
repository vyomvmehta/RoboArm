#pragma once
#include <stdint.h>
extern bool g_pca_present;
struct FakeWire {
  void begin() {}
  void setWireTimeout(uint32_t, bool) {}
  void beginTransmission(uint8_t) {}
  uint8_t endTransmission() { return g_pca_present ? 0 : 2; }
};
extern FakeWire Wire;
