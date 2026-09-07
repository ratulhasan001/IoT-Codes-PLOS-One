import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pip install pyserial")

SOURCES = ["ACC_X", "ACC_Y", "ACC_Z", "LIGHT", "SOUND", "HALL"]
PROGRESS_EVERY = 2.0
FLUSH_EVERY = 500

def fmt_dur(sec):
    if sec != sec or sec < 0 or sec == float("inf"):
        return "--:--"
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def progress(got, n, t0, bad):
    el = time.time() - t0
    rate = got / el if el > 0 else 0
    eta = (n - got) / rate if rate > 0 else float("inf")
    pct = 100.0 * got / n
    bar = "#" * int(pct / 5) + "." * (20 - int(pct / 5))
    line = (f"\r  [{bar}] {pct:5.1f}%  {got:>9,}/{n:,}  "
            f"{rate:>6.1f}/s  elapsed {fmt_dur(el)}  eta {fmt_dur(eta)}")
    if bad:
        line += f"  bad={bad}"
    sys.stdout.write(line + "   ")
    sys.stdout.flush()

def capture(port, baud, mode, n, out, node):
    cmd = {"analog": b"R", "jitter": b"J", "restart": b"B"}[mode]
    prefix = {"analog": "RAW,", "jitter": "JRAW,", "restart": "RST,"}[mode]
    want = 1 if mode == "jitter" else 6
    append = (mode == "restart")

    got, bad, t0 = 0, 0, time.time()
    interrupted = False

    with serial.Serial(port, baud, timeout=15) as ser:
        time.sleep(2)
        ser.reset_input_buffer()
        ser.write(cmd)
        print(f"mode={mode}  target={n:,}  -> {out}")
        if mode == "jitter":
            print(f"jitter runs at ~62 samples/s, expect ~{fmt_dur(n/62.0)}.")
        print("Ctrl-C stops early and keeps what has been collected.\n")

        f = open(out, "a" if append else "w")
        try:
            if not append or f.tell() == 0:
                if mode == "jitter":
                    f.write("idx,tcnt1\n")
                else:
                    f.write("idx," + ",".join(SOURCES) +
                            (",node,row\n" if append else "\n"))

            row_id = int(t0)
            last_print = 0.0
            while got < n:
                line = ser.readline().decode("ascii", errors="replace").strip()
                if not line:
                    if mode == "restart":
                        break
                    continue
                if line.startswith("EVT,RESTART_ROW_END"):
                    break
                if not line.startswith(prefix):
                    continue
                vals = line[len(prefix):].split(",")
                if len(vals) != want or not all(v.isdigit() for v in vals):
                    bad += 1
                    continue
                suffix = f",{node},{row_id}" if append else ""
                f.write(f"{got}," + ",".join(vals) + suffix + "\n")
                got += 1

                if got % FLUSH_EVERY == 0:
                    f.flush()

                now = time.time()
                if now - last_print >= PROGRESS_EVERY:
                    progress(got, n, t0, bad)
                    last_print = now

        except KeyboardInterrupt:
            interrupted = True
        finally:
            f.flush()
            f.close()
            try:
                ser.write(b"S")
            except Exception:
                pass

    dt = time.time() - t0
    progress(got, n, t0, bad)
    print("\n")
    if interrupted:
        print("STOPPED EARLY by user.")
    print(f"{got:,} samples in {fmt_dur(dt)} "
          f"({got/dt if dt else 0:.1f}/s), {bad} malformed")
    print(f"saved: {out}")
    if bad > max(10, got * 0.001):
        print("WARNING: >0.1% malformed lines. Check baud rate and cable.")
    if got < n:
        print(f"NOTE: {n-got:,} short of target. SP 800-90B wants 1,000,000 "
              f"for a publishable estimate.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/cu.usbmodem1101")
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--mode", choices=["analog", "jitter", "restart"],
                    default="analog")
    ap.add_argument("-n", type=int, default=1000000)
    ap.add_argument("-o", "--out", default="raw_analog.csv")
    ap.add_argument("--node", default="node-01")
    a = ap.parse_args()
    if a.mode == "restart":
        a.n = 1000
    capture(a.port, a.baud, a.mode, a.n, a.out, a.node)
