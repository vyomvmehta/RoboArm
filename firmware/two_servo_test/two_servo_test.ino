/*
  two_servo_test.ino  --  bench test for two servos on PCA9685 channels 0 and 1.

  A throwaway test tool, not the arm firmware. No protocol, no checksums, no
  watchdog: just type a pulse width and watch the servo. Use this to find where
  each servo's real travel ends before trusting arm_controller's 1000-2000 limits.

  WIRING
    Nano 5V  -> PCA9685 VCC   (logic only)     Nano GND -> PCA9685 GND
    Nano A4  -> PCA9685 SDA                    Nano A5  -> PCA9685 SCL
    LM2596 6.0 V OUT+ -> PCA9685 V+ screw terminal, OUT- -> its GND terminal
    Servos on output headers 0 and 1: brown/black to GND, red to V+, orange to PWM.

  SERIAL MONITOR: 115200 baud, line ending "Newline".

  COMMANDS
    0 1500     channel 0 to 1500 us
    1 1700     channel 1 to 1700 us
    c          both to 1500 us
    d          both limp (stops pulses: this is the panic button)
    w          slow sweep of the current channel, any key stops it
    s          show what each channel is set to
    e          widen the allowed range to 500-2500 for finding the real end stops

  SAFETY
    Boots limp. Moves in small steps rather than jumping, so a servo eases into
    position instead of slamming. If a servo buzzes and stops moving it is stalled
    against its mechanical limit: press d straight away.
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca(0x40);

const uint8_t CH[2]    = {0, 1};      // PCA9685 output channels in use
const uint16_t CENTRE  = 1500;
const uint8_t  STEP_US = 20;          // move this much per step
const uint8_t  STEP_MS = 20;          // wait this long between steps

uint16_t lo_limit = 1000;             // conservative until you have measured
uint16_t hi_limit = 2000;             // 'e' widens these to 500-2500

int current[2] = {-1, -1};            // -1 = limp, otherwise the pulse in us
uint8_t last_ch = 0;                  // which channel 'w' sweeps
bool pca_ok = false;

char line[32];
uint8_t len = 0;

// ---------------------------------------------------------------- helpers

void limp_all() {
  for (uint8_t i = 0; i < 2; i++) {
    if (pca_ok) pca.setPWM(CH[i], 0, 0);   // no pulses at all
    current[i] = -1;
  }
  Serial.println(F("both channels limp"));
}

// Ease to the target instead of jumping, so the servo draws less and you can
// hear or see it stall before it has been fighting for long.
void move_to(uint8_t idx, uint16_t target) {
  if (!pca_ok) { Serial.println(F("no PCA9685")); return; }
  if (target < lo_limit || target > hi_limit) {
    Serial.print(F("refused: ")); Serial.print(target);
    Serial.print(F(" us is outside ")); Serial.print(lo_limit);
    Serial.print(F("-")); Serial.print(hi_limit);
    Serial.println(F(" (press e to widen)"));
    return;
  }
  if (current[idx] < 0) {                 // limp: no idea where it is, go straight there
    pca.writeMicroseconds(CH[idx], target);
  } else {
    int from = current[idx];
    int dir  = (target > from) ? STEP_US : -(int)STEP_US;
    while (abs(target - from) > STEP_US) {
      from += dir;
      pca.writeMicroseconds(CH[idx], (uint16_t)from);
      delay(STEP_MS);
      if (Serial.available()) break;      // any keypress aborts the move
    }
    pca.writeMicroseconds(CH[idx], target);
  }
  current[idx] = target;
  last_ch = idx;
  Serial.print(F("ch")); Serial.print(CH[idx]);
  Serial.print(F(" -> ")); Serial.print(target); Serial.println(F(" us"));
}

void sweep(uint8_t idx) {
  Serial.print(F("sweeping ch")); Serial.print(CH[idx]);
  Serial.println(F(" slowly. Send any character to stop."));
  for (uint16_t p = lo_limit; p <= hi_limit; p += STEP_US) {
    pca.writeMicroseconds(CH[idx], p);
    current[idx] = p;
    Serial.print(p); Serial.println(F(" us"));
    delay(120);
    if (Serial.available()) { while (Serial.available()) Serial.read(); break; }
  }
  Serial.println(F("sweep done (still holding: press d to go limp)"));
}

void status() {
  for (uint8_t i = 0; i < 2; i++) {
    Serial.print(F("ch")); Serial.print(CH[i]); Serial.print(F(": "));
    if (current[i] < 0) Serial.println(F("limp"));
    else { Serial.print(current[i]); Serial.println(F(" us")); }
  }
  Serial.print(F("allowed range ")); Serial.print(lo_limit);
  Serial.print(F("-")); Serial.println(hi_limit);
}

// ---------------------------------------------------------------- command parsing

void handle(char *s) {
  if (s[0] == '\0') return;

  if (s[0] == 'd' && s[1] == '\0') { limp_all(); return; }
  if (s[0] == 's' && s[1] == '\0') { status();   return; }
  if (s[0] == 'w' && s[1] == '\0') { sweep(last_ch); return; }
  if (s[0] == 'c' && s[1] == '\0') { move_to(0, CENTRE); move_to(1, CENTRE); return; }
  if (s[0] == 'e' && s[1] == '\0') {
    lo_limit = 500; hi_limit = 2500;
    Serial.println(F("range widened to 500-2500 us."));
    Serial.println(F("Go in small steps and press d the moment a servo buzzes."));
    return;
  }

  // "<channel> <microseconds>", e.g. "0 1500"
  if ((s[0] == '0' || s[0] == '1') && s[1] == ' ') {
    uint8_t idx = s[0] - '0';
    long us = atol(s + 2);
    if (us <= 0) { Serial.println(F("give a pulse width, e.g. 0 1500")); return; }
    move_to(idx, (uint16_t)us);
    return;
  }

  Serial.println(F("commands: '0 1500', '1 1700', c, d, w, s, e"));
}

// ---------------------------------------------------------------- setup / loop

void setup() {
  Serial.begin(115200);
  Wire.begin();
  Wire.setWireTimeout(25000, true);

  Wire.beginTransmission(0x40);
  pca_ok = (Wire.endTransmission() == 0);

  if (pca_ok) {
    pca.begin();
    pca.setOscillatorFrequency(27000000);   // nominal: tune this during calibration
    pca.setPWMFreq(50);
    limp_all();
    Serial.println(F("PCA9685 found at 0x40."));
  } else {
    Serial.println(F("No PCA9685 at 0x40. Check VCC->5V, GND, SDA->A4, SCL->A5."));
  }

  Serial.println(F("two_servo_test: channels 0 and 1. Boots limp."));
  Serial.println(F("commands: '0 1500', '1 1700', c = centre, d = limp, w = sweep, s = status, e = widen range"));
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { line[len] = '\0'; handle(line); len = 0; continue; }
    if (len < sizeof(line) - 1) line[len++] = c;
  }
}
