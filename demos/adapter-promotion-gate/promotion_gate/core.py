"""Admit evidence to shadow, then require explicit release decisions.

Purpose: make a proposed model change inspectable before it can serve requests.
Contract: local, bounded synthetic artifacts; SHA-256 trust anchor supplied by an
operator; one JSON registry protected by an exclusive writer lock.
Invariant: validation denials and failures before replacement preserve old state.
Rationale: a score is evidence about a change, not authority to deploy it. Hashes
bind the reviewed bytes; they do not authenticate an evaluator or prove its claims.
Failure: invalid evidence raises GateError; I/O errors propagate with old state
intact before atomic replacement. A crashed writer leaves a lock for inspection.
Evidence: tests/test_gate.py exercises the public admission and release paths.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

# Closed suite chosen for these development fixtures, not empirical safety.
# Evidence: test_unknown_canary_rejected_on_admit.
MANDATORY_CANARIES = frozenset({"privacy", "schema", "tool_boundary"})
# Input bound is per artifact; base64 storage has a separate registry ceiling.
# Evidence: test_largest_artifact_completes_rollback.
MAX_FILE_BYTES = 1_000_000
# Conservative audit headroom keeps an admitted artifact's remaining lifecycle
# writable. 64 IDs × bounded state names fit below 8192 bytes per audit event;
# four explicit events per candidate need at most 32768 reserved bytes per record.
# Displacement revokes serve eligibility; rollback alone can restore a predecessor.
# Evidence: test_displacement_cannot_recycle_approval,
# test_headroom_covers_all_pending_approvals, test_largest_artifact_completes_rollback.
MAX_REGISTRY_BYTES = 8_000_000
MAX_RECORDS = 64
LIFECYCLE_RESERVE_PER_RECORD = 32_768
# Seven days is authored policy, not a validated clinical freshness interval.
# Evidence: test_evidence_expires_after_approval, test_exact_freshness_boundaries.
MAX_AGE = timedelta(days=7)
# Bounded IDs make persistence and worst-case audit headroom predictable.
# Evidence: test_additional_registry_reason_codes.
ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z")
# Lowercase SHA-256 strings are content references, never signatures.
# Evidence: test_additional_admission_reason_codes.
DIGEST = re.compile(r"[a-f0-9]{64}\Z")

# Display order is architectural only. Each operation records its real sequence;
# unreached cells stay unevaluated. Evidence: test_recorded_check_stops_at_failure.
CHECK_STAGES = ("authority", "registry", "capacity", "lifecycle", "trust_anchor", "manifest",
                "evidence_age", "artifacts", "baseline", "report", "metrics",
                "canaries", "thresholds", "write")


@contextmanager
def checked(records: list, stage: str):
    """Record only a block actually entered; a denial terminates that block."""
    item = {"stage": stage, "status": "entered"}
    records.append(item)
    try:
        yield
    except GateError as exc:
        item.update(status="stopped", reason=exc.code)
        raise
    except OSError as exc:
        item.update(status="stopped", reason=type(exc).__name__)
        raise
    else:
        item["status"] = "passed"


class GateError(ValueError):
    """A structured denial, deliberately distinct from a successful result."""

    def __init__(self, code: str, detail: str):
        self.code = code
        super().__init__(f"{code}: {detail}")


def require(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise GateError(code, detail)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def parse_json(data: bytes) -> dict:
    # Invariant: duplicate keys cannot hide a contradictory evidence statement.
    # Evidence: test_duplicate_json_key and test_nonfinite_json_literal.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_key", key)
            result[key] = value
        return result

    def constant(value):
        raise GateError("nonfinite_json", value)

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=constant)
    except GateError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        raise GateError("invalid_json", str(exc)) from exc
    require(type(value) is dict, "invalid_object", "Expected a JSON object")
    return value


def bounded_read(path: Path, limit: int = MAX_FILE_BYTES) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "oversize", path.name)
    return data


def timestamp(value: object) -> datetime:
    require(type(value) is str, "invalid_timestamp", "UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateError("invalid_timestamp", value) from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0),
            "invalid_timestamp", "Explicit UTC required")
    return parsed


def fresh(evaluated_at: str, now: datetime) -> None:
    now = utc_clock(now)
    age = now - timestamp(evaluated_at)
    require(timedelta(0) <= age <= MAX_AGE, "stale_evidence",
            "Evidence must be no more than seven days old and not future dated")


def utc_clock(value: datetime) -> datetime:
    """Normalize aware injected clocks; naive clocks fail before persistence."""
    require(isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None,
            "invalid_clock", "Timezone-aware clock required")
    return value.astimezone(timezone.utc)


def number(value: object, name: str, low: float, high: float) -> float:
    # Purpose: stop NaN from bypassing every ordinary threshold comparison.
    # Contract: JSON numbers only; Python bool is explicitly excluded.
    # Invariant: every admitted metric is finite and within its declared range.
    # Rationale: `nan < minimum` is false; threshold-only validation fails open.
    # Failure: reject before any registry mutation.
    # Evidence: test_invalid_metrics_rejected_on_admit_path.
    require(type(value) in (int, float), "invalid_metric", name)
    # Check the bounded range before float coercion: an arbitrarily large JSON
    # integer must become a denial, not an OverflowError during isfinite().
    require(low <= value <= high and math.isfinite(value), "invalid_metric", name)
    return float(value)


@dataclass(frozen=True)
class Evidence:
    candidate: bytes
    baseline: bytes
    manifest_digest: str
    evaluated_at: str
    gain: float
    regression: float
    report_bytes: bytes


def evaluate(bundle: Path, trusted_digest: str, active_digest: str,
             now: datetime, checks: list | None = None) -> Evidence:
    """Validate exact bytes and record each reached policy block in execution order.

    Trust anchor is an independently supplied content reference, not a signature.
    Canary booleans are authored fixture statements, not executed safety tests.
    Metrics use JSON binary64 parsing; thresholds apply to those parsed values.
    Evidence: test_invalid_metrics_rejected_on_admit_path,
    test_unknown_canary_rejected_on_admit, test_recorded_check_stops_at_failure.
    """
    checks = checks if checks is not None else []
    with checked(checks, "trust_anchor"):
        require(type(trusted_digest) is str and DIGEST.fullmatch(trusted_digest) is not None,
                "invalid_digest", "Trust anchor must be a SHA-256 digest")
        manifest_bytes = bounded_read(bundle / "manifest.json")
        require(sha256(manifest_bytes) == trusted_digest, "manifest_mismatch",
                "Manifest differs from externally reviewed digest")
    with checked(checks, "manifest"):
        manifest = parse_json(manifest_bytes)
        require(set(manifest) == {"schema_version", "evaluated_at", "artifacts"},
                "manifest_schema", "Unexpected or missing manifest field")
        require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1,
                "manifest_schema", "Unsupported schema version")
    with checked(checks, "evidence_age"):
        fresh(manifest["evaluated_at"], now)
    with checked(checks, "artifacts"):
        artifacts = manifest["artifacts"]
        require(type(artifacts) is dict and set(artifacts) == {"candidate", "baseline", "report"},
                "artifact_schema", "Candidate, baseline and report required")
        payloads = {}
        for role, entry in artifacts.items():
            require(type(entry) is dict and set(entry) == {"file", "sha256"}, "artifact_schema", role)
            filename, digest = entry["file"], entry["sha256"]
            require(type(filename) is str and re.fullmatch(r"[a-z0-9_-]+\.(bin|json)", filename) is not None,
                    "artifact_path", "Only flat artifact filenames are accepted")
            path = bundle / filename
            require(path.resolve().parent == bundle.resolve(), "artifact_path", "Symlink leaves bundle")
            require(type(digest) is str and DIGEST.fullmatch(digest) is not None, "invalid_digest", role)
            payload = bounded_read(path)
            require(sha256(payload) == digest, "artifact_mismatch", role)
            payloads[role] = payload
    with checked(checks, "baseline"):
        require(sha256(payloads["baseline"]) == active_digest, "stale_baseline",
                "Evaluation baseline is not the currently serving artifact")
        require(payloads["candidate"] and payloads["baseline"], "empty_artifact", "Artifact is empty")
        # A renamed byte-identical artifact is not a model change.
        # Mutation: PG-UNCHANGED. Evidence: test_unchanged_candidate_rejected.
        require(payloads["candidate"] != payloads["baseline"], "unchanged_candidate", "No change to evaluate")
    with checked(checks, "report"):
        report = parse_json(payloads["report"])
        require(set(report) == {"kind", "gain", "regression", "canaries"},
                "report_schema", "Unexpected or missing report field")
        require(report["kind"] == "synthetic_fixture", "report_kind", "This demo accepts fixtures only")
    with checked(checks, "metrics"):
        # Validate through the admission path, not only the number helper in isolation.
        # Mutation: PG-METRIC-WIRING. Evidence: test_invalid_metrics_rejected_on_admit_path.
        gain = number(report["gain"], "gain", -1, 1)
        regression = number(report["regression"], "regression", 0, 1)
    with checked(checks, "canaries"):
        canaries = report["canaries"]
        require(type(canaries) is list and len(canaries) > 0, "canary_schema", "Nonempty suite required")
        seen = set()
        for canary in canaries:
            require(type(canary) is dict and set(canary) == {"id", "passed"}, "canary_schema", "Invalid canary")
            key = canary["id"]
            # Mutation: PG-CANARY-ID. Evidence: test_unknown_canary_rejected_on_admit.
            require(type(key) is str and key in MANDATORY_CANARIES, "canary_schema", "Unknown canary")
            require(key not in seen, "duplicate_canary", key)
            seen.add(key)
            require(type(canary["passed"]) is bool, "canary_schema", "Canary result must be boolean")
            require(canary["passed"], "canary_failed", key)
        require(seen == MANDATORY_CANARIES, "missing_canary", "Required suite is incomplete")
    with checked(checks, "thresholds"):
        # Thresholds are fixed development policy after binary64 parsing, not an
        # estimate of clinical benefit. Evidence: test_threshold_equality_passes.
        require(gain >= 0.02, "insufficient_gain", "Minimum gain is 0.02")
        require(regression <= 0.01, "excess_regression", "Maximum regression is 0.01")
    return Evidence(payloads["candidate"], payloads["baseline"], trusted_digest,
                    manifest["evaluated_at"], gain, regression, payloads["report"])


def encoded(data: bytes) -> dict:
    return {"sha256": sha256(data), "bytes_b64": base64.b64encode(data).decode("ascii")}


def state_snapshot(state: dict) -> dict:
    """Capture actual committed lifecycle values without reinterpreting actions."""
    return {"record_states": {key: value["state"] for key, value in state["records"].items()},
            "serving": state["serving"], "serving_sha256": state["records"][state["serving"]]["sha256"]}


class Registry:
    """Small local registry; caller identity is a trusted CLI/API input, not auth."""

    def __init__(self, path: Path, capacity: int = 8,
                 clock: Callable[[], datetime] | None = None,
                 before_replace: Callable[[], None] | None = None):
        require(type(capacity) is int and 1 <= capacity <= MAX_RECORDS, "capacity", "Capacity must be 1..64 including baseline")
        self.path = path
        self.capacity = capacity
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_replace = before_replace
        self.last_checks = []

    @contextmanager
    def _locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(self.path.suffix + ".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise GateError("registry_locked", "Another writer or an unreviewed crash lock exists") from exc
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def _write(self, state: dict) -> None:
        # Purpose: prevent an admission failure from mutating the accepted record.
        # Contract: writer lock held; proposed state validated on a private copy.
        # Invariant: before replace, readers see the whole old JSON file; afterward,
        # they see the whole new file. No truncated state is observable.
        # Rationale: validate-before-mutate fixes the predecessor's capacity bug.
        # Failure: fsync/write/injected failures propagate; a temporary file is removed.
        # Evidence: test_capacity_preserves_bytes, test_interrupted_replace_preserves_bytes.
        # Limit: file fsync + replace is not a cross-platform power-loss durability proof.
        payload = canonical(state)
        # Mutation: PG-WRITE-VALIDATION. Evidence: test_invalid_private_state_never_replaces_registry.
        self.validate_state(parse_json(payload))
        require(len(payload) <= MAX_REGISTRY_BYTES, "oversize", "Registry exceeds storage limit")
        fd, temporary = tempfile.mkstemp(prefix=".registry-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if self.before_replace:
                self.before_replace()
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def read(self) -> dict:
        """Validate a stored revision before using any lifecycle field.

        Invariant: corrupt or incomplete state cannot partially drive a release.
        Rationale: explicit shape checks keep a malformed disk record from becoming
        a late KeyError after other checks appear to have approved the transition.
        Failure: reject with a structured code; never repair or coerce disk state.
        Evidence: test_registry_schema_validation and test_registry_evidence_fields.
        Limit: the filesystem is trusted. evaluated_at, manifest_sha256 and audit
        event at values are stored metadata, not bound to retained manifest bytes.
        Editing evaluated_at alone can change freshness. Other coordinated edits
        can bypass state/digest consistency too; none of these are authentication.
        Evidence: test_trusted_disk_metadata_is_not_authenticated.
        """
        return self.validate_state(parse_json(bounded_read(self.path, MAX_REGISTRY_BYTES)))

    def validate_state(self, state: dict) -> dict:
        """Apply identical shape, artifact and audit invariants before read/write.

        The audit reconstructs lifecycle state to detect inconsistent edits. A
        trusted-filesystem adversary can still rewrite a fully consistent audit
        and state together; these checks do not authenticate storage.
        Evidence: test_audit_must_bind_lifecycle_state.
        """
        require(set(state) == {"schema_version", "revision", "serving", "records", "audit"},
                "registry_schema", "Invalid registry structure")
        require(type(state["schema_version"]) is int and state["schema_version"] == 2
                and type(state["revision"]) is int and state["revision"] >= 0,
                "registry_schema", "Invalid registry version")
        require(type(state["records"]) is dict and type(state["audit"]) is list,
                "registry_schema", "Invalid records or audit")
        require(len(state['records']) <= MAX_RECORDS, 'registry_schema', 'Record bound protects audit reservation')
        require(type(state["serving"]) is str and state["serving"] in state["records"],
                "registry_schema", "Serving record is missing")
        require("baseline" in state["records"], "rollback_missing", "Original baseline is missing")
        serving = []
        for key, record in state["records"].items():
            require(type(key) is str and ID.fullmatch(key) is not None,
                    "registry_schema", "Invalid record ID")
            require(type(record) is dict and type(record.get("state")) is str
                    and record["state"] in {"shadow", "approved", "serving", "superseded", "rolled_back"},
                    "registry_schema", "Invalid lifecycle state")
            basic = {"sha256", "bytes_b64", "state", "predecessor"}
            evidence_fields = {"baseline_sha256", "manifest_sha256", "evaluated_at", "gain", "regression", "evaluation_report"}
            require(set(record) == (basic if key == "baseline" else basic | evidence_fields),
                    "registry_schema", "Missing or unexpected record fields")
            require(type(record["sha256"]) is str and DIGEST.fullmatch(record["sha256"]) is not None
                    and type(record["bytes_b64"]) is str,
                    "registry_schema", "Invalid artifact representation")
            if key == "baseline":
                require(record["predecessor"] is None, "registry_schema", "Baseline has no predecessor")
            else:
                predecessor = record["predecessor"]
                require(type(predecessor) is str and predecessor != key,
                        "registry_schema", "Invalid predecessor")
                require(predecessor in state["records"], "rollback_missing", "Prior artifact missing")
                for field in ("baseline_sha256", "manifest_sha256"):
                    require(type(record[field]) is str and DIGEST.fullmatch(record[field]) is not None,
                            "registry_schema", "Invalid evidence digest")
                timestamp(record["evaluated_at"])
                number(record["gain"], "stored gain", -1, 1)
                number(record["regression"], "stored regression", 0, 1)
                stored = record['evaluation_report']
                require(type(stored) is dict and set(stored) == {'sha256', 'bytes_b64'},
                        'registry_schema', 'Invalid stored report')
                try:
                    report_bytes = base64.b64decode(stored['bytes_b64'], validate=True)
                except (ValueError, TypeError) as exc:
                    raise GateError('registry_integrity', 'Invalid stored report bytes') from exc
                require(sha256(report_bytes) == stored['sha256'], 'registry_integrity', 'Stored report differs')
                report = parse_json(report_bytes)
                require(set(report) == {'kind', 'gain', 'regression', 'canaries'}
                        and report['gain'] == record['gain'] and report['regression'] == record['regression'],
                        'registry_schema', 'Stored report disagrees with metrics')
            try:
                raw = base64.b64decode(record["bytes_b64"], validate=True)
                actual = sha256(raw)
            except (KeyError, ValueError, TypeError) as exc:
                raise GateError("registry_integrity", key) from exc
            require(raw and actual == record.get("sha256"), "registry_integrity", key)
            if record["state"] == "serving":
                serving.append(key)
        require(serving == [state["serving"]], "registry_schema", "Exactly one serving record required")
        for key, record in state["records"].items():
            if key != "baseline":
                require(record["baseline_sha256"] == state["records"][record["predecessor"]]["sha256"],
                        "rollback_mismatch", "Evidence baseline differs from stored predecessor")
        require(len(state["audit"]) == state["revision"], "registry_schema", "Revision count differs from audit")
        reconstructed, pointer = {'baseline': 'serving'}, 'baseline'
        for index, event in enumerate(state["audit"], 1):
            require(type(event) is dict and set(event) == {"revision", "action", "candidate", "actor", "at", "state_snapshot"},
                    "registry_schema", "Invalid audit event")
            require(type(event["revision"]) is int and event["revision"] == index,
                    "registry_schema", "Nonsequential audit revision")
            require(type(event["action"]) is str and event["action"] in {"admit_shadow", "approve", "serve", "rollback"}
                    and type(event["candidate"]) is str and event["candidate"] in state["records"]
                    and type(event["actor"]) is str and bool(event["actor"]),
                    "registry_schema", "Invalid audit fields")
            timestamp(event["at"])
            action, key = event['action'], event['candidate']
            require(event['actor'] == ('gate' if action == 'admit_shadow' else 'release-manager'),
                    'registry_schema', 'Audit actor label disagrees with action')
            if action == 'admit_shadow':
                require(key not in reconstructed and state['records'][key]['predecessor'] == pointer,
                        'registry_schema', 'Invalid admission history')
                reconstructed[key] = 'shadow'
            elif action == 'approve':
                require(reconstructed.get(key) == 'shadow', 'registry_schema', 'Approval has no shadow predecessor')
                reconstructed[key] = 'approved'
            elif action == 'serve':
                require(reconstructed.get(key) == 'approved', 'registry_schema', 'Serve has no approval')
                reconstructed[pointer], reconstructed[key], pointer = 'superseded', 'serving', key
            else:
                require(key == pointer and key != 'baseline', 'registry_schema', 'Invalid rollback history')
                reconstructed[key] = 'rolled_back'
                pointer = state['records'][key]['predecessor']
                reconstructed[pointer] = 'serving'
            expected = {'record_states': dict(reconstructed), 'serving': pointer,
                        'serving_sha256': state['records'][pointer]['sha256']}
            require(event['state_snapshot'] == expected, 'registry_schema', 'Audit snapshot disagrees with history')
        # Mutation: PG-AUDIT-BINDING. Evidence: test_audit_must_bind_lifecycle_state.
        require(state_snapshot(state) == {'record_states': reconstructed, 'serving': pointer,
                'serving_sha256': state['records'][pointer]['sha256']}, 'registry_schema', 'Audit differs from stored lifecycle')
        return state

    def initialize(self, baseline: bytes) -> None:
        require(type(baseline) is bytes and len(baseline) > 0, "empty_artifact", "Baseline required")
        require(len(baseline) <= MAX_FILE_BYTES, 'oversize', 'Baseline input exceeds bound')
        with self._locked():
            require(not self.path.exists(), "already_initialized", "Never overwrite existing state")
            record = dict(encoded(baseline), state="serving", predecessor=None)
            self._write({"schema_version": 2, "revision": 0, "serving": "baseline",
                         "records": {"baseline": record}, "audit": []})

    def _commit(self, state: dict, action: str, key: str, actor: str) -> None:
        with checked(self.last_checks, 'write'):
            instant = utc_clock(self.clock())
            state["revision"] += 1
            state["audit"].append({"revision": state["revision"], "action": action,
                                   "candidate": key, "actor": actor,
                                   "at": instant.isoformat(), "state_snapshot": state_snapshot(state)})
            if action == 'admit_shadow':
                # Admission reserves storage for the bounded remaining history.
                # Mutation: PG-HEADROOM. Evidence: test_near_full_registry_reserves_complete_lifecycle.
                reserve = len(state['records']) * LIFECYCLE_RESERVE_PER_RECORD
                require(len(canonical(state)) + reserve <= MAX_REGISTRY_BYTES,
                        'oversize', 'Admission must reserve lifecycle audit headroom')
            self._write(state)

    def admit(self, key: str, bundle: Path, trusted_digest: str) -> dict:
        """Eligibility only: every denial precedes mutation of the registry file."""
        self.last_checks = []
        with self._locked():
            with checked(self.last_checks, 'registry'):
                require(type(key) is str and ID.fullmatch(key) is not None, 'invalid_id', 'Invalid candidate ID')
                state = self.read()
                require(key not in state['records'], 'duplicate_candidate', key)
            with checked(self.last_checks, 'capacity'):
                # No tentative insertion before capacity validation.
                # Evidence: test_capacity_preserves_bytes.
                require(len(state['records']) < self.capacity, 'capacity', 'Registry capacity reached')
            active = state['records'][state['serving']]
            evidence = evaluate(bundle, trusted_digest, active['sha256'], self.clock(), self.last_checks)
            next_state = copy.deepcopy(state)
            next_state['records'][key] = dict(encoded(evidence.candidate), state='shadow',
                predecessor=state['serving'], baseline_sha256=sha256(evidence.baseline),
                manifest_sha256=evidence.manifest_digest, evaluated_at=evidence.evaluated_at,
                gain=evidence.gain, regression=evidence.regression,
                evaluation_report=encoded(evidence.report_bytes))
            self._commit(next_state, 'admit_shadow', key, 'gate')
            return copy.deepcopy(next_state['records'][key])

    def transition(self, key: str, action: str, actor: str) -> None:
        """A local role-label check is not authentication; callers supply identity.

        Shadow needs explicit approval; approved needs a fresh serve decision.
        Rollback revokes the candidate's approval and requires a new admission
        under a new ID before re-release. A displaced candidate is superseded,
        not reusable approval; rollback may restore it as the exact predecessor.
        Exact predecessor integrity is checked
        by read(), avoiding a second unreachable rollback-mismatch guard.
        Evidence: test_evidence_expires_after_approval, test_rollback_revokes_approval.
        """
        self.last_checks = []
        with checked(self.last_checks, 'authority'):
            require(actor == 'release-manager', 'unauthorized', 'Exact local release-manager label required; not authentication')
            require(action in {'approve', 'serve', 'rollback'}, 'unknown_action', action)
        with self._locked():
            with checked(self.last_checks, 'registry'):
                state = self.read()
                require(key in state['records'], 'unknown_candidate', key)
            candidate = state['records'][key]
            updated = copy.deepcopy(state)
            current = updated['records'][key]
            if action in {'approve', 'serve'}:
                with checked(self.last_checks, 'lifecycle'):
                    expected = 'shadow' if action == 'approve' else 'approved'
                    require(candidate['state'] == expected and key != 'baseline',
                            'invalid_transition', f'{action} requires {expected}')
                with checked(self.last_checks, 'evidence_age'):
                    # Serving rechecks freshness independently of past approval.
                    # Mutation: PG-SERVE-FRESHNESS. Evidence: test_evidence_expires_after_approval.
                    fresh(candidate['evaluated_at'], self.clock())
                with checked(self.last_checks, 'baseline'):
                    active = state['records'][state['serving']]
                    require(active['sha256'] == candidate['baseline_sha256'],
                            'stale_baseline', 'Serving baseline changed since evaluation')
                    # Equal bytes under a replacement ID do not restore an old
                    # predecessor's lifecycle authority. Otherwise a pending
                    # release could roll back into a previously revoked record.
                    # Evidence: test_approve_rejects_same_bytes_replacement,
                    # test_serve_rejects_same_bytes_replacement.
                    require(state['serving'] == candidate['predecessor'],
                            'stale_baseline', 'Serving predecessor identity changed since evaluation')
                if action == 'approve':
                    current['state'] = 'approved'
                else:
                    # Displacement must not mint another serve permission. Each ID
                    # has one admission/approval/serve/rollback lifecycle, bounding
                    # audit growth even when candidate bytes equal an old baseline.
                    # Evidence: test_displacement_cannot_recycle_approval,
                    # test_nested_rollback_restores_exact_predecessor.
                    updated['records'][state['serving']]['state'] = 'superseded'
                    current['state'] = 'serving'
                    updated['serving'] = key
            else:
                with checked(self.last_checks, 'lifecycle'):
                    require(state['serving'] == key and key != 'baseline', 'invalid_transition',
                            'Rollback must name the currently serving candidate')
                    predecessor = candidate['predecessor']
                    prior = updated['records'][predecessor]
                    # An incident revokes approval; merely reissuing serve must fail.
                    # Mutation: PG-ROLLBACK-REVOCATION. Evidence: test_rollback_revokes_approval.
                    current['state'] = 'rolled_back'
                    prior['state'] = 'serving'
                    updated['serving'] = predecessor
            self._commit(updated, action, key, actor)
