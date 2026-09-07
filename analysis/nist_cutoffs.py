import sys
import math
from decimal import Decimal, getcontext

getcontext().prec = 80

ALPHA = Decimal(2) ** -20
W_BINARY = 1024
W_NONBINARY = 512

def rct_cutoff(h: float, alpha: Decimal = ALPHA) -> int:

    if h <= 0:
        raise ValueError("H must be > 0")
    neg_log2_alpha = -math.log2(float(alpha))
    return 1 + math.ceil(neg_log2_alpha / h)

def critbinom(n: int, p: Decimal, q: Decimal) -> int:

    if p <= 0:
        return 0
    if p >= 1:
        return n

    one_minus_p = Decimal(1) - p
    ratio = p / one_minus_p
    pmf = one_minus_p ** n
    cdf = pmf
    if cdf >= q:
        return 0
    for k in range(1, n + 1):
        pmf = pmf * Decimal(n - k + 1) / Decimal(k) * ratio
        cdf += pmf
        if cdf >= q:
            return k
    return n

def apt_cutoff(h: float, w: int = W_BINARY, alpha: Decimal = ALPHA) -> int:

    p = Decimal(2) ** Decimal(-h)
    return 1 + critbinom(w, p, Decimal(1) - alpha)

def report(h_values, w=W_BINARY):
    print(f"\nalpha = 2^-20    W = {w} ({'binary' if w == 1024 else 'non-binary'})")
    print(f"{'H (bits/sample)':>16} {'RCT cutoff':>12} {'APT cutoff':>12}   "
          f"{'longest allowed run':>20}")
    print("-" * 68)
    for h in h_values:
        rct = rct_cutoff(h)
        apt = apt_cutoff(h, w)
        print(f"{h:>16.3f} {rct:>12d} {apt:>12d}   {rct - 1:>20d}")
    print()

def sketch_lines(h_analog, h_jitter, n_analog=6):

    rct_a, apt_a = rct_cutoff(h_analog), apt_cutoff(h_analog)
    rct_j, apt_j = rct_cutoff(h_jitter), apt_cutoff(h_jitter)
    rct = ", ".join([str(rct_a)] * n_analog + [str(rct_j)])
    apt = ", ".join([str(apt_a)] * n_analog + [str(apt_j)])
    mb_a, mb_j = int(round(h_analog * 1000)), int(round(h_jitter * 1000))
    mb = ", ".join([str(mb_a)] * n_analog + [str(mb_j)])
    print("Paste into entropy_source.ino:\n")
    print(f"  const uint16_t RCT_CUTOFF[NUM_SOURCES]  = {{ {rct} }};")
    print(f"  const uint16_t APT_CUTOFF[NUM_SOURCES]  = {{ {apt} }};")
    print(f"  const uint16_t H_MILLIBITS[NUM_SOURCES] = {{ {mb} }};")
    print(f"\n  // H_analog = {h_analog}, H_jitter = {h_jitter} bits/sample")
    print("  // measured via SP 800-90B non-IID estimators on raw capture\n")

if __name__ == "__main__":
    args = [float(a) for a in sys.argv[1:]]

    if args:
        report(args)
        if len(args) >= 2:
            sketch_lines(args[0], args[1])
    else:
        report([0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0])
        print("The sketch defaults assume H=0.5 (analog) and H=1.0 (jitter).")
        print("Those are assumptions, not measurements. Measure yours first:\n")
        print("  1. Arduino: send 'R', capture >= 1,000,000 samples per source")
        print("  2. Extract the LSB column per source")
        print("  3. Run NIST's ea_non_iid on each -> min-entropy H")
        print("  4. Run: python3 nist_cutoffs.py <H_analog> <H_jitter>")
        print("  5. Paste the arrays into the sketch\n")
        print("NIST reference implementation:")
        print("  https://github.com/usnistgov/SP800-90B_EntropyAssessment\n")
