// Bench test for one servo (Parts test day, Nov 2026). A throwaway test tool, not the arm firmware
// (that's Ishaan's firmware/arm_controller, through the PCA9685).
//
// Wiring: servo signal (orange/yellow) -> Nano D9. Servo red -> LM2596 OUT+ (set to 6.0 V FIRST).
//         Servo brown/black -> LM2596 OUT-, AND Nano GND -> LM2596 OUT- (common ground).
//         Nano powered from the laptop's USB only. Never connect servo red to the Nano's 5V pin.
//
// Serial Monitor at 115200 baud, line ending "Newline". Type:
//   1500      -> move to that pulse width in microseconds (allowed 600-2400)
//   d         -> detach: stop sending pulses, servo goes limp
//   ?         -> show the current pulse
// Start at 1500 (centre). Most MG996R/MG90S servos cover roughly 1000-2000 us for ~180 degrees;
// go wider only in small steps and stop if the servo buzzes at an end.

#include <Servo.h>

const int SERVO_PIN = 9;
const int MIN_US = 600;
const int MAX_US = 2400;

Servo servo;
int current_us = -1;  // -1 = detached

void setup() {
  Serial.begin(115200);
  Serial.println(F("Bench test ready. Type a pulse in us (600-2400), d = limp, ? = status."));
  Serial.println(F("Servo is limp until you send a pulse."));
}

void loop() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) return;

  if (line == "d") {
    servo.detach();
    current_us = -1;
    Serial.println(F("Detached (limp)."));
  } else if (line == "?") {
    if (current_us < 0) Serial.println(F("Detached (limp)."));
    else { Serial.print(F("Holding ")); Serial.print(current_us); Serial.println(F(" us")); }
  } else {
    long us = line.toInt();
    if (us < MIN_US || us > MAX_US) {
      Serial.print(F("Rejected '")); Serial.print(line); Serial.println(F("': use 600-2400, d or ?"));
      return;
    }
    if (!servo.attached()) servo.attach(SERVO_PIN, MIN_US, MAX_US);
    servo.writeMicroseconds((int)us);
    current_us = (int)us;
    Serial.print(F("Moving to ")); Serial.print(current_us); Serial.println(F(" us"));
  }
}
