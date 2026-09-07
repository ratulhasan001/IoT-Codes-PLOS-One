import argparse
import math
import os
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("pip install numpy")

def main(path, outdir):
    v = np.genfromtxt(path, delimiter=",", skip_header=1, dtype=np.int64)
    if v.ndim == 2:
        v = v[:, 1]
    n = len(v)
    if n == 0:
        sys.exit("no samples found - check the CSV")

    os.makedirs(outdir, exist_ok=True)
    print(f"\n{path}: {n:,} samples")
    print(f"  TCNT1 range {v.min()}..{v.max()}  mean {v.mean():.0f}  "
          f"sd {v.std():.0f}")
    print(f"  distinct values: {len(np.unique(v)):,} "
          f"({100*len(np.unique(v))/n:.1f}% of samples)")

    b = (v & 1).astype(np.uint8)
    p = b.mean()
    h = -math.log2(max(p, 1 - p)) if 0 < p < 1 else 0.0
    print(f"\n  raw LSB p(1) = {p:.4f}   IID upper bound H = {h:.4f}")

    pairs = b[:n // 2 * 2].reshape(-1, 2)
    keep = pairs[pairs[:, 0] != pairs[:, 1]]
    vn = keep[:, 0] if len(keep) else np.array([], dtype=np.uint8)
    if len(vn):
        pv = vn.mean()
        hv = -math.log2(max(pv, 1 - pv)) if 0 < pv < 1 else 0.0
        ret = len(vn) / len(pairs)
        print(f"  von Neumann: {len(vn):,} bits, retention {ret:.3f} "
              f"(0.500 = ideal)")
        print(f"    debiased p(1) = {pv:.4f}   IID bound H = {hv:.4f}")

    c = b.astype(float) - p
    den = (c * c).sum()
    ac = [(c[:-k] * c[k:]).sum() / den if den else 0.0 for k in range(1, 9)]
    print("  autocorr lag 1-8: " + " ".join(f"{r:+.3f}" for r in ac))
    if max(abs(r) for r in ac) > 0.05:
        print("    !! structure detected - source may not be independent")
    else:
        print("    no structure detected")

    b.tofile(f"{outdir}/JITTER_lsb.bin")
    if len(vn):
        vn.astype(np.uint8).tofile(f"{outdir}/JITTER_vn.bin")

    print(f"\nwrote {outdir}/JITTER_lsb.bin ({n:,} bytes)")
    if n < 1000000:
        print(f"NOTE: {1000000-n:,} short of the 1,000,000 SP 800-90B wants.")
    print(f"\nNext, on the Pi:")
    print(f"  scp {outdir}/JITTER_lsb.bin pi@<ip>:~/nist/")
    print(f"  ./ea_non_iid ~/nist/JITTER_lsb.bin 1\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("-o", "--outdir", default="nist")
    a = ap.parse_args()
    main(a.csv, a.outdir)
