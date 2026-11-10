#!/usr/bin/env python3
"""
Market Intelligence Lab — High-Performance Stream Prefix & Microsecond/Millisecond Timestamp Formatter
Usage: python3 scripts/prefix_stream.py <TAG> <COLOR>
"""
import sys
from datetime import datetime

TAG = sys.argv[1] if len(sys.argv) > 1 else "[LOG]"
COLOR = sys.argv[2] if len(sys.argv) > 2 else "cyan"

COLORS = {
    "cyan": "\033[1;36m",
    "magenta": "\033[1;35m",
    "yellow": "\033[1;33m",
    "green": "\033[1;32m",
    "blue": "\033[1;34m",
    "red": "\033[1;31m",
    "dim": "\033[2m",
    "reset": "\033[0m"
}

c = COLORS.get(COLOR.lower(), COLORS["cyan"])
dim = COLORS["dim"]
reset = COLORS["reset"]

try:
    for line in iter(sys.stdin.readline, ""):
        clean = line.rstrip("\r\n")
        if not clean:
            continue
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        sys.stdout.write(f"{dim}{ts}{reset} {c}{TAG:<16}{reset} │ {clean}\n")
        sys.stdout.flush()
except (KeyboardInterrupt, BrokenPipeError):
    pass
sys.exit(0)
