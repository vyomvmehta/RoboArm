#include "stub/Arduino.h"
#include "stub/Wire.h"
#include "stub/Adafruit_PWMServoDriver.h"
uint32_t g_millis = 0;
std::string g_in; size_t g_in_pos = 0;
std::vector<std::string> g_out; std::string g_partial;
FakeSerial Serial; FakeWire Wire;
bool g_pca_present = true;
bool g_trace_pwm = false;
uint16_t g_pwm[16]; bool g_pwm_off[16]; uint32_t g_pwm_writes = 0;

#include "../arm_controller/arm_controller.ino"

static int fails = 0, checks = 0;

static std::string cs(const std::string &p) {
  unsigned char x = 0; for (char c : p) x ^= (unsigned char)c;
  char b[8]; snprintf(b, sizeof(b), "*%02X", x); return p + b;
}

static void drain() { g_out.clear(); }

static void expect(const char *label, const std::string &line,
                   const std::vector<std::string> &want_payloads) {
  g_out.clear();
  g_in = line + "\n"; g_in_pos = 0;
  loop();
  checks++;
  std::vector<std::string> want;
  for (auto &p : want_payloads) want.push_back(cs(p));
  bool ok = (g_out == want);
  printf("%-4s %-46s -> ", ok ? "PASS" : "FAIL", line.c_str());
  for (size_t i = 0; i < g_out.size(); i++) printf("%s%s", i ? " | " : "", g_out[i].c_str());
  if (g_out.empty()) printf("(nothing)");
  if (!ok) {
    printf("   EXPECTED ");
    for (size_t i = 0; i < want.size(); i++) printf("%s%s", i ? " | " : "", want[i].c_str());
    if (want.empty()) printf("(nothing)");
    fails++;
  }
  printf("\n");
}


// --- helpers for the motion-limiter checks -------------------------------------
// The arm only ramps while the laptop is talking to it: with no C frames the 300 ms
// watchdog drops it into HOLD and the ramp freezes. arm/control.py sends the latest
// target at a fixed 30 Hz, so these tests do the same.
static std::string g_hb;                       // heartbeat line, "" = laptop silent
static void hb(const std::string &line) { g_hb = line; }

static void step1ms() {
  g_millis++;
  if (!g_hb.empty() && (g_millis % 33) == 0) { g_in = g_hb + "\n"; g_in_pos = 0; }
  loop();
  g_out.clear();
}
static void run_ms(uint32_t ms) { for (uint32_t i = 0; i < ms; i++) step1ms(); }

static void feed(const std::string &line) {    // send one line, ignore the reply
  g_out.clear(); g_in = line + "\n"; g_in_pos = 0; loop(); g_out.clear();
}
static bool allOff() {
  for (int j = 0; j < 5; j++) if (!g_pwm_off[j]) return false;
  return true;
}
static void chk(const char *label, bool ok) {
  checks++; if (!ok) fails++;
  printf("%-4s %s\n", ok ? "PASS" : "FAIL", label);
}

int main() {
  printf("=== boot, PCA9685 present ===\n");
  g_pca_present = true; g_millis = 1000;
  setup();
  checks++;
  std::string banner = cs("R,0,fw0.2,DISARMED");
  bool ok = (g_out.size() == 1 && g_out[0] == banner);
  printf("%-4s banner -> %s   (same vector, version field now 0.2)\n",
         ok ? "PASS" : "FAIL", g_out.empty() ? "(nothing)" : g_out[0].c_str());
  if (!ok) fails++;

  printf("\n=== PROTOCOL.md section 2 test lines ===\n");
  expect("t", "C,1,1500,1500,1500,1500,1500*76", {"E,1,4"});   // not armed yet
  expect("t", "A,3*5E", {"K,3,ARMED"});
  expect("t", "C,1,1500,1500,1500,1500,1500*76", {"K,1,ARMED"});
  expect("t", "C,2,1100,1620,1480,1500,2000*7F", {"K,2,ARMED"});
  expect("t", "H,5*51", {"K,5,ARMED"});
  expect("t", cs("P,6"), {"K,6,ARMED"});
  expect("t", "D,4*5C", {"K,4,DISARMED"});

  printf("\n=== error paths (brief steps 3-4) ===\n");
  expect("t", "C,1,1500,1500,1500,1500,1501*76", {"E,1,1"});   // digit changed, checksum stale
  expect("t", cs("C,9,1500,1500,1500,1500,1500"), {"E,9,4"});   // C while DISARMED
  g_out.clear(); g_in = "A,3*5E\n"; g_in_pos = 0; loop(); drain();
  expect("t", cs("C,7,2501,1500,1500,1500,1500"), {"E,7,3"});  // just over J0 ceiling
  expect("t", cs("C,8,349,1500,1500,1500,1500"),  {"E,8,3"});  // just under J0 floor
  expect("t", cs("C,10,1500,1500,1500,1500"),     {"E,10,2"}); // wrong field count
  expect("t", cs("C,11,15x0,1500,1500,1500,1500"),{"E,11,2"}); // non-numeric
  expect("t", cs("Z,12"),                         {"E,12,5"}); // unknown type
  expect("t", cs("C,16,450,1500,1500,1500,2500"),  {"K,16,ARMED"}); // both ends legal everywhere
  expect("t", cs("C,17,1500,1500,1500,1500,2501"), {"E,17,3"});    // 2501 over the ceiling on J4
  expect("t", cs("C,18,1500,1500,1500,449,1500"),  {"E,18,3"});    // 449 under the floor on J3

  expect("t", cs("A,13"),                         {"E,13,7"}); // A while already ARMED
  expect("t", "C,14,1500,1500,1500,1500,1500",    {"E,14,2"}); // no checksum at all
  expect("t", cs("C,15,1500,1500,1500,1500,1500") + "EXTRA_PADDING_TO_EXCEED_SIXTY_FOUR_CHARACTERS_TOTAL",
         {"E,0,2"});                                            // line > 64 chars

  printf("\n=== watchdog (brief step 5) ===\n");
  g_out.clear(); g_in = cs("C,20,1500,1500,1500,1500,1500") + "\n"; g_in_pos = 0; loop(); drain();
  g_millis += 299; g_out.clear(); loop();
  checks++;
  if (g_out.empty()) printf("PASS 299 ms after last C -> still ARMED, nothing sent\n");
  else { printf("FAIL 299 ms -> %s\n", g_out[0].c_str()); fails++; }
  g_millis += 2; g_out.clear(); loop();
  checks++;
  if (g_out.size() == 1 && g_out[0] == cs("E,0,6"))
    printf("PASS 301 ms after last C -> %s, state now HOLD\n", g_out[0].c_str());
  else { printf("FAIL 301 ms -> %s\n", g_out.empty() ? "(nothing)" : g_out[0].c_str()); fails++; }
  g_millis += 5000; g_out.clear(); loop();
  checks++;
  if (g_out.empty()) printf("PASS error 6 is sent once, not repeatedly\n");
  else { printf("FAIL error 6 repeated -> %s\n", g_out[0].c_str()); fails++; }
  expect("t", cs("C,21,1500,1500,1500,1500,1500"), {"K,21,ARMED"});  // valid C leaves HOLD

  printf("\n=== boot, PCA9685 missing ===\n");
  g_pca_present = false; g_out.clear(); g_millis = 2000;
  setup();
  checks++;
  ok = (g_out.size() == 2 && g_out[0] == cs("R,0,fw0.2,FAULT") && g_out[1] == cs("E,0,8"));
  printf("%-4s boot with no PCA9685 -> ", ok ? "PASS" : "FAIL");
  for (size_t i = 0; i < g_out.size(); i++) printf("%s%s", i ? " | " : "", g_out[i].c_str());
  printf("\n");
  if (!ok) fails++;
  expect("t", cs("A,30"), {"E,30,7"});   // cannot arm out of FAULT


  // ===================================================== motion limiter (Nov 15 task)
  printf("\n=== first C declares where the arm is; it does not sweep to it ===\n");
  g_pca_present = true; g_millis = 10000; g_out.clear(); setup(); drain();
  feed(cs("A,1"));
  chk("arming leaves every channel off", allOff());
  feed(cs("C,2,1500,1500,1500,1500,1500"));
  chk("first C puts the pose on the pins at once", g_pwm[0]==1500 && g_pwm[4]==1500);
  chk("...and nothing is limp any more", !g_pwm_off[0]);
  hb(cs("C,2,1500,1500,1500,1500,1500"));
  run_ms(1000);
  chk("1 s of heartbeat later, still exactly there (target reached)",
      g_pwm[0]==1500 && g_pwm[4]==1500);

  printf("\n=== a 1000 us jump on j0 is ramped at 45 deg/s ===\n");
  hb(cs("C,3,2500,1500,1500,1500,1500"));
  feed(cs("C,3,2500,1500,1500,1500,1500"));
  chk("the frame itself moves at most one step", g_pwm[0] <= 1511);
  {
    uint16_t prev = g_pwm[0], worst = 0; uint32_t t0 = g_millis, arrived = 0;
    for (int i = 0; i < 4000 && !arrived; i++) {
      step1ms();
      uint16_t d = (g_pwm[0] > prev) ? (uint16_t)(g_pwm[0]-prev) : 0; prev = g_pwm[0];
      if (d > worst) worst = d;
      if (g_pwm[0] == 2500) arrived = g_millis - t0;
    }
    printf("      worst single step %u us; 1000 us covered in %lu ms = %.1f deg/s\n",
           worst, (unsigned long)arrived, arrived ? (1000.0/11.3889)*1000.0/arrived : 0.0);
    chk("no single tick moves j0 more than 11 us", worst <= 11);
    chk("takes ~1960 ms (1000 us at 512.5 us/s)", arrived >= 1950 && arrived <= 2000);
  }

  printf("\n=== j3 wrist is capped at 90 deg/s, exactly twice j0-j2 ===\n");
  hb(cs("C,4,2500,1500,1500,2500,1500"));
  feed(cs("C,4,2500,1500,1500,2500,1500"));
  {
    uint16_t prev = g_pwm[3], worst = 0; uint32_t t0 = g_millis, arrived = 0;
    for (int i = 0; i < 2000 && !arrived; i++) {
      step1ms();
      uint16_t d = (g_pwm[3] > prev) ? (uint16_t)(g_pwm[3]-prev) : 0; prev = g_pwm[3];
      if (d > worst) worst = d;
      if (g_pwm[3] == 2500) arrived = g_millis - t0;
    }
    printf("      worst single step %u us; 1000 us covered in %lu ms = %.1f deg/s\n",
           worst, (unsigned long)arrived, arrived ? (1000.0/11.3889)*1000.0/arrived : 0.0);
    chk("no single tick moves j3 more than 21 us", worst <= 21);
    chk("takes ~980 ms, half of j0's 1960", arrived >= 970 && arrived <= 1010);
  }

  printf("\n=== full 450-2500 sweep, all five joints at once, heartbeat running ===\n");
  g_millis = 50000; g_out.clear(); setup(); drain(); hb("");
  feed(cs("A,5")); feed(cs("C,6,450,450,450,450,450"));
  hb(cs("C,7,2500,2500,2500,2500,2500"));
  feed(cs("C,7,2500,2500,2500,2500,2500"));
  {
    uint16_t prev[5], worst[5] = {0,0,0,0,0}; uint32_t arr[5] = {0,0,0,0,0}, t0 = g_millis;
    for (int j = 0; j < 5; j++) prev[j] = g_pwm[j];
    for (int i = 0; i < 6000; i++) {
      step1ms();
      for (int j = 0; j < 5; j++) {
        uint16_t d = (g_pwm[j] > prev[j]) ? (uint16_t)(g_pwm[j]-prev[j]) : 0; prev[j] = g_pwm[j];
        if (d > worst[j]) worst[j] = d;
        if (!arr[j] && g_pwm[j] == 2500) arr[j] = g_millis - t0;
      }
    }
    const char *nm[5] = {"j0 base","j1 shldr","j2 elbow","j3 wrist","j4 grip"};
    for (int j = 0; j < 5; j++)
      printf("      %-9s worst step %2u us, 180 deg in %4lu ms = %.1f deg/s\n",
             nm[j], worst[j], (unsigned long)arr[j], arr[j] ? 180000.0/arr[j] : 0.0);
    chk("j0-j2 sweep 180 deg in ~4000 ms (45 deg/s)",
        arr[0]>=3990 && arr[0]<=4040 && arr[1]==arr[0] && arr[2]==arr[0]);
    chk("j3-j4 sweep 180 deg in ~2000 ms (90 deg/s)",
        arr[3]>=1990 && arr[3]<=2040 && arr[4]==arr[3]);
    chk("no joint ever exceeds its cap in one tick",
        worst[0]<=11 && worst[1]<=11 && worst[2]<=11 && worst[3]<=21 && worst[4]<=21);
  }

  printf("\n=== the limiter never writes a pulse outside the hard limits ===\n");
  g_millis = 100000; g_out.clear(); setup(); drain(); hb("");
  feed(cs("A,8")); feed(cs("C,9,450,450,450,450,450"));
  hb(cs("C,10,2500,2500,2500,2500,2500"));
  feed(cs("C,10,2500,2500,2500,2500,2500"));
  {
    uint16_t lo = 9999, hi = 0;
    for (int i = 0; i < 5000; i++) {
      step1ms();
      for (int j = 0; j < 5; j++) { if (g_pwm[j] < lo) lo = g_pwm[j]; if (g_pwm[j] > hi) hi = g_pwm[j]; }
    }
    printf("      every pulse written across the sweep stayed in %u-%u us\n", lo, hi);
    chk("never below PULSE_MIN (450) nor above PULSE_MAX (2500)", lo >= 450 && hi <= 2500);
  }

  printf("\n=== the watchdog outranks the ramp: HOLD freezes it where it got to ===\n");
  g_millis = 150000; g_out.clear(); setup(); drain(); hb("");
  feed(cs("A,11")); feed(cs("C,12,450,1500,1500,1500,1500"));
  feed(cs("C,13,2500,1500,1500,1500,1500"));   // then the laptop goes silent
  run_ms(200);
  chk("ramp under way at 200 ms", g_pwm[0] > 450 && g_pwm[0] < 2500);
  run_ms(200);                                  // crosses the 300 ms watchdog -> HOLD
  {
    uint16_t frozen = g_pwm[0];
    run_ms(3000);
    printf("      froze at %u us and stayed there for 3 s\n", frozen);
    chk("HOLD stops the ramp dead", g_pwm[0] == frozen);
    chk("...and does NOT go limp", !g_pwm_off[0]);
    expect("t", cs("C,14,2500,1500,1500,1500,1500"), {"K,14,ARMED"});
    chk("the resuming frame itself moves at most one step", g_pwm[0] <= frozen + 11);
    hb(cs("C,14,2500,1500,1500,1500,1500"));
    run_ms(100);
    printf("      resumed to %u us (%u us in ~6 ticks)\n",
           g_pwm[0], (uint16_t)(g_pwm[0]-frozen));
    chk("then it creeps on from the frozen pose, no jump",
        g_pwm[0] > frozen && g_pwm[0] <= frozen + 6*11);
  }

  printf("\n=== a stalled loop makes the arm lag, never lurch ===\n");
  g_millis = 200000; g_out.clear(); setup(); drain(); hb("");
  feed(cs("A,15")); feed(cs("C,16,1500,1500,1500,1500,1500"));
  feed(cs("C,17,2500,1500,1500,1500,1500"));
  {
    uint16_t before = g_pwm[0];
    g_millis += 200; loop();        // one pass after a 200 ms block (inside the watchdog)
    printf("      200 ms stall, one pass -> moved %u us (it 'owed' 10 ticks)\n",
           (uint16_t)(g_pwm[0]-before));
    chk("one step, not the ten it owed", (uint16_t)(g_pwm[0]-before) <= 11);
  }

  printf("\n=== a rejected frame leaves the ramp heading for the OLD target ===\n");
  g_millis = 250000; g_out.clear(); setup(); drain(); hb("");
  feed(cs("A,18")); feed(cs("C,19,2000,1500,1500,1500,1500"));
  hb(cs("C,20,1500,1500,1500,1500,1500"));      // target: travel down to 1500
  feed(cs("C,20,1500,1500,1500,1500,1500"));
  run_ms(200);
  expect("t", cs("C,21,2501,1500,1500,1500,1500"), {"E,21,3"});   // over J0's ceiling
  {
    uint16_t a1 = g_pwm[0]; run_ms(200); uint16_t a2 = g_pwm[0];
    printf("      %u -> %u us\n", a1, a2);
    chk("still travelling down to 1500, not up to the rejected 2501", a2 < a1);
  }

  printf("\n=== D goes limp; re-arming re-seeds the ramp from the next C ===\n");
  hb("");
  expect("t", cs("D,22"), {"K,22,DISARMED"});
  chk("all five channels off", allOff());
  feed(cs("A,23"));
  feed(cs("C,24,2450,2450,2450,2450,2450"));
  chk("first C after re-arming lands at once, no sweep from the old pose",
      g_pwm[0]==2450 && g_pwm[4]==2450);
  hb(cs("C,24,2450,2450,2450,2450,2450"));
  run_ms(500);
  chk("and stays put", g_pwm[0]==2450);

  printf("\n%d checks, %d failures\n", checks, fails);
  return fails ? 1 : 0;
}
