"""Governed retrieval for encrypted audit source text.

Requires BREAK_GLASS_AUDIT_KEY and records the access reason before printing
the decrypted note.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paths import LOG_DIR


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()

    key = os.environ.get("BREAK_GLASS_AUDIT_KEY")
    if not key:
        raise SystemExit("BREAK_GLASS_AUDIT_KEY is not configured.")

    source_path = LOG_DIR / "break_glass" / f"{args.event_id}.enc"
    if not source_path.exists():
        raise SystemExit("No encrypted source exists for this audit event.")

    access_event = {
        "event_id": args.event_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": args.reviewer,
        "reason": args.reason,
    }
    with (LOG_DIR / "break_glass_access.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(access_event) + "\n")

    plaintext = Fernet(key.encode("utf-8")).decrypt(source_path.read_bytes())
    print(plaintext.decode("utf-8"))


if __name__ == "__main__":
    main()
