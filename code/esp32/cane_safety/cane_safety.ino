// Smart cane - safety co-processor (ESP32 DevKit V1).
//
// Owns the reflexes: two VL53L0X ToF sensors and the vibration motor. It buzzes
// on its own, without the Pi, so obstacle alerts work ~1 s after power-on and
// keep working if the Pi software crashes (MEMORY.md section 4.1). The Pi only
// listens over USB serial and adds speech on top.
//
// Wiring:
//   ToF 1   VCC 3V3, GND, SDA D21, SCL D22, XSHUT D26   (I2C bus 0, Wire)
//   ToF 2   VCC 3V3, GND, SDA D18, SCL D19, XSHUT D27   (I2C bus 1, Wire1)
//   Motor   IN D13, VCC VIN (5V), GND
//
// Each sensor has its own I2C bus, so both stay at the default address 0x29
// and no readdressing is needed. XSHUT is used only to hard-reset a sensor
// that stops answering.
//
// Roles. One sensor looks FORWARD (obstacles), the other looks DOWN at the
// ground ahead of the tip (holes, drains, steps). Which physical sensor does
// which is set by the mount, so it is a serial command saved in flash, not a
// constant: R1 = ToF 1 forward / ToF 2 down (default), R2 = the reverse.
//
// Serial protocol, 115200 baud, one line per message:
//   ESP32 -> Pi   I <text>                          info / boot report
//                 D <ms> <fwd> <down> <fok> <dok> <base>
//                   fwd/down in mm, -1 = nothing in range; base = learned
//                   ground distance in mm, -1 = not learned yet
//                 H drop <mm> <base>                ground fell away: hole, drain, step down
//                 H step <mm> <base>                ground came up: kerb, step up, low object
//                 E <text>                          error
//   Pi -> ESP32   A0 / A1                           auto vibration off / on
//                 B<duty>,<ms>                      one buzz, duty 0-100 %
//                 R1 / R2                           sensor roles, saved
//                 S                                 status report (incl. motor duty)

#include <algorithm>
#include <Wire.h>
#include <VL53L0X.h>
#include <Preferences.h>

const int PIN_SDA1 = 21, PIN_SCL1 = 22, PIN_XSHUT1 = 26;
const int PIN_SDA2 = 18, PIN_SCL2 = 19, PIN_XSHUT2 = 27;
const int PIN_MOTOR = 13;

const int PWM_HZ = 200;            // inaudible, coin motors respond well here
const int PWM_BITS = 8;

// Forward obstacle bands, in mm. The forward sensor runs in long-range mode
// (about 2 m indoors, much less in direct sun), the down sensor in default
// mode (about 1.2 m, more precise), since the ground is always close.
const int CLOSE_MM = 400;          // nearer than this: solid buzz
const int FAR_MM = 1500;           // further than this: no obstacle buzz

// Ground watching. The down sensor learns how far away the ground normally is
// and alarms on a sudden change. Thresholds are a first guess for a cane held
// at a normal angle and must be tuned on a real pavement.
const int DROP_MM = 150;           // ground this much further away = drop
const int STEP_MM = 120;           // ground this much closer = step up
const int CONFIRM_READS = 2;       // on top of the median-of-3, so ~4 raw
                                   // readings (~130 ms) reject one-off noise
const uint32_t RELEARN_MS = 2000;  // a "change" that lasts this long is the
                                   // new normal (grip changed), not a hole
const uint32_t HAZARD_HOLDOFF_MS = 2500;
const int HAZARD_PULSES = 2;       // ground alarm: 2 long hard pulses (Adeel, 3 Oct)
const float BASE_ALPHA = 0.05;     // how fast the baseline follows slow drift

const uint32_t STALE_MS = 300;     // no new reading for this long = sensor dead
const uint32_t REPORT_MS = 50;     // 20 Hz to the Pi

struct Tof {
  VL53L0X dev;
  TwoWire *bus;
  int sda, scl, xshut;
  bool ok = false;
  bool fresh = false;              // a new reading since last looked at
  int mm = -1;                     // filtered: median of the last 3 readings
  int raw[3] = {-1, -1, -1};
  int rawIdx = 0;
  uint32_t lastReadMs = 0;
  uint32_t reinits = 0;
};

Tof tof[2];
int FWD = 0, DOWN = 1;             // indexes into tof[], set by R1/R2
bool autoBuzz = true;
Preferences prefs;

// ---- ground model ---------------------------------------------------------

float baseline = -1;               // learned ground distance, mm
int learnBuf[10];
int learnCount = 0;
int dropStreak = 0, stepStreak = 0;
uint32_t offBandSince = 0;
uint32_t lastHazardMs = 0;

// ---- motor ---------------------------------------------------------------

uint32_t manualUntil = 0;   // a manual buzz from the Pi overrides auto
uint32_t hazardUntil = 0;   // the ground alarm overrides obstacle buzzing

int motorDuty = 0;                 // last duty written, reported by S

void motor(int dutyPct) {
  motorDuty = dutyPct;
  ledcWrite(PIN_MOTOR, (dutyPct * 255) / 100);
}

// Obstacle feel is parking-sensor style, from the forward sensor (ToF 1) only:
// the nearer, the stronger and faster, on a smooth scale from FAR_MM (60 %
// duty, 100 ms on / 600 ms off) to CLOSE_MM, then a solid buzz. It was three
// fixed steps until 3 Oct 2026. The ground alarm is deliberately different,
// two long hard pulses, so a hole never feels like "something in front of you".
void updateMotor(uint32_t now) {
  if (now < manualUntil) return;
  if (now < hazardUntil) {
    uint32_t t = (hazardUntil - now);
    motor((t % 450) > 150 ? 100 : 0);   // 300 on / 150 off
    return;
  }
  Tof &f = tof[FWD];
  int mm = (f.ok && f.mm >= 0) ? f.mm : -1;
  if (!autoBuzz || mm < 0 || mm >= FAR_MM) { motor(0); return; }
  if (mm < CLOSE_MM) { motor(100); return; }

  float c = float(FAR_MM - mm) / (FAR_MM - CLOSE_MM);   // 0 far .. 1 close
  int duty = 60 + int(40 * c);
  int onMs = 100;
  int offMs = 60 + int(540 * (1 - c));
  motor((now % (onMs + offMs)) < (uint32_t)onMs ? duty : 0);
}

void buzzBlocking(int duty, int ms) {
  motor(duty); delay(ms); motor(0);
}

void hazard(const char *kind, int mm, uint32_t now) {
  if (now - lastHazardMs < HAZARD_HOLDOFF_MS) return;
  lastHazardMs = now;
  if (autoBuzz) hazardUntil = now + HAZARD_PULSES * 450;
  Serial.printf("H %s %d %d\n", kind, mm, (int)baseline);
}

// Called once per fresh down reading.
void watchGround(int mm, uint32_t now) {
  if (baseline < 0) {
    // Learn from the median of the first 10 real readings, so one stray value
    // at power-on cannot poison the baseline.
    if (mm < 0) return;
    learnBuf[learnCount++] = mm;
    if (learnCount == 10) {
      std::sort(learnBuf, learnBuf + 10);
      baseline = (learnBuf[4] + learnBuf[5]) / 2.0;
      learnCount = 0;
      Serial.printf("I ground learned %d mm\n", (int)baseline);
    }
    return;
  }

  // Nothing in range while the ground was in range means the ground fell away
  // further than the sensor can see. That is the most dangerous case of all.
  bool drop = (mm < 0) || (mm > baseline + DROP_MM);
  bool step = (mm >= 0) && (mm < baseline - STEP_MM);

  dropStreak = drop ? dropStreak + 1 : 0;
  stepStreak = step ? stepStreak + 1 : 0;
  if (dropStreak == CONFIRM_READS) hazard("drop", mm, now);
  if (stepStreak == CONFIRM_READS) hazard("step", mm, now);

  if (drop || step) {
    if (!offBandSince) offBandSince = now;
    if (now - offBandSince > RELEARN_MS) {
      // Lasted too long to be a hole the user is about to step into. The cane
      // angle changed, so start learning the ground again.
      baseline = -1; learnCount = 0; offBandSince = 0;
      dropStreak = stepStreak = 0;
      Serial.println("I ground changed for 2 s, relearning");
    }
  } else {
    offBandSince = 0;
    baseline += BASE_ALPHA * (mm - baseline);   // follow slow drift only
  }
}

// ---- sensors -------------------------------------------------------------

// Median of 3 with "nothing in range" (-1) counted as a vote. One bad reading,
// a flash of sunlight or a stray reflection, can no longer move the number or
// trigger a buzz. Costs one reading of latency (~33-50 ms).
int median3(const int *r) {
  int a = r[0], b = r[1], c = r[2];
  int none = (a < 0) + (b < 0) + (c < 0);
  if (none >= 2) return -1;
  if (none == 1) {                 // two real values: take the nearer, safer
    if (a < 0) return min(b, c);
    if (b < 0) return min(a, c);
    return min(a, b);
  }
  return max(min(a, b), min(max(a, b), c));
}

bool startTof(Tof &t, int idx) {
  digitalWrite(t.xshut, LOW);
  delay(10);
  digitalWrite(t.xshut, HIGH);
  delay(10);                       // datasheet boot time is 1.2 ms

  t.dev.setBus(t.bus);
  t.dev.setTimeout(100);
  if (!t.dev.init()) {
    Serial.printf("E tof%d init failed (no reply at 0x29 on SDA %d / SCL %d)\n",
                  idx + 1, t.sda, t.scl);
    t.ok = false;
    return false;
  }
  if (idx == FWD) {
    // Long-range mode, per the VL53L0X datasheet / Pololu example: lower the
    // return-signal limit and lengthen the laser pulses. About 2 m instead of
    // 1.2 m, at the cost of more noise, which the median filter absorbs.
    t.dev.setSignalRateLimit(0.1);
    t.dev.setVcselPulsePeriod(VL53L0X::VcselPeriodPreRange, 18);
    t.dev.setVcselPulsePeriod(VL53L0X::VcselPeriodFinalRange, 14);
  }
  t.dev.setMeasurementTimingBudget(33000);
  t.dev.startContinuous();
  t.raw[0] = t.raw[1] = t.raw[2] = -1;
  t.rawIdx = 0;
  t.mm = -1;
  t.ok = true;
  t.lastReadMs = millis();
  return true;
}

void scanBus(TwoWire *bus, int idx) {
  Serial.printf("I bus%d scan:", idx + 1);
  int found = 0;
  for (uint8_t a = 1; a < 127; a++) {
    bus->beginTransmission(a);
    if (bus->endTransmission() == 0) { Serial.printf(" 0x%02x", a); found++; }
  }
  Serial.println(found ? "" : " (nothing)");
}

// Non-blocking: only read when the sensor says a result is ready.
void pollTof(Tof &t, int idx, uint32_t now) {
  if (!t.ok) return;
  uint8_t status = t.dev.readReg(VL53L0X::RESULT_INTERRUPT_STATUS);
  if (t.dev.last_status == 0 && (status & 0x07)) {
    uint16_t r = t.dev.readRangeContinuousMillimeters();
    if (!t.dev.timeoutOccurred() && t.dev.last_status == 0) {
      t.raw[t.rawIdx] = (r >= 8000) ? -1 : r;   // 8190/8191 = nothing in range
      t.rawIdx = (t.rawIdx + 1) % 3;
      t.mm = median3(t.raw);
      t.lastReadMs = now;
      t.fresh = true;
    }
  }
  if (now - t.lastReadMs > STALE_MS) {
    // A sensor that silently stops reporting is the dangerous failure: the
    // cane looks healthy and the user gets nothing. Reset it hard.
    t.ok = false;
    t.mm = -1;
    t.reinits++;
    Serial.printf("E tof%d stopped answering, reinit #%u\n", idx + 1, t.reinits);
  }
}

// ---- serial commands -----------------------------------------------------

String line;

void setRoles(int fwd) {
  FWD = fwd; DOWN = 1 - fwd;
  baseline = -1; learnCount = 0;   // the down sensor changed, relearn
  Serial.printf("I roles: forward=tof%d down=tof%d\n", FWD + 1, DOWN + 1);
}

void handleCommand(const String &cmd) {
  if (cmd == "A0") { autoBuzz = false; motor(0); Serial.println("I auto off"); }
  else if (cmd == "A1") { autoBuzz = true; Serial.println("I auto on"); }
  else if (cmd == "R1" || cmd == "R2") {
    setRoles(cmd == "R1" ? 0 : 1);
    prefs.putUChar("fwd", FWD);
    // Long-range mode belongs to whichever sensor is now forward.
    for (int i = 0; i < 2; i++) startTof(tof[i], i);
  } else if (cmd == "S") {
    for (int i = 0; i < 2; i++)
      Serial.printf("I tof%d %s ok=%d mm=%d reinits=%u\n", i + 1,
                    i == FWD ? "forward" : "down", tof[i].ok, tof[i].mm,
                    tof[i].reinits);
    Serial.printf("I auto=%d ground=%d motor=%d\n", autoBuzz, (int)baseline, motorDuty);
  } else if (cmd == "T") {
    // Wiring test. A sensor can ACK its address (power and the bus are
    // there) yet return garbage data (a marginal SDA/SCL contact). The ID
    // registers tell the two apart: a healthy VL53L0X reads EE AA 10.
    for (int i = 0; i < 2; i++) {
      scanBus(tof[i].bus, i);
      uint8_t id[3];
      bool ok = true;
      for (int k = 0; k < 3; k++) {
        tof[i].bus->beginTransmission(0x29);
        tof[i].bus->write(0xC0 + k);
        if (tof[i].bus->endTransmission(false) != 0 ||
            tof[i].bus->requestFrom(0x29, 1) != 1) { ok = false; break; }
        id[k] = tof[i].bus->read();
      }
      if (ok) Serial.printf("I tof%d id %02X %02X %02X (expect EE AA 10)\n",
                            i + 1, id[0], id[1], id[2]);
      else    Serial.printf("E tof%d id read failed\n", i + 1);
    }
  } else if (cmd.startsWith("B")) {
    int comma = cmd.indexOf(',');
    int duty = constrain(cmd.substring(1, comma).toInt(), 0, 100);
    int ms = comma > 0 ? constrain(cmd.substring(comma + 1).toInt(), 0, 5000) : 300;
    manualUntil = millis() + ms;
    motor(duty);
    Serial.printf("I buzz %d%% %dms\n", duty, ms);
  } else if (cmd.length()) {
    Serial.printf("E unknown command '%s'\n", cmd.c_str());
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { handleCommand(line); line = ""; }
    else if (line.length() < 32) line += c;
  }
}

// ---- main ----------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  ledcAttach(PIN_MOTOR, PWM_HZ, PWM_BITS);
  motor(0);

  prefs.begin("cane", false);
  setRoles(prefs.getUChar("fwd", 0));

  tof[0].bus = &Wire;  tof[0].sda = PIN_SDA1; tof[0].scl = PIN_SCL1; tof[0].xshut = PIN_XSHUT1;
  tof[1].bus = &Wire1; tof[1].sda = PIN_SDA2; tof[1].scl = PIN_SCL2; tof[1].xshut = PIN_XSHUT2;
  for (auto &t : tof) { pinMode(t.xshut, OUTPUT); digitalWrite(t.xshut, LOW); }

  Wire.begin(PIN_SDA1, PIN_SCL1, 400000);
  Wire1.begin(PIN_SDA2, PIN_SCL2, 400000);
  delay(10);
  Serial.println("I cane_safety boot");

  for (int i = 0; i < 2; i++) {
    digitalWrite(tof[i].xshut, HIGH);
    delay(10);
    scanBus(tof[i].bus, i);
    startTof(tof[i], i);
  }
  Serial.printf("I ready tof1=%d tof2=%d\n", tof[0].ok, tof[1].ok);

  // "I am alive" for the user: two short pulses.
  buzzBlocking(100, 150); delay(100); buzzBlocking(100, 150);
}

void loop() {
  static uint32_t lastReport = 0, lastRetry = 0;
  uint32_t now = millis();

  readSerial();
  for (int i = 0; i < 2; i++) pollTof(tof[i], i, now);

  if (tof[DOWN].fresh) {
    tof[DOWN].fresh = false;
    if (tof[DOWN].ok) watchGround(tof[DOWN].mm, now);
  }
  tof[FWD].fresh = false;

  if (now - lastRetry > 1000) {
    lastRetry = now;
    for (int i = 0; i < 2; i++) if (!tof[i].ok) startTof(tof[i], i);
  }

  updateMotor(now);

  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    Serial.printf("D %lu %d %d %d %d %d\n", (unsigned long)now,
                  tof[FWD].mm, tof[DOWN].mm, tof[FWD].ok, tof[DOWN].ok,
                  (int)baseline);
  }
}
