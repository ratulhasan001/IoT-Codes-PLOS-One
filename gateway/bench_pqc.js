#!/usr/bin/env node

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const { ml_dsa44, ml_dsa65, ml_dsa87 } = require('@noble/post-quantum/ml-dsa.js');
const { falcon512, falcon1024 } = require('@noble/post-quantum/falcon.js');
const slh = require('@noble/post-quantum/slh-dsa.js');

const MSG = Buffer.from('firmware manifest v1.4.2 cid=QmXo... sha256=a91f...');

const SCHEMES = [
  { id: 'ml_dsa44',  label: 'ML-DSA-44',        api: ml_dsa44,  scale: 1,     cat: 'lattice' },
  { id: 'ml_dsa65',  label: 'ML-DSA-65',        api: ml_dsa65,  scale: 1,     cat: 'lattice' },
  { id: 'ml_dsa87',  label: 'ML-DSA-87',        api: ml_dsa87,  scale: 1,     cat: 'lattice' },
  { id: 'falcon512', label: 'Falcon-512',       api: falcon512, scale: 0.5,   cat: 'lattice' },
  { id: 'falcon1024',label: 'Falcon-1024',      api: falcon1024,scale: 0.3,   cat: 'lattice' },
  { id: 'slh128f',   label: 'SLH-DSA-128f',     api: slh.slh_dsa_sha2_128f, scale: 0.05, cat: 'hash' },
  { id: 'slh192f',   label: 'SLH-DSA-192f',     api: slh.slh_dsa_sha2_192f, scale: 0.03, cat: 'hash' },
  { id: 'slh128s',   label: 'SLH-DSA-128s',     api: slh.slh_dsa_sha2_128s, scale: 0.005, cat: 'hash', slow: true },
];

function stats(t) {
  const n = t.length;
  const mean = t.reduce((a, b) => a + b, 0) / n;
  const sd = Math.sqrt(t.reduce((a, b) => a + (b - mean) ** 2, 0) / n);
  const s = [...t].sort((a, b) => a - b);
  const moe = 1.96 * sd / Math.sqrt(n);
  return {
    mean, sd, n,
    min: s[0], max: s[n - 1],
    p50: s[Math.floor(0.5 * n)],
    p95: s[Math.floor(0.95 * n)],
    ci95: [mean - moe, mean + moe],
  };
}

function timeIt(fn, iters, warmup) {
  for (let i = 0; i < warmup; i++) fn(i);
  const t = [];
  for (let i = 0; i < iters; i++) {
    const a = process.hrtime.bigint();
    fn(i);
    t.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  return stats(t);
}

function benchScheme(sc, baseIter) {
  const iters = Math.max(5, Math.round(baseIter * sc.scale));
  const warmup = Math.max(2, Math.round(iters * 0.05));
  process.stdout.write(`  ${sc.label.padEnd(16)} n=${String(iters).padStart(4)} ... `);

  const L = sc.api.lengths || {};
  const seedLen = L.seed || 32;
  const seeds = Array.from({ length: iters + warmup },
                           () => crypto.randomBytes(seedLen));

  let keygen;
  try {
    keygen = timeIt((i) => sc.api.keygen(seeds[i]), iters, warmup);
  } catch (e) {
    keygen = timeIt(() => sc.api.keygen(), iters, warmup);
  }

  const k = sc.api.keygen(seeds[0]);
  const sign = timeIt(() => sc.api.sign(MSG, k.secretKey), iters, warmup);
  const sig = sc.api.sign(MSG, k.secretKey);
  const verify = timeIt(() => sc.api.verify(sig, MSG, k.publicKey), iters, warmup);

  if (!sc.api.verify(sig, MSG, k.publicKey)) {
    throw new Error(`${sc.label}: self-verification failed`);
  }

  console.log(`kg ${keygen.mean.toFixed(3)}ms  sg ${sign.mean.toFixed(3)}ms  vf ${verify.mean.toFixed(3)}ms`);
  return {
    id: sc.id, label: sc.label, category: sc.cat, quantum_safe: true,
    keygen, sign, verify,
    sizes: { publicKey: k.publicKey.length, secretKey: k.secretKey.length,
             signature: sig.length, seed: seedLen },
  };
}

function benchClassical(baseIter) {
  const out = [];
  const iters = baseIter, warmup = Math.max(2, Math.round(iters * 0.05));

  for (const [label, curve] of [['ECDSA P-256', 'prime256v1'], ['Ed25519', null]]) {
    process.stdout.write(`  ${label.padEnd(16)} n=${String(iters).padStart(4)} ... `);
    const mk = curve
      ? () => crypto.generateKeyPairSync('ec', { namedCurve: curve })
      : () => crypto.generateKeyPairSync('ed25519');
    const keygen = timeIt(mk, iters, warmup);
    const kp = mk();
    const doSign = curve
      ? () => crypto.sign('sha256', MSG, kp.privateKey)
      : () => crypto.sign(null, MSG, kp.privateKey);
    const sign = timeIt(doSign, iters, warmup);
    const sg = doSign();
    const doVerify = curve
      ? () => crypto.verify('sha256', MSG, kp.publicKey, sg)
      : () => crypto.verify(null, MSG, kp.publicKey, sg);
    const verify = timeIt(doVerify, iters, warmup);
    console.log(`kg ${keygen.mean.toFixed(3)}ms  sg ${sign.mean.toFixed(3)}ms  vf ${verify.mean.toFixed(3)}ms`);
    out.push({
      id: label.toLowerCase().replace(/[^a-z0-9]/g, '_'), label,
      category: 'classical', quantum_safe: false,
      keygen, sign, verify,
      sizes: { publicKey: kp.publicKey.export({ type: 'spki', format: 'der' }).length,
               secretKey: kp.privateKey.export({ type: 'pkcs8', format: 'der' }).length,
               signature: sg.length, seed: null },
      note: 'native OpenSSL - different substrate from the PQ schemes',
    });
  }
  return out;
}

function table(rows) {
  const pad = (s, n) => String(s).padEnd(n);
  const rt = (s, n) => String(s).padStart(n);
  console.log('\n' + '='.repeat(96));
  console.log('TIMING (ms)');
  console.log('='.repeat(96));
  console.log(pad('scheme', 16) + rt('keygen', 11) + rt('sign', 11) +
              rt('verify', 11) + rt('vf p95', 10) + rt('vf 95% CI', 24) + rt('n', 7));
  console.log('-'.repeat(96));
  for (const r of rows) {
    const ci = `[${r.verify.ci95[0].toFixed(4)}, ${r.verify.ci95[1].toFixed(4)}]`;
    console.log(
      pad(r.label, 16) +
      rt(r.keygen.mean.toFixed(4), 11) +
      rt(r.sign.mean.toFixed(4), 11) +
      rt(r.verify.mean.toFixed(4), 11) +
      rt(r.verify.p95.toFixed(4), 10) +
      rt(ci, 24) + rt(r.verify.n, 7));
  }

  console.log('\n' + '='.repeat(96));
  console.log('SIZES (bytes) - for firmware update these often matter more than speed');
  console.log('='.repeat(96));
  console.log(pad('scheme', 16) + rt('public key', 12) + rt('secret key', 12) +
              rt('signature', 12) + rt('sig vs ECDSA', 14));
  console.log('-'.repeat(96));
  const ec = rows.find(r => r.id.startsWith('ecdsa'));
  for (const r of rows) {
    const ratio = ec ? (r.sizes.signature / ec.sizes.signature).toFixed(1) + 'x' : '-';
    console.log(pad(r.label, 16) + rt(r.sizes.publicKey, 12) +
                rt(r.sizes.secretKey, 12) + rt(r.sizes.signature, 12) + rt(ratio, 14));
  }

  const pq = rows.filter(r => r.quantum_safe);
  const chosen = rows.find(r => r.id === 'ml_dsa87');
  if (chosen && pq.length > 1) {
    console.log('\n' + '='.repeat(96));
    console.log('ML-DSA-87 RELATIVE TO OTHER PQ SCHEMES (>1 means ML-DSA-87 is slower/larger)');
    console.log('='.repeat(96));
    console.log(pad('vs', 16) + rt('keygen', 11) + rt('sign', 11) +
                rt('verify', 11) + rt('sig size', 11));
    console.log('-'.repeat(96));
    for (const r of pq) {
      if (r.id === 'ml_dsa87') continue;
      console.log(pad(r.label, 16) +
        rt((chosen.keygen.mean / r.keygen.mean).toFixed(2) + 'x', 11) +
        rt((chosen.sign.mean / r.sign.mean).toFixed(2) + 'x', 11) +
        rt((chosen.verify.mean / r.verify.mean).toFixed(2) + 'x', 11) +
        rt((chosen.sizes.signature / r.sizes.signature).toFixed(2) + 'x', 11));
    }
  }
}

const argv = process.argv.slice(2);
const arg = (f, d) => { const i = argv.indexOf(f); return i < 0 ? d : argv[i + 1]; };
const baseIter = parseInt(arg('--iter', '100'), 10);
const quick = argv.includes('--quick');
const only = arg('--only', null);

let list = SCHEMES;
if (quick) list = list.filter(s => !s.slow);
if (only) {
  const want = only.split(',').map(x => x.trim());
  list = list.filter(s => want.includes(s.id));
}

console.log('post-quantum signature benchmark');
console.log(`host      : ${os.hostname()}  ${os.arch()} ${os.platform()}`);
console.log(`cpu       : ${os.cpus()[0].model}  x${os.cpus().length}`);
console.log(`memory    : ${(os.totalmem() / 1073741824).toFixed(1)} GB`);
console.log(`node      : ${process.version}`);
console.log(`base iter : ${baseIter}  (scaled per scheme)\n`);

const rss0 = process.memoryUsage().rss;
const t0 = Date.now();
const rows = [];

console.log('post-quantum:');
for (const sc of list) {
  try { rows.push(benchScheme(sc, baseIter)); }
  catch (e) { console.log(`SKIPPED (${e.message})`); }
}

if (!only) {
  console.log('\nclassical baselines (different substrate - see note):');
  rows.push(...benchClassical(baseIter));
}

table(rows);

const rssMB = (process.memoryUsage().rss - rss0) / 1048576;
console.log(`\nelapsed ${((Date.now() - t0) / 1000).toFixed(1)}s   RSS growth ${rssMB.toFixed(1)} MB`);
console.log('NOTE: classical rows use native OpenSSL; PQ rows use pure JS.');
console.log('      Do not present them as a like-for-like speed comparison.');
console.log('      LMS/XMSS (CNSA 2.0 for firmware signing) are stateful and');
console.log('      not benchmarked here - discuss in the paper.');

const report = {
  timestamp: new Date().toISOString(),
  host: { hostname: os.hostname(), arch: os.arch(), platform: os.platform(),
          cpu: os.cpus()[0].model, cores: os.cpus().length,
          memory_gb: +(os.totalmem() / 1073741824).toFixed(2),
          node: process.version, kernel: os.release() },
  config: { base_iterations: baseIter, message_bytes: MSG.length },
  results: rows,
  caveats: [
    'PQ schemes: pure-JS @noble/post-quantum. Classical: native OpenSSL.',
    'Cross-substrate timings are not directly comparable.',
    'LMS/XMSS omitted: stateful, incompatible with multi-publisher setting.',
  ],
};
const fn = `pqc-bench-${os.hostname()}-${Date.now()}.json`;
fs.writeFileSync(fn, JSON.stringify(report, null, 2));
console.log(`\nsaved: ${fn}`);
