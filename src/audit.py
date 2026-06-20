from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from .models import AnalysisResult
from .paths import LOG_DIR


def write_audit_event(source_text: str, result: AnalysisResult) -> str:
    """Write a PHI-minimised trace and optional encrypted break-glass source."""
    event_id = str(uuid4())
    encrypted_source_ref = _write_break_glass_source(event_id, source_text)
    event = {
        "event_id": event_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "document_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "document_type": result.document_type,
        "risk_level": result.risk_level,
        "recommended_action": result.recommended_action,
        "causal_rules": [link.to_dict() for link in result.causal_links],
        "model_name": result.model_name,
        "encrypted_source_ref": encrypted_source_ref,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")
    return event_id


def _write_break_glass_source(event_id: str, source_text: str) -> str | None:
    key = os.getenv("BREAK_GLASS_AUDIT_KEY")
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet

        encrypted = Fernet(key.encode("utf-8")).encrypt(source_text.encode("utf-8"))
    except (ImportError, ValueError):
        return None

    directory = LOG_DIR / "break_glass"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{event_id}.enc"
    path.write_bytes(encrypted)
    path.chmod(0o600)
    return str(path.relative_to(LOG_DIR))
