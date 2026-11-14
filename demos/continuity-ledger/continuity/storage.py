"""Purpose: store immutable-by-API, content-addressed ledger snapshots.

Contract: SHA-256 detects corruption relative to a separately retained expected
digest. It does not authenticate an actor, prevent a privileged writer replacing
both manifest and data, or provide a concurrent multi-writer event database.
Invariant: readers never accept a missing, altered or mismatched artifact.
Rationale: one content-addressed file avoids a two-file publication transaction.
Failure: exclusive creation refuses replacement; readers validate before use.
Evidence: tests/test_core.py::test_integrity_and_replacement and subprocess tests.
"""

import hashlib
import json
from pathlib import Path
from .core import SCHEMA, canonical, validate_ledger


def persist(directory: Path, records: list[dict]) -> dict:
    validate_ledger(records)
    content = canonical({"schema": SCHEMA, "events": records})
    checksum = hashlib.sha256(content).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (checksum + ".json")
    try:
        with path.open("xb") as target:
            target.write(content)
            target.flush()
            import os
            os.fsync(target.fileno())
    except FileExistsError:
        if path.read_bytes() != content:
            raise ValueError("content-address collision or corrupt existing snapshot")
    return {"schema": SCHEMA, "sha256": checksum, "filename": path.name,
            "byte_count": len(content), "event_count": len(records)}


def restore(directory: Path, manifest: dict):
    if set(manifest) != {"schema", "sha256", "filename", "byte_count", "event_count"}:
        raise ValueError("invalid manifest fields")
    checksum = manifest["sha256"]
    if (not isinstance(checksum, str) or len(checksum) != 64
            or any(c not in "0123456789abcdef" for c in checksum)
            or manifest["filename"] != checksum + ".json"
            or type(manifest["schema"]) is not int or manifest["schema"] != SCHEMA):
        raise ValueError("invalid manifest identity")
    for field in ("byte_count", "event_count"):
        if type(manifest[field]) is not int or manifest[field] < 1:
            raise ValueError("invalid manifest count")
    content = (directory / manifest["filename"]).read_bytes()
    if len(content) != manifest["byte_count"] or hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("snapshot integrity check failed")
    data = json.loads(content.decode("utf-8"))
    if set(data) != {"schema", "events"} or data["schema"] != SCHEMA:
        raise ValueError("snapshot schema mismatch")
    events = validate_ledger(data["events"])
    if len(events) != manifest["event_count"]:
        raise ValueError("snapshot event count mismatch")
    return events
