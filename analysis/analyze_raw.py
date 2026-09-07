
import argparse
import math
import os
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("pip install numpy")

def min_entropy_iid(bits):
    p = bits.mean()
    return -math.log2(max(p, 1.0 - p)) if 0 < p < 1 else 0.0

def longest_run(bits):
    if len(bits) == 0:
        return 0
    change = np.flatnonzero(np.diff(bits)) + 1
    bounds = np.concatenate(([0], change, [len(bits)]))
    return int(np.diff(bounds).max())

def rct_needed(h):
    return 1 + math.ceil(20 / h) if h > 0 else 999

def main(path, outdir):
    data = np.genfromtxt(path, delimiter=",", names=True, dtype=None,
                         encoding="ascii")
    names = [n for n in data.dtype.names
             if n not in ("idx", "node", "row")]
    cols = {n: np.asarray(data[n], dtype=np.int32) for n in names}
    n = len(next(iter(cols.values())))
    print(f"\n{path}: {n:,} samples x {len(names)} sources\n")

    os.makedirs(outdir, exist_ok=True)
    lsb = {}

    print(f"{'source':<8}{'mean':>8}{'sd':>7}{'p(1)':>8}{'H_iid':>8}"
          f"{'maxrun':>8}{'RCT_C':>7}   flags")
    print("-" * 74)
    total_h = 0.0
    for s in names:
        v = cols[s]
        b = (v & 1).astype(np.uint8)
        lsb[s] = b
        h = min_entropy_iid(b)
        total_h += h
        mr = longest_run(b)
        flags = []
        if h < 0.4:
            flags.append("LOW-ENTROPY")
        if v.std() < 5:
            flags.append("LOW-VARIANCE(stuck?)")
        if abs(v.mean() - 512) < 25 and v.std() > 15:
            flags.append("FLOATING-PIN?")
        if mr > rct_needed(h):
            flags.append("run>cutoff")
        print(f"{s:<8}{v.mean():>8.1f}{v.std():>7.1f}{b.mean():>8.3f}"
              f"{h:>8.3f}{mr:>8}{rct_needed(h):>7}   {','.join(flags)}")

        b.astype(np.uint8).tofile(f"{outdir}/{s}_lsb.bin")
        (v & 0xFF).astype(np.uint8).tofile(f"{outdir}/{s}_low8.bin")

    print(f"\nIID upper bound, all sources: {total_h:.3f} bits/sample-set")
    print(f"  per 256-sample block       : {total_h*256:.0f} bits (analog only)")
    print("  NOTE: this is a CEILING. ea_non_iid will return less.\n")

    for label, mat in (("full sample value", [cols[s].astype(float) for s in names]),
                       ("LSB", [lsb[s].astype(float) for s in names])):
        print(f"Inter-source Pearson correlation ({label}):")
        c = np.corrcoef(np.vstack(mat))
        print("        " + "".join(f"{s[:5]:>8}" for s in names))
        worst = (0.0, "", "")
        for i, s in enumerate(names):
            row = "".join(f"{c[i, j]:>8.3f}" for j in range(len(names)))
            print(f"{s:<8}{row}")
            for j in range(len(names)):
                if i < j and abs(c[i, j]) > abs(worst[0]):
                    worst = (c[i, j], s, names[j])
        if abs(worst[0]) > 0.05:
            print(f"\n  !! {worst[1]} / {worst[2]} correlate at {worst[0]:+.3f}")
            print("     >0.05 means these are NOT independent sources.")
            print("     Increase ADC settling, check shared supply/ground,")
            print("     or drop one from the entropy budget.\n")
        else:
            print(f"\n  max |r| = {abs(worst[0]):.3f} - independent at this level.\n")

    print("Serial autocorrelation of LSB (lag 1-8):")
    print(f"{'source':<8}" + "".join(f"{'l'+str(k):>8}" for k in range(1, 9)))
    for s in names:
        b = lsb[s].astype(float) - lsb[s].mean()
        den = (b * b).sum()
        row = ""
        hit = False
        for k in range(1, 9):
            r = (b[:-k] * b[k:]).sum() / den if den else 0.0
            if abs(r) > 0.05:
                hit = True
            row += f"{r:>8.3f}"
        print(f"{s:<8}{row}" + ("   <-- structured" if hit else ""))

    print(f"\nNIST files in {outdir}/ . Next:")
    print(f"  ea_non_iid {outdir}/{names[0]}_lsb.bin 1")
    print("  (repeat per source; take the MINIMUM as your H)")
    print("  then: python3 nist_cutoffs.py <H_analog> <H_jitter>\n")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("-o", "--outdir", default="nist")
    a = ap.parse_args()
    main(a.csv, a.outdir)
