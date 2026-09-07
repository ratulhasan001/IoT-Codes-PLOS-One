

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import serial
except ImportError:
    sys.exit("pyserial missing:  pip install pyserial")

def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

def verify_line(raw: str):

    if "*" not in raw:
        return None
    payload, _, crc_hex = raw.rpartition("*")
    try:
        expected = int(crc_hex, 16)
    except ValueError:
        return None
    if crc16_ccitt(payload.encode("ascii", errors="replace")) != expected:
        return None
    return payload

def parse_kv(fields):
    out = {}
    for f in fields:
        if "=" in f:
            k, _, v = f.partition("=")
            out[k] = v
    return out

def ntp_offset_seconds():

    try:
        r = subprocess.run(["chronyc", "tracking"], capture_output=True,
                           text=True, timeout=5)
        for line in r.stdout.splitlines():
            if "System time" in line:
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    try:
        r = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except Exception:
        return "unknown"

class Gateway:
    def __init__(self, node_id, log_path, fifo_path):
        self.node_id = node_id
        self.log_path = log_path
        self.fifo_path = fifo_path
        self.stats = {"seeds_ok": 0, "seeds_degraded": 0, "crc_drops": 0,
                      "parse_drops": 0, "telemetry": 0, "events": 0}

        self.nonce = secrets.token_bytes(32)
        self.pending_telemetry = []

    def log(self, record):
        record["node_id"] = self.node_id
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with open(self.log_path, "a") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def deliver_seed(self, seed: bytes, meta: dict):
\
\
\
\
\
\

        if not self.fifo_path:
            return False
        record = json.dumps({
            "seed_hex": seed.hex(),
            "health": meta.get("health"),
            "failed_sources": meta.get("failed_sources"),
            "entropy_bits": meta.get("entropy_bits"),
            "node_id": self.node_id,
            "telemetry": meta.get("telemetry", []),
        }, separators=(",", ":")) + "\n"
        try:
            fd = os.open(self.fifo_path, os.O_WRONLY | os.O_NONBLOCK)
            os.write(fd, record.encode("ascii"))
            os.close(fd)
            return True
        except OSError:
            return False

    def handle_seed(self, kv):
        seed_hex = kv.get("seed", "")
        try:
            seed = bytes.fromhex(seed_hex)
        except ValueError:
            self.stats["parse_drops"] += 1
            return
        if len(seed) != 32:
            self.stats["parse_drops"] += 1
            return

        healthy = kv.get("health") == "OK"
        failed = kv.get("failed", "unknown")

        commitment = hashlib.sha256(seed + self.nonce).hexdigest()

        record = {
            "type": "seed_attestation",
            "sp800_90b_health": "PASS" if healthy else "FAIL",
            "failed_sources": failed,
            "claimed_entropy_bits": int(kv.get("budget_bits", 0)),
            "seed_commitment": "0x" + commitment,
            "telemetry": self.pending_telemetry,
        }
        self.pending_telemetry = []

        if healthy:
            delivered = self.deliver_seed(seed, {
                "health": "PASS",
                "failed_sources": failed,
                "entropy_bits": record["claimed_entropy_bits"],
                "telemetry": record["telemetry"],
            })
            record["delivered_to_consumer"] = delivered
            self.stats["seeds_ok"] += 1
            print(f"[{time.strftime('%H:%M:%S')}] OK    "
                  f"entropy={record['claimed_entropy_bits']}b  "
                  f"commit={commitment[:12]}...  "
                  f"{'delivered' if delivered else 'no consumer'}")
        else:

            self.stats["seeds_degraded"] += 1
            record["delivered_to_consumer"] = False
            print(f"[{time.strftime('%H:%M:%S')}] DEGRADED  "
                  f"failed_sources={failed}  seed withheld")

        self.log(record)

        seed = None

    def handle_line(self, payload):
        fields = payload.split(",")
        kind = fields[0]

        if kind == "SEED":
            self.handle_seed(parse_kv(fields[1:]))
        elif kind == "TELEM":
            kv = parse_kv(fields[2:])
            kv["source"] = fields[1]
            self.pending_telemetry.append(kv)
            self.stats["telemetry"] += 1
        elif kind == "HEALTH":
            kv = parse_kv(fields[2:])
            kv["source"] = fields[1]
            self.log({"type": "health_dump", **kv})
        elif kind == "CONTEXT":
            self.pending_telemetry.append({"source": "BMP180_context",
                                           **parse_kv(fields[1:])})
        elif kind == "EVT":
            self.stats["events"] += 1
            self.log({"type": "device_event", "detail": fields[1:]})
            print(f"[{time.strftime('%H:%M:%S')}] EVENT {','.join(fields[1:])}")
        else:
            self.stats["parse_drops"] += 1

    def run(self, port, baud):
        self.log({"type": "gateway_start", "port": port, "baud": baud,
                  "clock": ntp_offset_seconds()})
        print(f"Gateway {self.node_id} on {port} @ {baud}")
        print(f"Log: {self.log_path}   FIFO: {self.fifo_path or '(none)'}")
        print("Seeds are delivered via FIFO only and never written to disk.\n")

        with serial.Serial(port, baud, timeout=10) as ser:
            time.sleep(2)
            ser.reset_input_buffer()
            ser.write(b"S")
            while True:
                raw = ser.readline().decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                payload = verify_line(raw)
                if payload is None:
                    self.stats["crc_drops"] += 1
                    continue
                self.handle_line(payload)

    def report(self):
        print("\n--- session stats ---")
        for k, v in self.stats.items():
            print(f"  {k:<18} {v}")
        total = self.stats["seeds_ok"] + self.stats["seeds_degraded"]
        if total:
            pct = 100.0 * self.stats["seeds_degraded"] / total
            print(f"  degraded rate      {pct:.2f}%")
        self.log({"type": "gateway_stop", "stats": self.stats})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--node-id", default="node-01")
    ap.add_argument("--log", default="entropy_log.jsonl")
    ap.add_argument("--fifo", default="/tmp/pqc_seed")
    args = ap.parse_args()

    gw = Gateway(args.node_id, args.log, args.fifo)
    try:
        gw.run(args.port, args.baud)
    except KeyboardInterrupt:
        pass
    except serial.SerialException as e:
        print(f"Serial error: {e}")
    finally:
        gw.report()

if __name__ == "__main__":
    main()
