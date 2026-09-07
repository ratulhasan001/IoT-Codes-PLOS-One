#include <Wire.h>
#include <Adafruit_BMP085.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "sha256_lite.h"
#include <avr/wdt.h>
#include <avr/interrupt.h>

#define BAUD_RATE       500000

#define ENABLE_OLED     1

#define NUM_ANALOG_SRC  6
#define NUM_SOURCES     7
#define IDX_JITTER      6

const uint8_t ANALOG_PINS[NUM_ANALOG_SRC] = { A0, A1, A2, A3, A6, A7 };
const char *SRC_NAMES[NUM_SOURCES] = {
  "ACC_X", "ACC_Y", "ACC_Z", "LIGHT", "SOUND", "HALL", "JITTER"
};

#define ANALOG_PER_BLOCK   256
#define JITTER_BITS_BLOCK   64
#define RESTART_SAMPLES   1000

#define APT_WINDOW 1024

const uint16_t RCT_CUTOFF[NUM_SOURCES] = { 41, 41, 41, 41, 41, 41, 21 };
const uint16_t APT_CUTOFF[NUM_SOURCES] = { 793, 793, 793, 793, 793, 793, 589 };

const uint16_t H_MILLIBITS[NUM_SOURCES] = { 500, 500, 500, 500, 500, 500, 1000 };

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

Adafruit_BMP085 bmp;
bool bmp_ok = false;
SHA256Lite sha256;

struct HealthState {
  uint8_t  rct_prev;
  uint16_t rct_run;
  uint16_t rct_max;
  uint8_t  apt_ref;
  uint16_t apt_seen;
  uint16_t apt_matches;
  uint16_t apt_max_matches;
  bool     failed;
  uint16_t rct_failures;
  uint16_t apt_failures;
  uint32_t samples;
  uint32_t ones;
  bool     initialised;
};

HealthState health[NUM_SOURCES];

void resetHealth() {
  for (uint8_t s = 0; s < NUM_SOURCES; s++) {
    health[s].rct_prev        = 0;
    health[s].rct_run         = 0;
    health[s].rct_max         = 0;
    health[s].apt_ref         = 0;
    health[s].apt_seen        = 0;
    health[s].apt_matches     = 0;
    health[s].apt_max_matches = 0;
    health[s].failed          = false;
    health[s].rct_failures    = 0;
    health[s].apt_failures    = 0;
    health[s].samples         = 0;
    health[s].ones            = 0;
    health[s].initialised     = false;
  }
}

void healthUpdate(uint8_t src, uint8_t bit) {
  HealthState &h = health[src];
  h.samples++;
  h.ones += bit;

  if (!h.initialised) {
    h.rct_prev    = bit;
    h.rct_run     = 1;
    h.apt_ref     = bit;
    h.apt_seen    = 1;
    h.apt_matches = 1;
    h.initialised = true;
    return;
  }

  if (bit == h.rct_prev) {
    h.rct_run++;
    if (h.rct_run > h.rct_max) h.rct_max = h.rct_run;
    if (h.rct_run >= RCT_CUTOFF[src]) {
      h.failed = true;
      h.rct_failures++;
      h.rct_run = 1;
    }
  } else {
    h.rct_prev = bit;
    h.rct_run  = 1;
  }

  if (h.apt_seen >= APT_WINDOW) {

    if (h.apt_matches > h.apt_max_matches) h.apt_max_matches = h.apt_matches;
    if (h.apt_matches >= APT_CUTOFF[src]) {
      h.failed = true;
      h.apt_failures++;
    }

    h.apt_ref     = bit;
    h.apt_seen    = 1;
    h.apt_matches = 1;
  } else {
    h.apt_seen++;
    if (bit == h.apt_ref) h.apt_matches++;
  }
}

bool anySourceFailed() {
  for (uint8_t s = 0; s < NUM_SOURCES; s++) if (health[s].failed) return true;
  return false;
}

volatile uint8_t  jitter_raw_ready = 0;
volatile uint16_t jitter_raw_value = 0;

ISR(WDT_vect) {
  jitter_raw_value = TCNT1;
  jitter_raw_ready = 1;
}

void jitterBegin() {
  cli();
  TCCR1A = 0;
  TCCR1B = (1 << CS10);
  TCNT1  = 0;
  MCUSR &= ~(1 << WDRF);
  WDTCSR |= (1 << WDCE) | (1 << WDE);
  WDTCSR  = (1 << WDIE);
  sei();
}

void jitterEnd() {
  cli();
  MCUSR &= ~(1 << WDRF);
  WDTCSR |= (1 << WDCE) | (1 << WDE);
  WDTCSR  = 0x00;
  sei();
}

uint16_t jitterNextRaw() {
  while (!jitter_raw_ready) {  }
  cli();
  uint16_t v = jitter_raw_value;
  jitter_raw_ready = 0;
  sei();
  return v;
}

uint8_t jitterNextDebiasedBit() {
  while (true) {
    uint8_t a = (uint8_t)(jitterNextRaw() & 0x01);
    healthUpdate(IDX_JITTER, a);
    uint8_t b = (uint8_t)(jitterNextRaw() & 0x01);
    healthUpdate(IDX_JITTER, b);
    if (a != b) return a;
  }
}

uint16_t readAnalogSettled(uint8_t pin) {
  (void)analogRead(pin);
  return (uint16_t)analogRead(pin);
}

uint16_t crc16(const char *data, uint16_t len) {
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < len; i++) {
    crc ^= (uint16_t)data[i] << 8;
    for (uint8_t b = 0; b < 8; b++)
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
  }
  return crc;
}

char linebuf[320];

void emitLine(const char *s) {
  uint16_t c = crc16(s, strlen(s));
  Serial.print(s);
  Serial.print("*");
  if (c < 0x1000) Serial.print("0");
  if (c < 0x0100) Serial.print("0");
  if (c < 0x0010) Serial.print("0");
  Serial.println(c, HEX);
}

enum Mode { MODE_SEED, MODE_RAW_ANALOG, MODE_RAW_JITTER, MODE_RESTART, MODE_HALT };
Mode mode = MODE_SEED;

void checkCommand() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case 'S': mode = MODE_SEED;       jitterBegin(); break;
    case 'R': mode = MODE_RAW_ANALOG; jitterEnd();   break;
    case 'J': mode = MODE_RAW_JITTER; jitterBegin(); break;
    case 'B': mode = MODE_RESTART;    jitterEnd();   break;
    case 'H': dumpHealth();                          break;
    case 'Z': resetHealth();  emitLine("EVT,HEALTH_RESET"); break;
    default:  break;
  }
}

void dumpHealth() {
  for (uint8_t s = 0; s < NUM_SOURCES; s++) {
    HealthState &h = health[s];
    snprintf(linebuf, sizeof(linebuf),
      "HEALTH,%s,state=%s,n=%lu,ones=%lu,rct_max=%u,rct_fail=%u,"
      "apt_max=%u,apt_fail=%u,rct_C=%u,apt_C=%u",
      SRC_NAMES[s], h.failed ? "FAIL" : "OK",
      (unsigned long)h.samples, (unsigned long)h.ones,
      h.rct_max, h.rct_failures, h.apt_max_matches, h.apt_failures,
      RCT_CUTOFF[s], APT_CUTOFF[s]);
    emitLine(linebuf);
  }
}

void setup() {
  Serial.begin(BAUD_RATE);
  analogReference(DEFAULT);
  resetHealth();

#if ENABLE_OLED
  if (display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println(F("Entropy source boot"));
    display.display();
  }
#endif

  bmp_ok = bmp.begin();

  jitterBegin();

  emitLine("EVT,BOOT,fw=entropy_source_v2");
  snprintf(linebuf, sizeof(linebuf),
    "EVT,CONFIG,sources=%d,analog_per_block=%d,jitter_bits=%d,"
    "apt_window=%d,bmp180=%s",
    NUM_SOURCES, ANALOG_PER_BLOCK, JITTER_BITS_BLOCK, APT_WINDOW,
    bmp_ok ? "context_only" : "absent");
  emitLine(linebuf);
}

void runSeedMode() {
  sha256.reset();

  uint32_t sum[NUM_ANALOG_SRC];
  uint32_t sumsq[NUM_ANALOG_SRC];
  for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) { sum[s] = 0; sumsq[s] = 0; }

  for (uint16_t i = 0; i < ANALOG_PER_BLOCK; i++) {
    for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) {
      uint16_t v = readAnalogSettled(ANALOG_PINS[s]);
      healthUpdate(s, (uint8_t)(v & 0x01));
      sha256.update(&v, sizeof(v));
      sum[s]   += v;
      sumsq[s] += (uint32_t)v * v;
    }
  }

  uint8_t  jbyte = 0;
  uint8_t  jbits = 0;
  for (uint16_t i = 0; i < JITTER_BITS_BLOCK; i++) {
    jbyte = (jbyte << 1) | jitterNextDebiasedBit();
    if (++jbits == 8) { sha256.update(&jbyte, 1); jbyte = 0; jbits = 0; }
  }

  float temp = 0; int32_t pressure = 0;
  if (bmp_ok) {
    temp = bmp.readTemperature();
    pressure = bmp.readPressure();
    sha256.update(&temp, sizeof(temp));
    sha256.update(&pressure, sizeof(pressure));
  }

  byte seed[32];
  sha256.finalize(seed, 32);

  uint32_t budget_mb = 0;
  for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++)
    if (!health[s].failed) budget_mb += (uint32_t)H_MILLIBITS[s] * ANALOG_PER_BLOCK;
  if (!health[IDX_JITTER].failed)
    budget_mb += (uint32_t)H_MILLIBITS[IDX_JITTER] * JITTER_BITS_BLOCK;
  uint32_t budget_bits = budget_mb / 1000;

  char failed_list[80] = "";
  for (uint8_t s = 0; s < NUM_SOURCES; s++) {
    if (health[s].failed) {
      if (failed_list[0]) strncat(failed_list, "+", sizeof(failed_list) - strlen(failed_list) - 1);
      strncat(failed_list, SRC_NAMES[s], sizeof(failed_list) - strlen(failed_list) - 1);
    }
  }
  if (!failed_list[0]) strcpy(failed_list, "none");

  int n = snprintf(linebuf, sizeof(linebuf),
    "SEED,health=%s,failed=%s,budget_bits=%lu,seed=",
    anySourceFailed() ? "FAIL" : "OK", failed_list,
    (unsigned long)budget_bits);
  for (uint8_t i = 0; i < 32 && n < (int)sizeof(linebuf) - 3; i++)
    n += snprintf(linebuf + n, sizeof(linebuf) - n, "%02X", seed[i]);
  emitLine(linebuf);

  for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) {
    uint32_t mean = sum[s] / ANALOG_PER_BLOCK;
    uint32_t var  = (sumsq[s] / ANALOG_PER_BLOCK) - (mean * mean);
    snprintf(linebuf, sizeof(linebuf),
      "TELEM,%s,mean=%lu,var=%lu,ones=%lu,n=%lu,state=%s",
      SRC_NAMES[s], (unsigned long)mean, (unsigned long)var,
      (unsigned long)health[s].ones, (unsigned long)health[s].samples,
      health[s].failed ? "FAIL" : "OK");
    emitLine(linebuf);
  }
  snprintf(linebuf, sizeof(linebuf),
    "TELEM,JITTER,ones=%lu,n=%lu,state=%s",
    (unsigned long)health[IDX_JITTER].ones,
    (unsigned long)health[IDX_JITTER].samples,
    health[IDX_JITTER].failed ? "FAIL" : "OK");
  emitLine(linebuf);

  if (bmp_ok) {
    char tbuf[12]; dtostrf(temp, 5, 2, tbuf);
    snprintf(linebuf, sizeof(linebuf),
      "CONTEXT,temp_c=%s,pressure_pa=%ld", tbuf, (long)pressure);
    emitLine(linebuf);
  }

  memset(seed, 0, sizeof(seed));

#if ENABLE_OLED
  updateDisplay(temp);
#endif
}

#if ENABLE_OLED
void updateDisplay(float temp) {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.setTextSize(1);
  display.print(F("SRC: "));
  for (uint8_t s = 0; s < NUM_SOURCES; s++)
    display.print(health[s].failed ? F("X") : F("."));
  display.setCursor(0, 12);
  display.print(anySourceFailed() ? F("STATE: DEGRADED") : F("STATE: OK"));
  display.drawLine(0, 22, 128, 22, SSD1306_WHITE);
  display.setCursor(0, 28);
  for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) {
    display.print(SRC_NAMES[s][0]);
    display.print(health[s].failed ? '!' : ' ');
  }
  display.setCursor(0, 44);
  display.print(F("J bits/s ~15  T"));
  display.print(temp, 1);
  display.display();
}
#endif

void runRawAnalog() {

  for (uint16_t i = 0; i < 500; i++) {
    int n = snprintf(linebuf, sizeof(linebuf), "RAW");
    for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) {
      uint16_t v = readAnalogSettled(ANALOG_PINS[s]);
      n += snprintf(linebuf + n, sizeof(linebuf) - n, ",%u", v);
    }
    Serial.println(linebuf);
    if (Serial.available()) { checkCommand(); return; }
  }
}

void runRawJitter() {
  for (uint16_t i = 0; i < 100; i++) {
    uint16_t v = jitterNextRaw();
    Serial.print(F("JRAW,"));
    Serial.println(v);
    if (Serial.available()) { checkCommand(); return; }
  }
}

void runRestartRow() {
  emitLine("EVT,RESTART_ROW_BEGIN");
  for (uint16_t i = 0; i < RESTART_SAMPLES; i++) {
    int n = snprintf(linebuf, sizeof(linebuf), "RST");
    for (uint8_t s = 0; s < NUM_ANALOG_SRC; s++) {
      uint16_t v = readAnalogSettled(ANALOG_PINS[s]);
      n += snprintf(linebuf + n, sizeof(linebuf) - n, ",%u", v);
    }
    Serial.println(linebuf);
  }
  emitLine("EVT,RESTART_ROW_END");
  mode = MODE_HALT;
}

void loop() {
  checkCommand();
  switch (mode) {
    case MODE_SEED:       runSeedMode();   break;
    case MODE_RAW_ANALOG: runRawAnalog();  break;
    case MODE_RAW_JITTER: runRawJitter();  break;
    case MODE_RESTART:    runRestartRow(); break;
    case MODE_HALT:       delay(100);      break;
  }
}
