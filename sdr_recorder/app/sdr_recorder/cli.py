"""Standalone receive-only test mode for PlutoSDR or generated mock IQ."""
from __future__ import annotations

import argparse
import time
import wave
from pathlib import Path

import numpy as np

from .dsp import NFMChannel
from .sdr import MockSource, PlutoSource


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("pluto", "mock"), default="mock")
    parser.add_argument("--uri", default="ip:192.168.2.1")
    parser.add_argument("--frequency", type=int, default=446_156_250)
    parser.add_argument("--center", type=int, default=446_156_250)
    parser.add_argument("--sample-rate", type=int, default=1_000_000)
    parser.add_argument("--gain-db", type=float, default=0)
    parser.add_argument("--squelch-dbfs", type=float, default=-45)
    parser.add_argument("--duration", type=float, default=10)
    parser.add_argument("--output", type=Path, default=Path("cli-test.wav"))
    args = parser.parse_args()
    if args.source == "mock":
        source = MockSource(args.center, args.sample_rate, args.gain_db, [args.frequency])
    else:
        source = PlutoSource(args.uri, args.center, args.sample_rate, args.sample_rate,
                             "manual", args.gain_db)
    channel = NFMChannel(args.frequency, args.center, args.sample_rate, 10_000, args.squelch_dbfs)
    source.open(); first = 0; saved = 0; started = time.monotonic()
    try:
        with wave.open(str(args.output), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(10_000)
            while time.monotonic() - started < args.duration:
                raw = source.read(); result = channel.process(raw, first); first += len(raw)
                if result.carrier:
                    wav.writeframesraw((result.audio * 32767).astype("<i2").tobytes())
                    saved += len(result.audio)
                print(f"\r{result.signal_dbfs:7.2f} dBFS {'OPEN' if result.carrier else 'closed'}", end="")
    finally:
        source.close()
    print(f"\nSaved {saved / 10_000:.2f} seconds to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
