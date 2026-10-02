// Laptop unit test for code/esp32/cane_safety/safety_logic.h.
//
//   g++ -std=c++17 -Wall -Wextra -I../cane_safety test_safety_logic.cpp -o t && ./t
//
// Runs the motor decisions millisecond by millisecond, the way loop() does,
// and checks the patterns the user feels. Exit code 0 = all passed.

#include <cstdio>
#include <cstdlib>
#include "safety_logic.h"

using namespace safety;

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { \
  std::printf("FAIL line %d: %s\n", __LINE__, msg); failures++; } } while (0)

// Milliseconds with duty > 0 in [from, to), and number of off->on edges.
struct Feel { int onMs; int pulses; int minDuty; int maxDuty; };

template <typename F>
Feel feel(uint32_t from, uint32_t to, F duty) {
  Feel f{0, 0, 101, -1};
  int prev = 0;
  for (uint32_t t = from; t < to; t++) {
    int d = duty(t);
    if (d > 0) f.onMs++;
    if (d > 0 && prev == 0) f.pulses++;
    if (d < f.minDuty) f.minDuty = d;
    if (d > f.maxDuty) f.maxDuty = d;
    prev = d;
  }
  return f;
}

void testObstacleBands() {
  CHECK(obstacleDuty(-1, 0) == -1, "nothing in range = no pattern");
  CHECK(obstacleDuty(FAR_MM, 0) == -1, "at FAR_MM = no pattern");
  CHECK(obstacleDuty(5000, 0) == -1, "far away = no pattern");
  Feel close = feel(0, 3000, [](uint32_t t) { return obstacleDuty(300, t); });
  CHECK(close.onMs == 3000 && close.minDuty == 100, "close = continuous 100 %");
  Feel near = feel(0, 3000, [](uint32_t t) { return obstacleDuty(600, t); });
  CHECK(near.pulses == 10 && near.onMs == 1200 && near.maxDuty == 85,
        "near = 85 %, 120 on / 180 off");
  Feel far = feel(0, 7000, [](uint32_t t) { return obstacleDuty(1200, t); });
  CHECK(far.pulses == 10 && far.onMs == 1000 && far.maxDuty == 60,
        "far = 60 %, 100 on / 600 off");
  CHECK(obstacleDuty(600, 150) == 0, "off phase is 0, not -1");
}

void testHazard() {
  uint32_t start = 10000;
  uint32_t until = start + HAZARD_LEN_MS;
  CHECK(hazardDuty(start - 1, 0) == -1, "no alarm = no pattern");
  Feel h = feel(start, until, [&](uint32_t t) { return hazardDuty(t, until); });
  CHECK(h.pulses == 3, "ground alarm = 3 pulses");
  CHECK(h.onMs >= 897 && h.onMs <= 900, "ground alarm = 3 x 300 ms on");
  CHECK(h.maxDuty == 100, "ground alarm at 100 %");
  CHECK(hazardDuty(until, until) == -1, "alarm ends");
}

void testBoot() {
  Feel b = feel(0, 1000, [](uint32_t t) { return bootDuty(t); });
  CHECK(b.pulses == 2 && b.onMs == 300, "boot = two 150 ms pulses");
  CHECK(bootDuty(400) == -1, "boot pattern ends at 400 ms");
}

// The hole found on 2 Oct 2026: the Pi sends B0,5000 while an obstacle is
// at 30 cm. Before Step 1.5 that meant 5 s of silence.
void testPiCannotSilenceObstacle() {
  Feel f = feel(0, 5000, [](uint32_t t) {
    return arbitrate(hazardDuty(t, 0), obstacleDuty(300, t), /*B0*/ 0);
  });
  CHECK(f.onMs == 5000 && f.minDuty == 100, "B0,5000 cannot silence a close obstacle");
}

void testPiCannotSilenceGroundAlarm() {
  uint32_t until = HAZARD_LEN_MS;
  Feel f = feel(0, until, [&](uint32_t t) {
    return arbitrate(hazardDuty(t, until), /*A0: obstacle muted*/ -1, /*B0*/ 0);
  });
  CHECK(f.pulses == 3, "B0 + A0 cannot silence the ground alarm");
}

// A Pi request must not fill the off phases of a safety pattern, or the near
// pattern turns into a continuous buzz and feels like "close".
void testPiCannotReshapePattern() {
  Feel f = feel(0, 3000, [](uint32_t t) {
    return arbitrate(-1, obstacleDuty(600, t), /*B100*/ 100);
  });
  CHECK(f.pulses == 10 && f.onMs == 1200, "B100 cannot fill the near pattern's gaps");
}

void testHazardBeatsObstacle() {
  CHECK(arbitrate(0, 100, 100) == 0, "hazard off phase beats close obstacle");
  CHECK(arbitrate(100, 60, -1) == 100, "hazard on phase wins");
}

void testRequestPlaysWhenQuiet() {
  CHECK(arbitrate(-1, -1, 85) == 85, "sync buzz plays when nothing else runs");
  CHECK(arbitrate(-1, -1, -1) == 0, "all quiet = motor off");
}

int main() {
  testObstacleBands();
  testHazard();
  testBoot();
  testPiCannotSilenceObstacle();
  testPiCannotSilenceGroundAlarm();
  testPiCannotReshapePattern();
  testHazardBeatsObstacle();
  testRequestPlaysWhenQuiet();
  if (failures) { std::printf("%d check(s) failed\n", failures); return 1; }
  std::printf("all safety_logic checks passed\n");
  return 0;
}
