#!/usr/bin/env node

const fs = require('fs');
const crypto = require('crypto');
const { ml_dsa87 } = require('@noble/post-quantum/ml-dsa.js');

const FIFO = '/tmp/pqc_seed';
const OUT = 'attestations.jsonl';
const NODE_ID = process.env.NODE_ID || 'pi-edge-01';

const NONCE = crypto.randomBytes(32);

function wipe(buf) {
  if (buf && buf.fill) buf.fill(0);
}

function makeBirthCertificate(seed, meta = {}) {
  if (seed.length !== 32) {
    throw new Error(`seed must be 32 bytes, got ${seed.length}`);
  }

  if (meta.health === 'FAIL') {
    throw new Error('refusing to derive a key from a degraded entropy source');
  }

  const t0 = process.hrtime.bigint();
  const keys = ml_dsa87.keygen(seed);
  const tKeygen = Number(process.hrtime.bigint() - t0) / 1e6;

  const commitment = crypto.createHash('sha256')
    .update(seed).update(NONCE).digest('hex');

  const body = {
    version: 'entropy-provenance/1',
    node_id: NODE_ID,
    timestamp: new Date().toISOString(),
    algorithm: 'ML-DSA-87 (FIPS 204)',
    public_key: Buffer.from(keys.publicKey).toString('hex'),
    entropy_provenance: {
      seed_commitment: '0x' + commitment,
      sp800_90b_health: meta.health || 'unknown',
      failed_sources: meta.failed || 'unknown',
      claimed_entropy_bits: meta.entropyBits ?? null,
      source_health: (meta.telemetry || [])
        .filter((t) => t.state)
        .map((t) => `${t.source}=${t.state}`).join(','),
      source_vector: ['ACC_X', 'ACC_Y', 'ACC_Z', 'LIGHT', 'SOUND',
                      'HALL', 'JITTER'],
      conditioner: 'SHA-256 (sha256_lite, KAT-verified)',
    },
  };

  const canonical = Buffer.from(JSON.stringify(body), 'utf8');
  const signRand = crypto.createHash('sha256')
    .update(seed).update('signRand').digest().subarray(0, 32);

  const t1 = process.hrtime.bigint();
  const sig = ml_dsa87.sign(canonical, keys.secretKey,
                            { extraEntropy: signRand });
  const tSign = Number(process.hrtime.bigint() - t1) / 1e6;

  const t2 = process.hrtime.bigint();
  const ok = ml_dsa87.verify(sig, canonical, keys.publicKey);
  const tVerify = Number(process.hrtime.bigint() - t2) / 1e6;

  if (!ok) throw new Error('self-verification failed - refusing to emit');

  const cert = {
    ...body,
    self_signature: Buffer.from(sig).toString('hex'),
    timings_ms: {
      keygen: +tKeygen.toFixed(4),
      sign: +tSign.toFixed(4),
      verify: +tVerify.toFixed(4),
    },
  };

  wipe(keys.secretKey);
  return cert;
}

function emit(cert) {
  fs.appendFileSync(OUT, JSON.stringify(cert) + '\n');
  console.log(
    `[${cert.timestamp.slice(11, 19)}] key derived  ` +
    `pk=${cert.public_key.slice(0, 12)}...  ` +
    `health=${cert.entropy_provenance.sp800_90b_health}  ` +
    `keygen=${cert.timings_ms.keygen}ms sign=${cert.timings_ms.sign}ms ` +
    `verify=${cert.timings_ms.verify}ms`
  );
}

function watch() {
  console.log(`watching ${FIFO} (node ${NODE_ID}) -> ${OUT}`);
  console.log('start gateway.py in another terminal.\n');

  let pending = '';

  const handleRecord = (line) => {
    let rec;
    try {
      rec = JSON.parse(line);
    } catch (e) {
      console.error('malformed FIFO record, skipped');
      return;
    }
    if (!/^[0-9a-f]{64}$/i.test(rec.seed_hex || '')) {
      console.error('record missing a valid 32-byte seed, skipped');
      return;
    }
    const seed = Buffer.from(rec.seed_hex, 'hex');
    try {
      emit(makeBirthCertificate(seed, {
        health: rec.health || 'unknown',
        failed: rec.failed_sources || 'unknown',
        entropyBits: rec.entropy_bits ?? null,
        telemetry: rec.telemetry || [],
      }));
    } finally {
      wipe(seed);
    }
  };

  const loop = () => {
    let fd;
    try {
      fd = fs.openSync(FIFO, 'r');
    } catch (e) {
      console.error(`cannot open ${FIFO}: ${e.message}`);
      console.error(`create it with:  mkfifo ${FIFO}`);
      process.exit(1);
    }
    const chunk = Buffer.alloc(65536);
    try {
      let n;
      while ((n = fs.readSync(fd, chunk, 0, chunk.length, null)) > 0) {
        pending += chunk.subarray(0, n).toString('ascii');
        let nl;
        while ((nl = pending.indexOf('\n')) >= 0) {
          const line = pending.slice(0, nl).trim();
          pending = pending.slice(nl + 1);
          if (line) handleRecord(line);
        }
      }
    } catch (e) {
      if (e.code !== 'EAGAIN') console.error('read error:', e.message);
    } finally {
      fs.closeSync(fd);
      wipe(chunk);
    }
    setImmediate(loop);
  };
  loop();
}

function bench(n) {
  console.log(`ML-DSA-87 benchmark, ${n} iterations`);
  console.log(`platform: ${process.arch} ${process.platform}, ` +
              `node ${process.version}\n`);

  const seeds = Array.from({ length: n }, () => crypto.randomBytes(32));
  const msg = Buffer.from('firmware manifest placeholder');
  const kg = [], sg = [], vf = [];

  for (let i = 0; i < 5; i++) ml_dsa87.keygen(seeds[0]);

  for (let i = 0; i < n; i++) {
    let t = process.hrtime.bigint();
    const k = ml_dsa87.keygen(seeds[i]);
    kg.push(Number(process.hrtime.bigint() - t) / 1e6);

    t = process.hrtime.bigint();
    const s = ml_dsa87.sign(msg, k.secretKey);
    sg.push(Number(process.hrtime.bigint() - t) / 1e6);

    t = process.hrtime.bigint();
    ml_dsa87.verify(s, msg, k.publicKey);
    vf.push(Number(process.hrtime.bigint() - t) / 1e6);

    wipe(k.secretKey);
  }

  const stat = (a) => {
    const s = [...a].sort((x, y) => x - y);
    const mean = a.reduce((p, c) => p + c, 0) / a.length;
    const sd = Math.sqrt(a.reduce((p, c) => p + (c - mean) ** 2, 0) / a.length);
    const ci = 1.96 * sd / Math.sqrt(a.length);
    return { mean, sd, ci, p50: s[Math.floor(s.length * 0.5)],
             p95: s[Math.floor(s.length * 0.95)], min: s[0],
             max: s[s.length - 1] };
  };

  console.log('operation   mean(ms)   sd      95% CI              p95     max');
  console.log('-'.repeat(68));
  for (const [name, arr] of [['keygen', kg], ['sign', sg], ['verify', vf]]) {
    const t = stat(arr);
    console.log(
      `${name.padEnd(11)}${t.mean.toFixed(4).padStart(8)}` +
      `${t.sd.toFixed(4).padStart(9)}   ` +
      `[${(t.mean - t.ci).toFixed(4)}, ${(t.mean + t.ci).toFixed(4)}]` +
      `${t.p95.toFixed(4).padStart(9)}${t.max.toFixed(4).padStart(8)}`
    );
  }
  const L = ml_dsa87.lengths;
  console.log(`\nsizes: pk ${L.publicKey} B, sk ${L.secretKey} B, ` +
              `sig ${L.signature} B, seed ${L.seed} B`);
  console.log(`RSS: ${(process.memoryUsage().rss / 1048576).toFixed(1)} MB`);
}

const argv = process.argv.slice(2);
const arg = (f) => { const i = argv.indexOf(f); return i < 0 ? null : argv[i + 1]; };

if (argv.includes('--bench')) {
  bench(parseInt(arg('--bench') || '100', 10));
} else if (arg('--seed')) {
  const hex = arg('--seed');
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) {
    console.error('--seed needs exactly 64 hex characters (32 bytes)');
    process.exit(1);
  }
  const seed = Buffer.from(hex, 'hex');
  const cert = makeBirthCertificate(seed, { health: 'PASS',
    failed: 'none', entropyBits: null });
  emit(cert);
  console.log('\n' + JSON.stringify(cert, (k, v) =>
    (k === 'public_key' || k === 'self_signature')
      ? v.slice(0, 32) + `... (${v.length / 2} bytes)` : v, 2));
  wipe(seed);
} else if (argv.includes('--watch')) {
  watch();
} else {
  console.log(`usage:
  node keygen.js --watch              consume seeds from ${FIFO}
  node keygen.js --seed <64 hex>      one-shot, for testing
  node keygen.js --bench 100          performance benchmark (run on the Pi)`);
}

module.exports = { makeBirthCertificate };
