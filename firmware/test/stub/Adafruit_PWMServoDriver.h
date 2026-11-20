#pragma once
#include <stdint.h>
#include <stdio.h>
extern bool g_trace_pwm;
extern uint16_t g_pwm[16];      // last microseconds written per channel
extern bool     g_pwm_off[16];  // true = that channel was switched off (limp)
extern uint32_t g_pwm_writes;   // how many writeMicroseconds calls in total
class Adafruit_PWMServoDriver {
public:
  Adafruit_PWMServoDriver(uint8_t a) : addr(a) {}
  void begin() {}
  void setOscillatorFrequency(uint32_t) {}
  void setPWMFreq(float) {}
  void setPWM(uint8_t ch, uint16_t on, uint16_t off) {
    g_pwm[ch] = 0; g_pwm_off[ch] = true;
    if (g_trace_pwm) printf("      [pwm] ch%u off\n", ch);
  }
  void writeMicroseconds(uint8_t ch, uint16_t us) {
    g_pwm[ch] = us; g_pwm_off[ch] = false; g_pwm_writes++;
    if (g_trace_pwm) printf("      [pwm] ch%u = %u us\n", ch, us);
  }
private:
  uint8_t addr;
};
