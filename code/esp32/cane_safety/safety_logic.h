// Smart cane - motor decisions as pure functions.
//
// Kept free of Arduino calls so the same code runs on the ESP32 and in the
// laptop unit test (code/esp32/tests/test_safety_logic.cpp).
//
// Each pattern function returns the duty 0-100 it wants right now, or -1 when
// it has nothing to say. 0 and -1 are different on purpose: 0 is the off
// phase of a pattern that is still running, -1 means no pattern at all. The
// arbiter needs the difference so a Pi request cannot fill a pattern's gaps.

#pragma once
#include <stdint.h>

namespace safety {

// Forward obstacle bands, mm. Unchanged from the pre-Step-1.5 firmware.
const int CLOSE_MM = 400;
const int NEAR_MM = 800;
const int FAR_MM = 1500;

// Ground alarm: three pulses, 300 ms on / 150 ms off.
const uint32_t HAZARD_PERIOD_MS = 450;
const uint32_t HAZARD_LEN_MS = 3 * HAZARD_PERIOD_MS;

// Parking-sensor style: closer = stronger and faster, close = solid buzz.
inline int obstacleDuty(int mm, uint32_t now) {
  if (mm < 0 || mm >= FAR_MM) return -1;
  if (mm < CLOSE_MM) return 100;
  int duty, onMs, offMs;
  if (mm < NEAR_MM) { duty = 85; onMs = 120; offMs = 180; }
  else              { duty = 60; onMs = 100; offMs = 600; }
  return (now % (onMs + offMs)) < (uint32_t)onMs ? duty : 0;
}

// Same formula as before Step 1.5, counted down from hazardUntil.
inline int hazardDuty(uint32_t now, uint32_t hazardUntil) {
  if (now >= hazardUntil) return -1;
  uint32_t t = hazardUntil - now;
  return (t % HAZARD_PERIOD_MS) > 150 ? 100 : 0;
}

// "I am alive" at boot: 150 on, 100 off, 150 on. Used to be a blocking
// delay() in setup() that held the safety loop off for about 400 ms.
inline int bootDuty(uint32_t sinceBoot) {
  if (sinceBoot < 150) return 100;
  if (sinceBoot < 250) return 0;
  if (sinceBoot < 400) return 100;
  return -1;
}

// The ESP32's own safety patterns always win. While a ground alarm or an
// obstacle pattern runs, a buzz requested by the Pi is ignored, including in
// the pattern's off phases, so the pattern keeps the shape the user learned.
// Before Step 1.5 any Pi request overrode both, and B0,5000 meant 5 s of
// silence. Requests (sync buzz, boot pulses) play only when the ESP32 has
// nothing to say.
inline int arbitrate(int hazard, int obstacle, int request) {
  if (hazard >= 0) return hazard;
  if (obstacle >= 0) return obstacle;
  if (request >= 0) return request;
  return 0;
}

}  // namespace safety
