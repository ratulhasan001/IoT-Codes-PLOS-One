# Entropy-Assured Post-Quantum Key Generation on IoT Edge Devices

Code and data for the manuscript *Entropy-assured post-quantum key generation on IoT edge devices: source independence, measured min-entropy and signature scheme selection*, submitted to PLOS ONE and currently under review.

The work builds a seven-source hardware entropy module: six analogue sensor channels and one watchdog-oscillator jitter source on an Arduino Mega 2560. Each source is characterised under NIST SP 800-90B. The module's conditioned seeds feed FIPS 204 ML-DSA-87 key generation on a Raspberry Pi 4 gateway. The repository contains:

- the firmware, which runs per-source health tests and produces seeds;
- the scripts that capture raw samples and analyse them;
- the gateway and key-derivation code;
- the eight-scheme post-quantum signature benchmark;
- the raw captures and logs behind the reported results.

Main results reported in the manuscript:

- Per-source non-IID min-entropy ranges from 0.214 to 0.726 bits per sample.
- Three nominally independent channels (LIGHT, SOUND, HALL) are strongly correlated in their full sample values, with Pearson r up to +0.966.
- Eight post-quantum signature schemes were benchmarked on the Pi's Cortex-A72.

## Citation

> **Status: under review.** This manuscript has not been peer reviewed or accepted yet, and it has no DOI. Please cite it as a submitted manuscript. This entry will be updated if the paper is published.

```bibtex
@unpublished{hasan2026entropy,
  author = {Hasan, Ratul and Rayhan, Md Arik and Pranto, Md. Ohiduzaman and
            Haque, Md. Momenul and Oley, Yousuf and Farjana, Samiha},
  title  = {Entropy-assured post-quantum key generation on {IoT} edge devices:
            source independence, measured min-entropy and signature scheme selection},
  note   = {Manuscript submitted to PLOS ONE, September 2026. Under review},
  year   = {2026}
}
```

## Repository layout

| Path | Language | Purpose |
|---|---|---|
| `firmware/entropy_source.ino` | Arduino C++ | Entropy module firmware. Samples 6 ADC channels and the WDT/Timer1 jitter source, runs SP 800-90B Repetition Count and Adaptive Proportion tests per source, conditions with SHA-256, and emits CRC-16-protected serial lines. It also has raw-capture modes for entropy estimation. |
| `firmware/sha256_lite.h` | C | Self-contained SHA-256 (FIPS 180-4) for AVR, used as the conditioner. It replaces a library that would also claim the watchdog interrupt vector. |
| `analysis/capture_raw.py` | Python | Puts the board into raw analogue, raw jitter or restart mode and writes the unconditioned samples to CSV. |
| `analysis/analyze_raw.py` | Python | Per-source bias, IID min-entropy upper bound, longest runs, inter-source Pearson correlation (full value and LSB) and LSB autocorrelation at lags 1 to 8. Exports `.bin` files for `ea_non_iid`. |
| `analysis/jitter_to_bin.py` | Python | Jitter-capture summary (bias, von Neumann retention, autocorrelation). Exports `.bin` files for `ea_non_iid`. |
| `analysis/nist_cutoffs.py` | Python | Exact SP 800-90B RCT/APT cutoffs (alpha = 2^-20, W = 1024) for given min-entropy values. |
| `analysis/make_figures.py` | Python | Draws the five data figures in the manuscript. |
| `gateway/gateway.py` | Python | Raspberry Pi gateway. Checks per-line CRCs, logs seed attestations as append-only JSONL, and passes healthy seeds to the key-derivation process through a FIFO. Seeds are never written to disk. |
| `gateway/keygen.js` | Node.js | Derives an ML-DSA-87 key pair deterministically from each 32-byte seed. Writes a self-signed provenance record ("birth certificate"). Also has a one-shot mode and an ML-DSA-87-only benchmark. |
| `gateway/bench_pqc.js` | Node.js | Keygen/sign/verify timings and key/signature sizes for ML-DSA-44/65/87, Falcon-512/1024 and SLH-DSA-SHA2-128f/192f/128s. Also measures ECDSA P-256 and Ed25519 as baselines. |
| `dataset/` | CSV, JSONL, JSON | Raw captures, gateway log, attestations and benchmark output (see [Dataset](#dataset)). |

## Hardware

The firmware uses ATmega Timer1 and watchdog registers (`TCCR1A`, `TCCR1B`, `TCNT1`, `WDTCSR`) directly, so it runs only on AVR boards. The manuscript describes the following setup.

| Source | Pin | Sensor (as described in the manuscript) |
|---|---|---|
| `ACC_X` | A0 | ADXL335 accelerometer (GY-61), x axis |
| `ACC_Y` | A1 | ADXL335, y axis |
| `ACC_Z` | A2 | ADXL335, z axis |
| `LIGHT` | A3 | photoresistor |
| `SOUND` | A6 | electret microphone |
| `HALL` | A7 | Hall-effect sensor |
| `JITTER` | internal | watchdog RC oscillator sampled against the 16 MHz crystal through Timer1 |

Other parts:

- **Entropy module board:** Arduino Mega 2560 (ATmega2560, 16 MHz).
- **Context sensor:** BMP180 temperature and pressure sensor on I2C. Its readings are logged and hashed in as context only. They do not count toward the entropy budget.
- **Display:** optional 128x64 SSD1306 OLED on I2C at address `0x3C`. Set `ENABLE_OLED` to `0` in the sketch to disable it.
- **Gateway:** Raspberry Pi 4 Model B (Cortex-A72, 4 cores, arm64 Linux), connected over USB serial at 500000 baud.

All sensors share one 5 V / GND rail. The manuscript identifies this shared rail and the shared ADC sample-and-hold as the two candidate causes of the inter-channel coupling it reports.

## Pipeline

```
 sensors + WDT jitter
        |
 firmware/entropy_source.ino
        |
        |-- raw modes (R / J / B) --> analysis/capture_raw.py --> raw_*.csv
        |                                    |
        |                    analyze_raw.py / jitter_to_bin.py --> nist/*.bin
        |                                    |
        |                    ea_non_iid (NIST, external) --> min-entropy H
        |                                    |
        |                    nist_cutoffs.py --> RCT/APT cutoffs --> back into the sketch
        |                                    |
        |                    make_figures.py --> fig_*.pdf / fig_*.png
        |
        |-- seed mode (S) --> gateway/gateway.py --> entropy_log.jsonl
                                     |  (FIFO /tmp/pqc_seed)
                              gateway/keygen.js --watch --> attestations.jsonl

 gateway/bench_pqc.js (stand-alone, on the Pi) --> pqc-bench-<host>-<ms>.json
```

### Firmware serial protocol

Each command is a single character sent over serial at 500000 baud.

| Command | Mode | Output |
|---|---|---|
| `S` | Seed mode (default at boot) | Per 256-sample block: `SEED`, then `TELEM` lines per source, then a `CONTEXT` line (BMP180). Each line ends in `*XXXX` (CRC-16/CCITT). |
| `R` | Raw analogue | `RAW,<ACC_X>,<ACC_Y>,<ACC_Z>,<LIGHT>,<SOUND>,<HALL>` (10-bit values, no CRC) |
| `J` | Raw jitter | `JRAW,<TCNT1>` (no CRC) |
| `B` | Restart test | `EVT,RESTART_ROW_BEGIN`, then 1000 `RST,...` lines, then `EVT,RESTART_ROW_END`. The board then halts until power-cycled. |
| `H` | Health dump | One `HEALTH,<source>,...` line per source |
| `Z` | Reset | Clears latched health-test failures |

In seed mode, each block hashes the following into SHA-256 to make a 32-byte seed:

- 256 samples from each analogue channel (each channel is read twice and the first read is discarded, to let the ADC settle);
- 64 von Neumann-debiased jitter bits;
- the BMP180 readings.

The health tests run on the raw least significant bit of each source, before conditioning. Failures latch until a `Z` command is sent. The `SEED` line reports `health=OK|FAIL`, the failed sources, and an entropy budget computed from `H_MILLIBITS` for the sources that have not failed.

## Reproducing the results

### Dependencies

**Firmware (Arduino IDE or `arduino-cli`):**

- AVR board core;
- the libraries `Adafruit BMP085 Library`, `Adafruit GFX Library` and `Adafruit SSD1306`, plus the built-in `Wire`;
- `sha256_lite.h`, which must sit in the same folder as the sketch.

**Python 3:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pyserial numpy matplotlib
```

| Script | Needs |
|---|---|
| `capture_raw.py`, `gateway.py` | `pyserial` |
| `analyze_raw.py`, `jitter_to_bin.py` | `numpy` |
| `make_figures.py` | `matplotlib`, `numpy` |
| `nist_cutoffs.py` | standard library only |

**Node.js:** `keygen.js` and `bench_pqc.js` need `@noble/post-quantum`. The repository has no `package.json`, so install the package next to the scripts. The manuscript reports version 0.7.1:

```bash
cd gateway
npm install @noble/post-quantum@0.7.1
```

The benchmark in `dataset/` was run on Node.js v20.19.2. `@noble/post-quantum` is published as an ES module, and the scripts load it with `require()`. Use a Node.js version that can `require()` ES modules (20.19+ or 22.12+).

**NIST SP 800-90B tool (external):** min-entropy is estimated with `ea_non_iid` from NIST's reference implementation. It is not included in this repository, and no script here calls it automatically: the analysis scripts write the input files and print the command to run. Build it separately:

```bash
git clone https://github.com/usnistgov/SP800-90B_EntropyAssessment
cd SP800-90B_EntropyAssessment/cpp && make
# Debian / Raspberry Pi OS build deps:
# sudo apt install build-essential libbz2-dev libdivsufsort-dev libjsoncpp-dev libssl-dev
```

The Makefile needs OpenMP, which Apple clang does not provide, so build it on Linux (for example on the Pi). The manuscript reports using commit `87c104d`.

### 1. Flash the firmware

1. Open `firmware/entropy_source.ino`. Keep `sha256_lite.h` in the same folder.
2. Select the Mega 2560 board and upload.
3. On boot, the board prints:
   - `EVT,BOOT,fw=entropy_source_v2`
   - an `EVT,CONFIG,...` line.

> **Health-test constants.** The sketch as committed contains placeholder constants that assume H = 0.5 for the analogue sources and H = 1.0 for jitter:
>
> - `RCT_CUTOFF` = 41 / 21
> - `APT_CUTOFF` = 793 / 589
> - `H_MILLIBITS` = 500 / 1000
>
> The per-source values in the manuscript come from the measured min-entropies:
>
> ```c
> const uint16_t RCT_CUTOFF[NUM_SOURCES]  = { 72, 95, 64, 40, 40, 34, 29 };
> const uint16_t APT_CUTOFF[NUM_SOURCES]  = { 897, 934, 880, 782, 782, 743, 694 };
> const uint16_t H_MILLIBITS[NUM_SOURCES] = { 285, 214, 319, 523, 523, 610, 726 };
> ```
>
> These cutoffs are what `nist_cutoffs.py` prints for H = 0.285, 0.214, 0.319, 0.523, 0.523, 0.610 and 0.726 (step 4). With these `H_MILLIBITS` values the firmware's budget comes to 679 bits per block, which is the `claimed_entropy_bits` value recorded in `dataset/entropy_log.jsonl`. With the committed placeholders it would report 832 bits.

### 2. Capture raw samples

Run the following on the machine connected to the board. The default port is `/dev/cu.usbmodem1101` (macOS); on Linux, pass `--port /dev/ttyACM0`.

```bash
cd analysis
# 10^6 samples per analogue channel (mode R)
python3 capture_raw.py --mode analog -n 1000000 -o raw_analog.csv

# raw jitter (mode J); runs at about 62 samples/s, so 10^6 samples takes about 4.5 h
python3 capture_raw.py --mode jitter -n 1000000 -o raw_jitter.csv

# optional restart-test rows (mode B): one 1000-sample row per run, appended;
# power-cycle the board between runs
python3 capture_raw.py --mode restart -o restart.csv --node node-01
```

Notes:

- Ctrl-C stops a capture early and keeps the samples collected so far.
- The script warns if more than 0.1% of lines are malformed.
- When it exits, it switches the board back to seed mode.
- For a long unattended jitter run:
  - Linux: `nohup python3 capture_raw.py ... > capture.log 2>&1 &`
  - macOS: prefix the command with `caffeinate -i`.

### 3. Statistical analysis and NIST input files

```bash
python3 analyze_raw.py ../dataset/raw_analog.csv -o nist
python3 jitter_to_bin.py ../dataset/raw_jitter.csv -o nist
```

`analyze_raw.py` prints the following for each source:

- mean, standard deviation, P(LSB = 1) and the IID upper bound;
- longest run and diagnostic flags;
- the 6x6 Pearson correlation matrix for full values and for LSBs;
- LSB autocorrelation at lags 1 to 8.

It writes `nist/<SOURCE>_lsb.bin` (one byte per sample, 0 or 1) and `nist/<SOURCE>_low8.bin` (the low 8 ADC bits).

`jitter_to_bin.py` writes:

- `nist/JITTER_lsb.bin`, the raw LSB before debiasing (the noise-source output assessed in the manuscript);
- `nist/JITTER_vn.bin`, the von Neumann-debiased bits.

Run on the included `dataset/raw_analog.csv`, `analyze_raw.py` gives the correlation matrices, IID bounds and autocorrelation values that are hard-coded in `make_figures.py`.

### 4. Min-entropy estimation and health-test cutoffs

```bash
# per source, binary symbols (1 bit per sample); repeat for each *_lsb.bin
./ea_non_iid nist/ACC_X_lsb.bin 1
...
./ea_non_iid nist/JITTER_lsb.bin 1
```

Take the minimum over the non-IID estimators as H for each source. Then compute the cutoffs:

```bash
python3 nist_cutoffs.py 0.285 0.214 0.319 0.523 0.523 0.610 0.726
```

This prints the RCT and APT cutoff for each H given. With two or more arguments, the script also prints a "Paste into entropy_source.ino" block. That block treats the first argument as a single analogue H shared by all six channels and the second as the jitter H. For per-source cutoffs, copy the values from the table instead. Run the script with no arguments to get a reference table over a range of H values.

### 5. Figures

```bash
python3 make_figures.py
```

Writes the following to the current directory, each as `.pdf` and `.png`:

- `fig_minentropy`
- `fig_budget`
- `fig_tradeoff`
- `fig_correlation`
- `fig_acf`

The script does not read the dataset; the numbers it plots are hard-coded:

| Figure | Values plotted | Source of the values |
|---|---|---|
| `fig_minentropy` | IID bounds | `analyze_raw.py` / `jitter_to_bin.py` output |
| `fig_minentropy` | non-IID estimates | `ea_non_iid` output |
| `fig_correlation`, `fig_acf` | correlation and autocorrelation values | `analyze_raw.py` output |
| `fig_tradeoff` | signature sizes and mean verification times | `dataset/pqc-bench-pi-1787333879412.json` |
| `fig_budget` | totals for the four independence assumptions | manuscript |

### 6. Gateway, key derivation and attestations (on the Pi)

Use three terminals. Start the consumer before the gateway: the gateway opens the FIFO in non-blocking mode, and if nothing is reading it the seed is not delivered (`delivered_to_consumer: false`).

```bash
# terminal 1: create the FIFO once
mkfifo /tmp/pqc_seed

# terminal 2: key derivation; writes attestations.jsonl in the current directory
cd gateway
NODE_ID=pi-edge-01 node keygen.js --watch

# terminal 3: gateway; writes entropy_log.jsonl
python3 gateway.py --port /dev/ttyACM0 --node-id pi-edge-01 \
    --log entropy_log.jsonl --fifo /tmp/pqc_seed
```

How the components handle each seed:

- **`gateway.py`:**
  - drops any line whose CRC does not match;
  - logs every `SEED` line as a `seed_attestation` record, recording a commitment `SHA-256(seed || nonce)` rather than the seed itself;
  - forwards only `health=OK` seeds to the FIFO;
  - prints session statistics on Ctrl-C.
- **`keygen.js`:**
  - refuses seeds flagged `FAIL`;
  - runs `ml_dsa87.keygen(seed)`;
  - signs the provenance body with the new secret key and verifies the signature before writing the record.

Other modes:

```bash
node keygen.js --seed <64 hex chars>   # one-shot derivation, for testing
node keygen.js --bench 100             # ML-DSA-87 keygen/sign/verify timing only
```

### 7. Post-quantum signature benchmark (on the Pi)

```bash
cd gateway
node bench_pqc.js --iter 1000                      # configuration used for dataset/ (base_iterations = 1000)
node bench_pqc.js --quick                          # skip SLH-DSA-128s
node bench_pqc.js --only ml_dsa87,falcon512        # subset; skips the classical baselines
```

Iteration counts scale per scheme from `--iter`. With `--iter 1000` the counts are:

| Scheme | Iterations |
|---|---|
| ML-DSA-44, ML-DSA-65, ML-DSA-87 | 1000 each |
| Falcon-512 | 500 |
| Falcon-1024 | 300 |
| SLH-DSA-128f | 50 |
| SLH-DSA-192f | 30 |
| SLH-DSA-128s | 5 |

Each scheme also gets a 5% warm-up, with at least 2 warm-up runs. Results go to `pqc-bench-<hostname>-<epoch ms>.json`.

The post-quantum schemes run in pure JavaScript (`@noble/post-quantum`). The ECDSA P-256 and Ed25519 baselines run in native OpenSSL through `node:crypto`. The two groups are reported separately and should not be compared directly. LMS and XMSS are not benchmarked.

## Dataset

All files in `dataset/` were recorded from the hardware described above. The gateway session and the benchmark ran on 2026-08-21 on node `pi-edge-01`.

### `raw_analog.csv`: raw analogue capture (mode `R`)

1,000,000 rows plus a header (about 31 MB).

| Column | Description |
|---|---|
| `idx` | Sample index, 0 to 999999 |
| `ACC_X`, `ACC_Y`, `ACC_Z`, `LIGHT`, `SOUND`, `HALL` | Unconditioned 10-bit ADC readings (0 to 1023) from pins A0, A1, A2, A3, A6, A7. One row is one pass over all six channels. |

### `raw_jitter.csv`: raw jitter capture (mode `J`)

20,000 rows plus a header.

| Column | Description |
|---|---|
| `idx` | Sample index |
| `tcnt1` | Timer1 counter value (0 to 65535) latched in the watchdog interrupt. Its least significant bit, before von Neumann debiasing, is the noise-source output. |

> **Jitter sample count.** This file holds 2x10^4 jitter samples, fewer than the 10^6 that SP 800-90B specifies. The manuscript states that the jitter estimate it uses (H = 0.726) comes from a 5x10^4-sample capture, which is not included here. At 2x10^4 samples the manuscript reports H = 0.626. The analogue capture meets the 10^6 requirement.

### `entropy_log.jsonl`: gateway log (`gateway.py`)

139 records, one JSON object per line:

- 1 `gateway_start` record;
- 137 `seed_attestation` records, all `PASS` with 679 claimed bits; 135 were delivered to the consumer;
- 1 `gateway_stop` record.

Fields present in every record:

| Field | Description |
|---|---|
| `type` | `gateway_start`, `seed_attestation` or `gateway_stop` |
| `node_id` | Gateway identifier |
| `ts` | UTC timestamp (ISO 8601) |

`gateway_start` fields:

| Field | Description |
|---|---|
| `port`, `baud` | Serial port and baud rate |
| `clock` | NTP status from `chronyc` or `timedatectl` |

`seed_attestation` fields:

| Field | Description |
|---|---|
| `sp800_90b_health` | `PASS` or `FAIL` (from the firmware's per-source RCT/APT state) |
| `failed_sources` | `none` or the failed sources joined with `+` |
| `claimed_entropy_bits` | Firmware entropy budget for the block |
| `seed_commitment` | `0x` + SHA-256(seed &#124;&#124; nonce). The nonce is random per gateway session and held only in memory. |
| `telemetry` | List of per-source objects; see below |
| `delivered_to_consumer` | Whether the seed was written to the FIFO |

`gateway_stop` fields:

| Field | Description |
|---|---|
| `stats` | Session counters: `seeds_ok`, `seeds_degraded`, `crc_drops`, `parse_drops`, `telemetry`, `events` |

**Telemetry objects.** All values are stored as strings.

| Source | Fields | Notes |
|---|---|---|
| Analogue sources | `source`, `mean`, `var`, `ones`, `n`, `state` | `mean` and `var` are per block; `ones` and `n` are cumulative since boot or the last `Z` |
| `JITTER` | `source`, `ones`, `n`, `state` | `n` counts raw bits before debiasing |
| `BMP180_context` | `source`, `temp_c`, `pressure_pa` | Context readings only |

The firmware sends a block's `TELEM` and `CONTEXT` lines after that block's `SEED` line, so the telemetry attached to a seed record describes the previous block. The first record's list is empty.

### `attestations.jsonl`: ML-DSA-87 provenance records (`keygen.js`)

135 records, one per delivered seed.

| Field | Description |
|---|---|
| `version` | `entropy-provenance/1` |
| `node_id`, `timestamp` | Node identifier and ISO 8601 time |
| `algorithm` | `ML-DSA-87 (FIPS 204)` |
| `public_key` | Hex-encoded ML-DSA-87 public key (2592 bytes) |
| `entropy_provenance.seed_commitment` | `0x` + SHA-256(seed &#124;&#124; nonce), using `keygen.js`'s own per-process nonce (see the note below) |
| `entropy_provenance.sp800_90b_health`, `failed_sources`, `claimed_entropy_bits` | Copied from the gateway record |
| `entropy_provenance.source_health` | `SOURCE=state` list built from the telemetry |
| `entropy_provenance.source_vector` | The seven source names |
| `entropy_provenance.conditioner` | `SHA-256 (sha256_lite, KAT-verified)` |
| `self_signature` | Hex-encoded ML-DSA-87 signature (4627 bytes) over `JSON.stringify` of the record, excluding `self_signature` and `timings_ms`. It is signed with the derived secret key as proof of possession. |
| `timings_ms` | `keygen`, `sign` and `verify` times for this record, in ms |

The gateway's commitment and `keygen.js`'s commitment use different nonces, so the same seed produces different commitments in the two files. Link records by order and time instead.

The self-signatures can be checked with the following ES module, run from `gateway/` after installing `@noble/post-quantum`. On the included file, all 135 verify.

```js
// verify.mjs  ->  node verify.mjs ../dataset/attestations.jsonl
import fs from 'node:fs';
import { ml_dsa87 } from '@noble/post-quantum/ml-dsa.js';
const lines = fs.readFileSync(process.argv[2], 'utf8').trim().split('\n');
let ok = 0;
for (const line of lines) {
  const { self_signature, timings_ms, ...body } = JSON.parse(line);
  const msg = Buffer.from(JSON.stringify(body), 'utf8');
  if (ml_dsa87.verify(Buffer.from(self_signature, 'hex'), msg,
                      Buffer.from(body.public_key, 'hex'))) ok++;
}
console.log(`${ok}/${lines.length} signatures verify`);
```

### `pqc-bench-pi-1787333879412.json`: signature benchmark (`bench_pqc.js --iter 1000`)

Recorded on host `pi`:

- CPU: Cortex-A72, 4 cores, 3.71 GB memory;
- Node.js v20.19.2;
- kernel `6.12.75+rpt-rpi-v8`.

| Key | Contents |
|---|---|
| `timestamp`, `host`, `config` | Run metadata. `config` holds `base_iterations` = 1000 and `message_bytes` = 51. |
| `results[]` | One entry per scheme; fields listed below |
| `caveats` | Notes on cross-substrate comparison and why LMS/XMSS are omitted |

Each `results[]` entry has:

- `id`, `label`, `category` (`lattice`, `hash` or `classical`) and `quantum_safe`;
- `keygen`, `sign` and `verify` timing objects, each with `mean`, `sd`, `n`, `min`, `max`, `p50`, `p95` and `ci95`, all in ms;
- `sizes`: `publicKey`, `secretKey`, `signature` and `seed`, in bytes.

There are ten entries: eight post-quantum schemes plus the two classical baselines.

## Notes

- `make_figures.py` holds the published numbers as constants. Re-running the capture and analysis on new hardware will not update the figures until those constants are edited.
- The restart-test mode (`B`) is implemented, but no restart dataset is included.
- No licence file is included in this repository.

---

Ratul Hasan · [ratulhasan.dev](https://ratulhasan.dev)
