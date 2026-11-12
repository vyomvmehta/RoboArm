/*
  arm_controller.ino  --  RoboArm firmware v0
  Implements docs/PROTOCOL.md (DRAFT v1). Owner: Ishaan (D8). Checker: Vyom.

  WHAT v0 DOES
    Boots DISARMED (outputs off, servos limp), speaks the PROTOCOL.md line format
    over USB serial, enforces the safety states and the 300 ms watchdog, and drives
    the PCA9685 at 50 Hz. No motion limiter yet: that lands with the Nov 15 task,
    and until then a C frame is written straight to the outputs.

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

#define FW_VERSION "fw0.1"

static const uint8_t  PCA_ADDR      = 0x40;
static const uint32_t PCA_OSC_HZ    = 27000000UL;  // nominal; corrected at calibration (PROTOCOL.md s8)
static const uint16_t PWM_FREQ_HZ   = 50;
static const uint16_t WATCHDOG_MS   = 300;
static const uint8_t  NJOINTS       = 5;
static const uint8_t  LINE_MAX      = 64;          // longer than this -> error 2
static const uint8_t  MAX_FIELDS    = 8;

static const uint8_t  CHANNEL[NJOINTS]   = {0, 1, 2, 3, 4};

// Firmware hard limits (PROTOCOL.md s9): a safety floor, deliberately wider than the
// laptop's working range in config/calibration.yaml (550-2550), so they only trip on a bug.
//
// MEASURED (MG90S, 2026-11-10): 180 deg spans about 650-2600 us; the end stop is near 500 and
// it is still moving at 2600. J3 wrist and J4 gripper are MG90S, so these values are theirs.
//
// ASSUMED for J0-J2: those are MG996R 180s, which had not arrived when this was written and
// have never been measured. An MG996R whose travel stops at 2500 would STALL if driven to
// 2600. Measure them (firmware/two_servo_test: 'e' then 'w') and narrow these three entries
// before any of those joints is driven to an extreme. The arrays are per joint for that reason.
static const uint16_t PULSE_MIN[NJOINTS] = {500, 500, 500, 500, 500};
static const uint16_t PULSE_MAX[NJOINTS] = {2600, 2600, 2600, 2600, 2600};

// ---------------------------------------------------------------- state

enum State { ST_DISARMED, ST_ARMED, ST_HOLD, ST_FAULT };

static State    state         = ST_DISARMED;
static bool     pca_ok        = false;
static uint16_t current_us[NJOINTS];               // 0 = that channel is limp
static bool     outputs_live  = false;
static uint32_t last_c_ms     = 0;

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
  for (uint8_t j = 0; j < NJOINTS; ++j) current_us[j] = 0;
  outputs_live = false;
}

static void write_pose(const uint16_t us[NJOINTS]) {
  if (!pca_ok) return;
  for (uint8_t j = 0; j < NJOINTS; ++j) {
    pca.writeMicroseconds(CHANNEL[j], us[j]);
    current_us[j] = us[j];
  }
  outputs_live = true;
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

  uint16_t target[NJOINTS];
  for (uint8_t j = 0; j < NJOINTS; ++j) {
    uint32_t v;
    if (!parse_uint(field[2 + j], 65535UL, &v)) { send_e(seq, 2); return; }
    if (v < PULSE_MIN[j] || v > PULSE_MAX[j])   { send_e(seq, 3); return; }  // reject whole frame
    target[j] = (uint16_t)v;
  }

  write_pose(target);
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
  state = ST_ARMED;
  last_c_ms = millis();   // start the watchdog's 300 ms grace period now
  send_k(seq);
}

static void handle_d(uint8_t nfields, uint16_t seq) {
  if (nfields != 2) { send_e(seq, 2); return; }

  // v0 skips "move to park first" (brief): that needs the motion limiter.
  outputs_off();
  if (state != ST_FAULT) state = ST_DISARMED;   // FAULT only clears on reset
  send_k(seq);
}

static void handle_h(uint8_t nfields, uint16_t seq) {
  if (nfields != 2)        { send_e(seq, 2); return; }
  if (state != ST_ARMED)   { send_e(seq, 4); return; }

  // v0 acknowledges H but does NOT move. The home pose is an (x,y,z,pitch)
  // target in config/arm.yaml: reaching it needs IK plus the joint-angle ->
  // pulse map in calibration.yaml, and it must be ramped by the motion
  // limiter rather than jumped to. All three land with the Nov 15 task.
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

  for (uint8_t j = 0; j < NJOINTS; ++j) current_us[j] = 0;

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
}
