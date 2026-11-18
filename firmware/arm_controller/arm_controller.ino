/*
  arm_controller.ino  --  RoboArm firmware v0
  Implements docs/PROTOCOL.md (DRAFT v1). Owner: Ishaan (D8). Checker: Vyom.

  WHAT THIS DOES
    Boots DISARMED (outputs off, servos limp), speaks the PROTOCOL.md line format
    over USB serial, enforces the safety states and the 300 ms watchdog, and drives
    the PCA9685 at 50 Hz.

    A C frame sets a TARGET; it is never written straight to the outputs. The motion
    limiter walks each joint towards its target at that joint's own speed cap, so no
    frame -- however far it jumps, and however fast they arrive -- can make a joint
    move faster than config/arm.yaml allows.

  WHAT IS STILL MISSING (each needs the assembled arm, or a decision)
    D goes straight limp instead of ramping to park first, and H acknowledges without
    moving. Both need park/home as PULSES, which means IK and the angle->pulse map --
    both of which live on the laptop, not here. See handle_d and handle_h.

  HARDWARE
    Laptop -- USB -- Arduino Nano -- I2C -- PCA9685 -- servos
      Nano 5V  -> PCA9685 VCC   (logic only)      Nano GND -> PCA9685 GND
      Nano A4  -> PCA9685 SDA                     Nano A5  -> PCA9685 SCL
      LM2596 6.0 V OUT+ -> PCA9685 V+ screw terminal, OUT- -> its GND terminal
      All grounds tied together. Never feed the Nano's 5V into V+.

  CHANNEL MAP (PCA9685 output header)
      ch0 = J0 base      ch1 = J1 shoulder   ch2 = J2 elbow
      ch3 = J3 wrist     ch4 = J4 gripper
    Bench test uses one MG90S on ch4.

  LIBRARY
    "Adafruit PWM Servo Driver Library" (Arduino IDE: Tools > Manage Libraries).

  SERIAL MONITOR
    115200 baud, line ending "Newline".
*/

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// ---------------------------------------------------------------- configuration

#define FW_VERSION "fw0.2"   // 0.2 = the motion limiter below. The banner is the only way
                             // to tell from the bench which firmware is on the board.

static const uint8_t  PCA_ADDR      = 0x40;
static const uint32_t PCA_OSC_HZ    = 27000000UL;  // nominal; corrected at calibration (PROTOCOL.md s8)
static const uint16_t PWM_FREQ_HZ   = 50;
static const uint16_t WATCHDOG_MS   = 300;
static const uint8_t  NJOINTS       = 5;
static const uint8_t  LINE_MAX      = 64;          // longer than this -> error 2
static const uint8_t  MAX_FIELDS    = 8;

static const uint8_t  CHANNEL[NJOINTS]   = {0, 1, 2, 3, 4};

// Firmware hard limits (PROTOCOL.md s9): the last guard against a bad frame. Uniform across
// all five joints (agreed in person with Vyom, 2026-11-13).
//
// MEASURED 2026-11-13 at Velocity, every servo: 450-2500 us for a full 180 deg, which is
// 11.4 us/deg, mid-travel 1475 us.
//
// The laptop's working range in config/calibration.yaml is 500-2450, sitting 50 us inside
// these, which is the margin s9 asks for.
static const uint16_t PULSE_MIN[NJOINTS] = { 450,  450,  450,  450,  450};
static const uint16_t PULSE_MAX[NJOINTS] = {2500, 2500, 2500, 2500, 2500};

// Motion limiter (PROTOCOL.md s6: ARMED "ramps every joint towards the latest C target").
//
// Each joint is capped on its OWN speed, independently. This deliberately does NOT
// synchronise the joints the way arm/motion.py step_toward does: that shapes the path,
// which is the laptop's job. This is a ceiling and nothing more. Two layers both shaping
// the path would only fight each other.
//
// The caps are config/arm.yaml speed_limits_deg_per_s and us_per_deg is
// config/calibration.yaml. Both are the laptop's files; if either moves, move it here
// too. Both get retuned at calibration (Nov 21-23), so expect these to change.
static const uint16_t TICK_MS = 20;               // = the 50 Hz PWM frame. Writing more
                                                  // often cannot change what a servo sees.
static const uint32_t US_PER_DEG_MILLI = 11389;   // calibration.yaml us_per_deg 11.3889, x1000

// Step per tick, in THOUSANDTHS of a microsecond, and positions are kept in milli-us to
// match. The fraction is the whole reason: at 45 deg/s a tick is 10.25 us, and rounding
// that down to 10 would run the joint 2.4 % slow, further out the longer the move runs.
#define STEP_MILLI(deg_per_s) \
  ((uint32_t)(((uint32_t)(deg_per_s) * US_PER_DEG_MILLI * TICK_MS) / 1000UL))
static const uint32_t STEP_MILLI_US[NJOINTS] = {
  STEP_MILLI(45),   // j0 base      -> 10250 = 10.25 us/tick = 512.5 us/s = 45 deg/s
  STEP_MILLI(45),   // j1 shoulder     a full 450-2500 sweep takes 4.0 s
  STEP_MILLI(45),   // j2 elbow
  STEP_MILLI(90),   // j3 wrist     -> 20500 = 20.50 us/tick = 1025 us/s = 90 deg/s
  STEP_MILLI(90)    // j4 gripper      the same sweep takes 2.0 s
};

// ---------------------------------------------------------------- state

enum State { ST_DISARMED, ST_ARMED, ST_HOLD, ST_FAULT };

static State    state         = ST_DISARMED;
static bool     pca_ok        = false;
static uint16_t current_us[NJOINTS];               // what is on the pins now; 0 = limp
static uint16_t target_us[NJOINTS];                // what the latest accepted C asked for
static uint32_t pos_milli[NJOINTS];                // where the ramp has got to, in milli-us
static bool     have_target   = false;             // false = no C since arming, outputs off
static uint32_t last_c_ms     = 0;
static uint32_t last_tick_ms  = 0;

static char     line_buf[LINE_MAX + 1];
static uint8_t  line_len      = 0;
static bool     line_overflow = false;

static Adafruit_PWMServoDriver pca(PCA_ADDR);

static const char *state_name(State s) {
  switch (s) {
    case ST_DISARMED: return "DISARMED";
    case ST_ARMED:    return "ARMED";
    case ST_HOLD:     return "HOLD";
    default:          return "FAULT";
  }
}

// ---------------------------------------------------------------- line output

// Appends the XOR checksum and a bare '\n' (not "\r\n": PROTOCOL.md s1 says lines end in \n).
static void send_line(const char *payload) {
  uint8_t cs = 0;
  for (const char *p = payload; *p; ++p) cs ^= (uint8_t)*p;
  char tail[4];
  tail[0] = '*';
  tail[1] = "0123456789ABCDEF"[(cs >> 4) & 0x0F];
  tail[2] = "0123456789ABCDEF"[cs & 0x0F];
  tail[3] = '\0';
  Serial.print(payload);
  Serial.print(tail);
  Serial.print('\n');
}

static void send_k(uint16_t seq) {
  char buf[32];
  snprintf(buf, sizeof(buf), "K,%u,%s", (unsigned)seq, state_name(state));
  send_line(buf);
}

static void send_e(uint16_t seq, uint8_t code) {
  char buf[20];
  snprintf(buf, sizeof(buf), "E,%u,%u", (unsigned)seq, (unsigned)code);
  send_line(buf);
}

static void send_banner() {
  char buf[40];
  snprintf(buf, sizeof(buf), "R,0,%s,%s", FW_VERSION, state_name(state));
  send_line(buf);
}

// ---------------------------------------------------------------- outputs

static void outputs_off() {
  if (pca_ok) {
    for (uint8_t j = 0; j < NJOINTS; ++j) pca.setPWM(CHANNEL[j], 0, 0);
  }
  for (uint8_t j = 0; j < NJOINTS; ++j) { current_us[j] = 0; pos_milli[j] = 0; }
  have_target = false;
}

// Puts the ramp's position on the pins. Only the channels that actually changed are
// written: with one slider moving, that is one I2C write per tick instead of five.
//
// No clamp is needed here. pos_milli only ever holds an accepted target x1000, or a value
// between two of them, and every accepted target passed PULSE_MIN/PULSE_MAX in handle_c.
static void write_current() {
  if (!pca_ok) return;
  for (uint8_t j = 0; j < NJOINTS; ++j) {
    uint16_t us = (uint16_t)((pos_milli[j] + 500UL) / 1000UL);   // round to nearest us
    if (us == current_us[j]) continue;
    pca.writeMicroseconds(CHANNEL[j], us);
    current_us[j] = us;
  }
}

// One step per tick towards the target, per joint, capped. Driven from loop().
static void advance_ramp() {
  // ARMED only. HOLD has to freeze wherever the ramp got to (PROTOCOL.md s6: HOLD keeps
  // the last CURRENT pulses) -- the laptop has gone quiet, so creeping on towards a stale
  // target is the last thing we want. DISARMED and FAULT have no outputs at all.
  if (state != ST_ARMED || !have_target) return;

  uint32_t now = millis();
  if ((uint32_t)(now - last_tick_ms) < TICK_MS) return;
  last_tick_ms = now;
  // Deliberately not "last_tick_ms += TICK_MS": if the loop ever stalls, we take one step
  // late rather than several at once. A stall then makes the arm lag, never lurch.

  for (uint8_t j = 0; j < NJOINTS; ++j) {
    uint32_t goal = (uint32_t)target_us[j] * 1000UL;
    uint32_t step = STEP_MILLI_US[j];
    if (goal > pos_milli[j]) {
      pos_milli[j] = (goal - pos_milli[j] <= step) ? goal : pos_milli[j] + step;
    } else if (goal < pos_milli[j]) {
      pos_milli[j] = (pos_milli[j] - goal <= step) ? goal : pos_milli[j] - step;
    }
  }
  write_current();
}

// ---------------------------------------------------------------- parsing

// Strict unsigned decimal: digits only, no sign, no spaces, no overflow past max.
static bool parse_uint(const char *s, uint32_t max, uint32_t *out) {
  if (s == NULL || *s == '\0') return false;
  uint32_t v = 0;
  for (const char *p = s; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    v = v * 10UL + (uint32_t)(*p - '0');
    if (v > max) return false;
  }
  *out = v;
  return true;
}

static bool hex_nibble(char c, uint8_t *out) {
  if (c >= '0' && c <= '9') { *out = (uint8_t)(c - '0');        return true; }
  if (c >= 'A' && c <= 'F') { *out = (uint8_t)(c - 'A' + 10);   return true; }
  if (c >= 'a' && c <= 'f') { *out = (uint8_t)(c - 'a' + 10);   return true; }
  return false;
}

// Best-effort seq for an error reply on a line we could not fully parse.
// Reads the second comma-separated field; 0 if it is missing or not a number.
static uint16_t sniff_seq(const char *s, uint8_t len) {
  uint8_t i = 0;
  while (i < len && s[i] != ',') ++i;
  if (i >= len) return 0;
  ++i;
  char tmp[6];
  uint8_t n = 0;
  while (i < len && s[i] != ',' && s[i] != '*' && n < sizeof(tmp) - 1) tmp[n++] = s[i++];
  tmp[n] = '\0';
  uint32_t v;
  if (!parse_uint(tmp, 65535UL, &v)) return 0;
  return (uint16_t)v;
}

// ---------------------------------------------------------------- message handlers

static void handle_c(char *field[], uint8_t nfields, uint16_t seq) {
  // C,<seq>,p0,p1,p2,p3,p4  -> 7 fields exactly
  if (nfields != 2 + NJOINTS) { send_e(seq, 2); return; }

  // A C frame is only honoured while the arm is live. HOLD counts: a valid C
  // there is what brings us back to ARMED (PROTOCOL.md s6).
  if (state != ST_ARMED && state != ST_HOLD) { send_e(seq, 4); return; }

  uint16_t want[NJOINTS];
  for (uint8_t j = 0; j < NJOINTS; ++j) {
    uint32_t v;
    if (!parse_uint(field[2 + j], 65535UL, &v)) { send_e(seq, 2); return; }
    if (v < PULSE_MIN[j] || v > PULSE_MAX[j])   { send_e(seq, 3); return; }  // reject whole frame
    want[j] = (uint16_t)v;
  }
  // Nothing above this line has touched the target, so a rejected frame leaves the old
  // one standing and the ramp carries on towards it (error 3, PROTOCOL.md s5).
  for (uint8_t j = 0; j < NJOINTS; ++j) target_us[j] = want[j];

  if (!have_target) {
    // First C since arming. With no position feedback, this frame is the only thing that
    // can say where the arm is, so take it as the truth and start the ramp from there
    // rather than sweeping to it from some assumed pose. The laptop holds up its end:
    // arm/control.py arm() sets the target to park BEFORE sending A, so the first C is
    // the park pose, and a limp arm is already resting at park (PROTOCOL.md s6).
    for (uint8_t j = 0; j < NJOINTS; ++j) pos_milli[j] = (uint32_t)target_us[j] * 1000UL;
    have_target  = true;
    last_tick_ms = millis();
    write_current();      // the starting pose: declared, not travelled to
  }

  last_c_ms = millis();
  state = ST_ARMED;
  send_k(seq);
}

static void handle_a(uint8_t nfields, uint16_t seq) {
  if (nfields != 2)          { send_e(seq, 2); return; }
  if (state != ST_DISARMED)  { send_e(seq, 7); return; }

  // No position feedback exists, so the firmware cannot verify the park pose.
  // PROTOCOL.md s6 makes that the operator's job. Outputs stay off until the
  // first C frame arrives, so arming never jerks the arm.
  have_target = false;    // and that first C is what re-seeds the ramp
  state = ST_ARMED;
  last_c_ms = millis();   // start the watchdog's 300 ms grace period now
  send_k(seq);
}

static void handle_d(uint8_t nfields, uint16_t seq) {
  if (nfields != 2) { send_e(seq, 2); return; }

  // Still goes straight limp rather than ramping to park first (PROTOCOL.md s3). The
  // limiter exists now, but park is defined in config/arm.yaml as JOINT ANGLES, and
  // turning those into pulses needs the angle->pulse map on the laptop. The laptop is
  // also the right owner: arm/control.py disarm() can set its target to park, let this
  // limiter ramp there, and only then send D -- same end behaviour, no duplicated map.
  // Hard-coding a park pose here would copy that contract into the place that is hardest
  // to correct, and every number it would copy is a placeholder until calibration.
  outputs_off();
  if (state != ST_FAULT) state = ST_DISARMED;   // FAULT only clears on reset
  send_k(seq);
}

static void handle_h(uint8_t nfields, uint16_t seq) {
  if (nfields != 2)        { send_e(seq, 2); return; }
  if (state != ST_ARMED)   { send_e(seq, 4); return; }

  // Acknowledges H but still does NOT move. home is an (x, y, z, pitch) target in
  // config/arm.yaml, so reaching it needs IK and the angle->pulse map, both of which are
  // on the laptop. With the limiter in place the laptop does not really need H any more:
  // it can run IK itself and just move its own target, and the ramp here makes that
  // smooth. Whether H still earns its place in the protocol is a call for all three.
  send_k(seq);
}

static void handle_p(uint8_t nfields, uint16_t seq) {
  if (nfields != 2) { send_e(seq, 2); return; }
  send_k(seq);      // ping: touches nothing, and does not feed the watchdog
}

// ---------------------------------------------------------------- line dispatch

static void handle_line() {
  if (line_overflow) { send_e(0, 2); return; }   // line > 64 chars
  if (line_len == 0) return;                     // blank line: ignore silently

  // Checksum must be the last three characters: '*' then two hex digits.
  if (line_len < 4 || line_buf[line_len - 3] != '*') {
    send_e(sniff_seq(line_buf, line_len), 2);
    return;
  }
  uint8_t hi, lo;
  if (!hex_nibble(line_buf[line_len - 2], &hi) || !hex_nibble(line_buf[line_len - 1], &lo)) {
    send_e(sniff_seq(line_buf, line_len), 2);
    return;
  }

  uint8_t payload_len = line_len - 3;
  uint8_t want = (uint8_t)((hi << 4) | lo);
  uint8_t got  = 0;
  for (uint8_t i = 0; i < payload_len; ++i) got ^= (uint8_t)line_buf[i];
  if (got != want) {
    send_e(sniff_seq(line_buf, payload_len), 1);
    return;
  }

  // Split the payload in place on commas.
  line_buf[payload_len] = '\0';
  char *field[MAX_FIELDS];
  uint8_t nfields = 0;
  field[nfields++] = line_buf;
  for (uint8_t i = 0; i < payload_len; ++i) {
    if (line_buf[i] == ',') {
      line_buf[i] = '\0';
      if (nfields >= MAX_FIELDS) { send_e(0, 2); return; }
      field[nfields++] = &line_buf[i + 1];
    }
  }

  if (field[0][0] == '\0' || field[0][1] != '\0') { send_e(0, 2); return; }  // type is one letter

  uint32_t seq32;
  if (nfields < 2 || !parse_uint(field[1], 65535UL, &seq32)) { send_e(0, 2); return; }
  uint16_t seq = (uint16_t)seq32;

  switch (field[0][0]) {
    case 'C': handle_c(field, nfields, seq); break;
    case 'A': handle_a(nfields, seq);        break;
    case 'D': handle_d(nfields, seq);        break;
    case 'H': handle_h(nfields, seq);        break;
    case 'P': handle_p(nfields, seq);        break;
    default:  send_e(seq, 5);                break;
  }
}

static void read_serial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      handle_line();
      line_len = 0;
      line_overflow = false;
      continue;
    }
    if (line_overflow) continue;               // drop the rest of an over-long line
    if (line_len < LINE_MAX) line_buf[line_len++] = c;
    else                     line_overflow = true;
  }
}

// ---------------------------------------------------------------- watchdog

static void service_watchdog() {
  if (state != ST_ARMED) return;
  if ((uint32_t)(millis() - last_c_ms) < WATCHDOG_MS) return;

  // HOLD keeps the last pulses on the outputs: do not touch them.
  state = ST_HOLD;
  send_e(0, 6);   // unsolicited, so seq 0 (same convention as the R banner)
}

// ---------------------------------------------------------------- setup / loop

void setup() {
  Serial.begin(115200);

  for (uint8_t j = 0; j < NJOINTS; ++j) { current_us[j] = 0; target_us[j] = 0; pos_milli[j] = 0; }
  last_tick_ms = millis();

  Wire.begin();
  Wire.setWireTimeout(25000, true);   // never hang if SDA/SCL are shorted

  Wire.beginTransmission(PCA_ADDR);
  pca_ok = (Wire.endTransmission() == 0);

  if (pca_ok) {
    pca.begin();
    pca.setOscillatorFrequency(PCA_OSC_HZ);
    pca.setPWMFreq(PWM_FREQ_HZ);
    outputs_off();                    // boot limp
    state = ST_DISARMED;
  } else {
    state = ST_FAULT;
  }

  send_banner();                      // healthy boot gives exactly R,0,fw0.1,DISARMED*71
  if (!pca_ok) send_e(0, 8);          // PCA9685 missing: outputs stay off until reset
}

void loop() {
  read_serial();
  service_watchdog();
  advance_ramp();     // after the watchdog, so a pass that drops us into HOLD freezes the
                      // pose on that same pass instead of taking one more step first
}
