#ifndef SHA256_LITE_H
#define SHA256_LITE_H

#include <stdint.h>
#include <string.h>

#ifdef __AVR__
  #include <avr/pgmspace.h>
  #define SHA256L_K_READ(i) ((uint32_t)pgm_read_dword_near(&sha256l_K[i]))
  #define SHA256L_PROGMEM PROGMEM
#else
  #define SHA256L_K_READ(i) (sha256l_K[i])
  #define SHA256L_PROGMEM
#endif

static const uint32_t sha256l_K[64] SHA256L_PROGMEM = {
  0x428a2f98UL, 0x71374491UL, 0xb5c0fbcfUL, 0xe9b5dba5UL,
  0x3956c25bUL, 0x59f111f1UL, 0x923f82a4UL, 0xab1c5ed5UL,
  0xd807aa98UL, 0x12835b01UL, 0x243185beUL, 0x550c7dc3UL,
  0x72be5d74UL, 0x80deb1feUL, 0x9bdc06a7UL, 0xc19bf174UL,
  0xe49b69c1UL, 0xefbe4786UL, 0x0fc19dc6UL, 0x240ca1ccUL,
  0x2de92c6fUL, 0x4a7484aaUL, 0x5cb0a9dcUL, 0x76f988daUL,
  0x983e5152UL, 0xa831c66dUL, 0xb00327c8UL, 0xbf597fc7UL,
  0xc6e00bf3UL, 0xd5a79147UL, 0x06ca6351UL, 0x14292967UL,
  0x27b70a85UL, 0x2e1b2138UL, 0x4d2c6dfcUL, 0x53380d13UL,
  0x650a7354UL, 0x766a0abbUL, 0x81c2c92eUL, 0x92722c85UL,
  0xa2bfe8a1UL, 0xa81a664bUL, 0xc24b8b70UL, 0xc76c51a3UL,
  0xd192e819UL, 0xd6990624UL, 0xf40e3585UL, 0x106aa070UL,
  0x19a4c116UL, 0x1e376c08UL, 0x2748774cUL, 0x34b0bcb5UL,
  0x391c0cb3UL, 0x4ed8aa4aUL, 0x5b9cca4fUL, 0x682e6ff3UL,
  0x748f82eeUL, 0x78a5636fUL, 0x84c87814UL, 0x8cc70208UL,
  0x90befffaUL, 0xa4506cebUL, 0xbef9a3f7UL, 0xc67178f2UL
};

class SHA256Lite {
public:
  SHA256Lite() { reset(); }

  void reset() {
    h[0] = 0x6a09e667UL; h[1] = 0xbb67ae85UL;
    h[2] = 0x3c6ef372UL; h[3] = 0xa54ff53aUL;
    h[4] = 0x510e527fUL; h[5] = 0x9b05688cUL;
    h[6] = 0x1f83d9abUL; h[7] = 0x5be0cd19UL;
    total = 0;
    fill  = 0;
  }

  void update(const void *data, size_t len) {
    const uint8_t *p = (const uint8_t *)data;
    total += len;
    while (len) {
      size_t take = 64 - fill;
      if (take > len) take = len;
      memcpy(buf + fill, p, take);
      fill += take; p += take; len -= take;
      if (fill == 64) { compress(buf); fill = 0; }
    }
  }

  void finalize(uint8_t *out, size_t outLen) {
    uint64_t bits = (uint64_t)total * 8;
    uint8_t pad = 0x80;
    update(&pad, 1);
    pad = 0x00;
    while (fill != 56) update(&pad, 1);
    uint8_t lenbe[8];
    for (int8_t i = 7; i >= 0; i--) { lenbe[i] = (uint8_t)(bits & 0xFF); bits >>= 8; }

    memcpy(buf + 56, lenbe, 8);
    compress(buf);
    fill = 0;

    uint8_t digest[32];
    for (uint8_t i = 0; i < 8; i++) {
      digest[i * 4 + 0] = (uint8_t)(h[i] >> 24);
      digest[i * 4 + 1] = (uint8_t)(h[i] >> 16);
      digest[i * 4 + 2] = (uint8_t)(h[i] >> 8);
      digest[i * 4 + 3] = (uint8_t)(h[i]);
    }
    if (outLen > 32) outLen = 32;
    memcpy(out, digest, outLen);
    memset(digest, 0, sizeof(digest));
  }

private:
  uint32_t h[8];
  uint8_t  buf[64];
  uint8_t  fill;
  uint32_t total;

  static uint32_t rotr(uint32_t x, uint8_t n) { return (x >> n) | (x << (32 - n)); }

  void compress(const uint8_t *block) {
    uint32_t w[16];
    for (uint8_t i = 0; i < 16; i++)
      w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) |
             ((uint32_t)block[i * 4 + 2] << 8) | (uint32_t)block[i * 4 + 3];

    uint32_t a = h[0], b = h[1], c = h[2], d = h[3];
    uint32_t e = h[4], f = h[5], g = h[6], hh = h[7];

    for (uint8_t i = 0; i < 64; i++) {
      if (i >= 16) {
        uint32_t w15 = w[(i + 1) & 15], w2 = w[(i + 14) & 15];
        uint32_t s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >> 3);
        uint32_t s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >> 10);
        w[i & 15] += s0 + w[(i + 9) & 15] + s1;
      }
      uint32_t S1  = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      uint32_t ch  = (e & f) ^ ((~e) & g);
      uint32_t t1  = hh + S1 + ch + SHA256L_K_READ(i) + w[i & 15];
      uint32_t S0  = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t t2  = S0 + maj;
      hh = g; g = f; f = e; e = d + t1;
      d = c; c = b; b = a; a = t1 + t2;
    }

    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }
};

#endif
