"""Stands for `opencode run … <prompt>`: prints the final reply text on stdout."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _common import mode, record  # noqa: E402

argv = sys.argv[1:]
text = argv[-1] if argv else sys.stdin.read()
record(text)
if mode() == "limit":
    print("Rate limit exceeded (429): too many requests", file=sys.stderr)
    sys.exit(1)
if mode() == "error":
    print("boom", file=sys.stderr)
    sys.exit(2)
print(f"done: {text[:40]}")
