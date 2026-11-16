#pragma once
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>
#include <cstddef>

extern uint32_t g_millis;
inline uint32_t millis() { return g_millis; }

extern std::string g_in;        // pending serial input
extern size_t      g_in_pos;
extern std::vector<std::string> g_out;   // emitted lines
extern std::string g_partial;

struct FakeSerial {
  void begin(long) {}
  int available() { return (int)(g_in.size() - g_in_pos); }
  int read() { return g_in_pos < g_in.size() ? (unsigned char)g_in[g_in_pos++] : -1; }
  void print(const char *s) { g_partial += s; }
  void print(char c) {
    if (c == '\n') { g_out.push_back(g_partial); g_partial.clear(); }
    else g_partial += c;
  }
};
extern FakeSerial Serial;
