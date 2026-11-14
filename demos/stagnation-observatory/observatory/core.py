"""Purpose: distinguish novel language from externally checkable task progress.

Contract: a harness supplies the task specification and pinned digests separately
from the agent's trace and artifact bytes. Per-event decisions leave; no
remediation action is dispatched.
Invariant: only a new accepted criterion adds progress. New progress, an
authorized wait declaration, and a completed task reset the idle-event count.
Changing words, artifact names or a completed milestone adds no new progress.
Rationale: repetition is a text property; progress needs a task-specific checker.
Failure: malformed traces raise ValueError; unavailable/altered evidence receives
an explicit evidence_error outcome and is never silently counted as progress.
Evidence: tests/test_core.py covers criteria, hashes, waiting and replay wiring.

The calling harness must protect spec and pinned_digests; this Python function
does not authenticate its caller. Store bytes and event role labels do not set
that policy. Exact item-ID matching demonstrates the checker's call path, not
work quality. These are synthetic administrative examples, not model evaluations.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re

# IDs are bounded syntax, not authentication or evidence of ownership.
ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
# Authored development policy: investigate on the third event without a new
# accepted milestone. This is not a held-out optimum; healthy sparse work alerts.
# Evidence: test_exact_loop, test_cadence_three_status_events_exposes_five_alerts.
STALL_WINDOW = 3
# Mutation: SO-LEXICAL-THRESHOLD. Development baseline, not a semantic-equivalence
# threshold. The value is an authored development policy, not a held-out optimum.
# Inclusive 0.88, 0.87 and 0.86 are distinguished by boundary tests.
# Evidence: test_lexical_threshold_is_inclusive_and_separates_signals.
# Evidence: test_lexical_neighbours_below_the_policy_do_not_alert.
LEXICAL_THRESHOLD = 0.88
# Fixture policy bounds each authorized wait to six ordered ticks, not seconds.
# It limits one declaration, not a sequence of separately authorized renewals.
# Evidence: test_wait_respects_boundary, test_trusted_wait_horizon_is_exact,
# test_event_wait_horizon_is_exact. Each test reaches its named check directly.
MAX_WAIT_TICKS = 6
# Authored demo resource limits, not empirical safety limits. UTF-8 bytes bound
# stored text independently of character count; event count bounds replay work.
# Evidence: test_text_and_artifact_byte_limits, test_event_count_limit.
MAX_TEXT_BYTES = 8192
MAX_TRACE_EVENTS = 10000
MAX_ARTIFACT_BYTES = 65536


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def identifier(value: object) -> bool:
    return type(value) is str and ID.fullmatch(value) is not None


@dataclass(frozen=True)
class Event:
    event_id: str
    task_id: str
    tick: int
    kind: str
    role: str
    text: str
    criterion_id: str | None
    artifact_id: str | None
    wait_until: int | None
    wake_condition: str | None

    @classmethod
    def parse(cls, value: dict) -> "Event":
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("event fields do not match schema")
        event = cls(**value)
        if not identifier(event.event_id) or not identifier(event.task_id):
            raise ValueError("invalid event or task ID")
        if type(event.tick) is not int or event.tick < 1:
            raise ValueError("tick must be a positive integer")
        if event.kind not in ("message", "result", "wait") or event.role not in ("agent", "controller"):
            raise ValueError("invalid kind or role")
        if type(event.text) is not str or not event.text.strip() or len(event.text.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError(f"event text must contain 1..{MAX_TEXT_BYTES} bytes")
        if event.kind == "result":
            if not identifier(event.criterion_id) or not identifier(event.artifact_id):
                raise ValueError("result must identify criterion and artifact")
        elif event.criterion_id is not None or event.artifact_id is not None:
            raise ValueError("only a result can carry criterion evidence")
        if event.kind == "wait":
            if event.role != "controller":
                raise ValueError("wait requires the controller role label")
            if type(event.wait_until) is not int or not event.tick < event.wait_until <= event.tick + MAX_WAIT_TICKS:
                raise ValueError("wait must have a bounded future expiry")
            if type(event.wake_condition) is not str or not event.wake_condition.strip():
                raise ValueError("wait requires an inspectable wake condition")
        elif event.wait_until is not None or event.wake_condition is not None:
            raise ValueError("only wait events can carry expiry")
        if event.kind != "wait" and event.role != "agent":
            raise ValueError("controller events are limited to wait declarations")
        return event


def validate_trace(trace: dict, *, spec: dict, pinned_digests: dict, store: dict) -> tuple[Event, ...]:
    """Validate untrusted input without accepting policy embedded in that input.

    Contract: spec and pinned_digests are harness-owned keyword inputs. Trace
    contains only identity and events; store contains only artifact bytes as
    UTF-8 text. The harness must not construct trusted inputs from agent fields.
    Failure: malformed input raises ValueError before any replay decision. A
    caller must investigate that rejection rather than interpret it as no alert.
    Evidence: test_trace_cannot_supply_policy, test_controller_label_cannot_authorize_wait.
    """
    # Agent records cannot supply the acceptance policy beside their own claims.
    # The caller must protect the separately supplied spec/pins; syntax is not auth.
    # Evidence: test_trace_cannot_supply_policy.
    if type(trace) is not dict or set(trace) != {"trace_id", "task_id", "events"}:
        raise ValueError("trace fields do not match schema")
    if not identifier(trace["trace_id"]) or not identifier(trace["task_id"]):
        raise ValueError("invalid trace or task ID")
    if type(spec) is not dict or set(spec) != {"task_id", "criteria", "waits"}:
        raise ValueError("trusted specification fields do not match schema")
    if not identifier(spec["task_id"]) or spec["task_id"] != trace["task_id"]:
        raise ValueError("trace does not match trusted task")
    criteria = spec["criteria"]
    if type(criteria) is not dict or not criteria:
        raise ValueError("task requires independent criteria")
    for key, items in criteria.items():
        if (not identifier(key) or type(items) is not list or not items
                or not all(identifier(item) for item in items) or len(set(items)) != len(items)):
            raise ValueError("criterion requires unique expected item IDs")
    if type(spec["waits"]) is not dict:
        raise ValueError("trusted wait declarations must be a dictionary")
    for key, wait in spec["waits"].items():
        if (not identifier(key) or type(wait) is not dict
                or set(wait) != {"tick", "wait_until", "wake_condition"}
                or type(wait["tick"]) is not int or wait["tick"] < 1
                or type(wait["wait_until"]) is not int
                or not wait["tick"] < wait["wait_until"] <= wait["tick"] + MAX_WAIT_TICKS
                or type(wait["wake_condition"]) is not str or not wait["wake_condition"].strip()):
            raise ValueError("invalid trusted wait declaration")
    if type(pinned_digests) is not dict:
        raise ValueError("pinned digests must be a dictionary")
    for key, digest in pinned_digests.items():
        if (not identifier(key) or type(digest) is not str
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("invalid pinned digest")
    if type(store) is not dict:
        raise ValueError("artifact store must be a dictionary")
    for key, content in store.items():
        if (not identifier(key) or type(content) is not str
                or len(content.encode("utf-8")) > MAX_ARTIFACT_BYTES):
            raise ValueError(f"artifact store entries require valid IDs and UTF-8 text of at most {MAX_ARTIFACT_BYTES} bytes; not manifests")
    records = trace["events"]
    if type(records) is not list or not 1 <= len(records) <= MAX_TRACE_EVENTS:
        raise ValueError(f"trace must contain 1..{MAX_TRACE_EVENTS} events")
    events = tuple(Event.parse(record) for record in records)
    seen, previous = set(), 0
    for event in events:
        if event.event_id in seen or event.tick <= previous:
            raise ValueError("duplicate event or non-increasing tick")
        # Accepted event order supplies the clock. An agent cannot jump to a
        # later harness wait by inventing elapsed ticks; callers assign this
        # contiguous ordinal before replay. This is order, not wall-clock time.
        # Evidence: test_agent_cannot_jump_to_a_future_authorized_wait.
        if event.tick != previous + 1:
            raise ValueError("tick must equal the next accepted event ordinal")
        if event.task_id != trace["task_id"]:
            raise ValueError("cross-task event")
        if event.criterion_id is not None and event.criterion_id not in criteria:
            raise ValueError("unknown criterion")
        if event.kind == "wait":
            declaration = {"tick": event.tick, "wait_until": event.wait_until,
                           "wake_condition": event.wake_condition}
            # A self-reported controller role is insufficient without the exact
            # harness authorization. Evidence: test_controller_label_cannot_authorize_wait.
            if spec["waits"].get(event.event_id) != declaration:
                raise ValueError("wait does not match a trusted controller declaration")
        seen.add(event.event_id)
        previous = event.tick
    return events


def inspect_evidence(event: Event, *, spec: dict, pinned_digests: dict, store: dict) -> dict:
    """Compare actual artifact bytes and items with an independent specification.

    Contract: only an exact task-and-criterion-bound set of items satisfies a
    criterion, after delivered bytes match the separately pinned harness digest.
    The agent store never supplies an expected digest or acceptance criteria.
    Invariant: a plausible file name or a 'done' assertion is insufficient.
    Rationale: this deliberately small validator proves a verifiable call path;
    a real workflow needs a checker appropriate to its own acceptance criteria.
    Accepted item IDs alone say nothing about the quality of the underlying work.
    Failure: missing/hash-invalid/malformed/wrong-task content is evidence_error;
    well-formed content that fails a criterion is a valid observed failure.
    Evidence: test_tampered_missing_and_wrong_task, test_cosmetic_is_not_progress.
    """
    content = store.get(event.artifact_id)
    result = {"status": "evidence_error", "reason": "missing_artifact", "satisfied": False,
              "artifact_id": event.artifact_id, "criterion_id": event.criterion_id}
    if content is None:
        return result
    raw = content.encode("utf-8")
    expected_digest = pinned_digests.get(event.artifact_id)
    result.update(expected_sha256=expected_digest, actual_sha256=sha256(raw), content=content)
    # An agent-supplied file without a harness pin is unavailable evidence, not
    # a request to trust the file's own hash. Evidence: test_unpinned_artifact_cannot_certify_itself.
    if expected_digest is None:
        result["reason"] = "unpinned_artifact"
        return result
    # Mutation: SO-SEPARATE-PIN. Rehashing changed store bytes cannot replace the
    # separately supplied expectation; exact pinned-byte reconstruction still passes.
    # Evidence: test_recomputed_agent_digest_cannot_replace_harness_pin.
    if sha256(raw) != expected_digest:
        result["reason"] = "artifact_digest_mismatch"
        return result
    try:
        def pairs(values):
            parsed = {}
            for key, value in values:
                if key in parsed:
                    raise ValueError("duplicate artifact key")
                parsed[key] = value
            return parsed
        # Mutation: SO-DUPLICATE-JSON. A correct last key must not conceal a
        # conflicting earlier key. Evidence: test_duplicate_json_key_with_correct_last_value_is_rejected.
        data = json.loads(content, object_pairs_hook=pairs)
    except (ValueError, TypeError, RecursionError):
        # A byte-bounded document may still exceed the JSON decoder's nesting
        # capacity. Preserve the evidence-error contract rather than crashing.
        # Evidence: test_deep_json_is_an_evidence_error.
        result["reason"] = "invalid_artifact_json"
        return result
    if (type(data) is not dict or set(data) != {"task_id", "criterion_id", "items"}
            or not identifier(data["task_id"]) or not identifier(data["criterion_id"])
            or type(data["items"]) is not list
            or not all(identifier(item) for item in data["items"])
            or len(set(data["items"])) != len(data["items"])):
        result["reason"] = "invalid_artifact_schema"
        return result
    if data["task_id"] != event.task_id:
        result["reason"] = "wrong_task_artifact"
        return result
    # Mutation: SO-CRITERION-BINDING. Identical item sets do not make a draft
    # artifact evidence for final approval. Evidence: test_artifact_cannot_complete_another_criterion_with_same_items.
    if data["criterion_id"] != event.criterion_id:
        result["reason"] = "wrong_criterion_artifact"
        return result
    expected = spec["criteria"][event.criterion_id]
    # Mutation: SO-EXACT-ITEMS. The toy contract is the exact item set, not a
    # superset containing every stage or a subset missing required items.
    # It proves matching, not work quality.
    # Evidence: test_superset_artifact_does_not_satisfy_exact_criterion.
    # Evidence: test_empty_and_partial_item_sets_do_not_complete_a_criterion.
    satisfied = set(data["items"]) == set(expected)
    result.update(status="verified" if satisfied else "criterion_not_met",
                  reason="expected_items_present" if satisfied else "items_do_not_match",
                  satisfied=satisfied, expected_items=expected, actual_items=data["items"])
    return result


def normalize(text: str) -> str:
    """Normalize case/whitespace only; changing numeric evidence stays visible."""
    return " ".join(text.casefold().split())


def replay(trace: dict, *, spec: dict, pinned_digests: dict, store: dict,
           trust_claims_ablation: bool = False) -> dict:
    """Replay without evaluation labels or a learned model.

    Contract: three agent events without a new accepted criterion trigger an
    alert unless a wait applies, all criteria are complete, or current evidence
    is invalid. Evidence errors take priority and separately require investigation;
    they never signal healthy work. Tick == expiry is expired.
    Invariant: re-presenting a completed criterion never resets the stall clock.
    Rationale: clear wait policy prevents equating externally blocked work with
    failure. Evidence errors are visible separately; they make no progress claim.
    Failure: malformed inputs abort with ValueError; callers must investigate
    rejection, not treat the absence of rows as healthy work. `trust_claims_ablation` is an explicit unsafe
    experiment: it treats result claims as progress to test validator wiring.
    Evidence: test_wait_expiry, test_replayed_milestone, test_validator_ablation.
    """
    events = validate_trace(trace, spec=spec, pinned_digests=pinned_digests, store=store)
    completed, words = set(), []
    idle, wait_until, wake = 0, None, None
    rows = []
    for event in events:
        exact = lexical = False
        similarity = 0.0
        evidence = None
        new_progress = False
        if event.kind != "wait":
            normalized = normalize(event.text)
            recent = words[-2:]
            if recent:
                similarity = max(SequenceMatcher(None, normalized, item).ratio() for item in recent)
            exact = len(recent) == 2 and all(normalized == item for item in recent)
            lexical = len(recent) == 2 and all(SequenceMatcher(None, normalized, item).ratio() >= LEXICAL_THRESHOLD for item in recent)
            words.append(normalized)
        if event.kind == "wait":
            # Mutation: SO-WAIT-RESET. A separately authorized wait explicitly
            # resets any accumulated idle events, even when declared after work.
            # Evidence: test_authorized_wait_resets_existing_idle_count.
            wait_until, wake, idle = event.wait_until, event.wake_condition, 0
            status, reason = "waiting", "controller_wait_declared"
        else:
            if event.kind == "result":
                evidence = inspect_evidence(event, spec=spec, pinned_digests=pinned_digests, store=store)
                # Mutation: SO-EVIDENCE-WIRING. Only the labeled unsafe ablation
                # may turn an unchecked claim into acceptance; normal replay uses
                # the checker result. Evidence: test_cosmetic_is_not_progress.
                satisfied = evidence["satisfied"] or trust_claims_ablation
                if satisfied and event.criterion_id not in completed:
                    completed.add(event.criterion_id)
                    new_progress = True
            # Expiry is exclusive: at the expiry tick normal monitoring resumes.
            # Evidence: test_wait_expiry.
            active_wait = wait_until is not None and event.tick < wait_until
            if new_progress:
                idle = 0
                status, reason = "progress", "new_criterion_verified" if not trust_claims_ablation else "unsafe_claim_trusted"
            # Invalid evidence requires investigation even during a wait or after
            # completion; it is never a healthy negative. Evidence: test_repeated_errors_have_explicit_priority.
            elif evidence and evidence["status"] == "evidence_error":
                if not active_wait:
                    idle += 1
                status, reason = "evidence_error", evidence["reason"]
            # Completion is terminal for idle counting, not immunity from errors.
            # Evidence: test_completed_task_does_not_stall.
            elif len(completed) == len(spec["criteria"]):
                idle = 0
                status, reason = "complete", "all_declared_criteria_verified"
            elif active_wait:
                status, reason = "waiting", "inside_declared_wait"
            else:
                idle += 1
                if idle >= STALL_WINDOW:
                    status, reason = "alert", "no_new_verified_progress"
                else:
                    status, reason = "observing", "awaiting_progress_window"
        rows.append({"event": event.__dict__, "exact_alert": exact, "lexical_alert": lexical,
                     "lexical_similarity": round(similarity, 4), "new_progress": new_progress,
                     "completed_criteria": sorted(completed), "idle_agent_events": idle,
                     "status": status, "reason": reason, "evidence": evidence,
                     "wait_until": wait_until, "wake_condition": wake,
                     "wait_active": wait_until is not None and event.tick < wait_until})
    used_artifacts = {event.artifact_id for event in events if event.artifact_id is not None}
    used_waits = {event.event_id for event in events if event.kind == 'wait'}
    # Valid unused inputs are reported, not silently treated as observations.
    # A pinned, well-formed artifact that misses the criterion remains an
    # observed failure: this API cannot infer who authored inconsistent inputs.
    # Evidence: test_unused_harness_inputs_are_explicit_diagnostics.
    diagnostics = {'unused_pins': sorted(set(pinned_digests) - used_artifacts),
                   'unused_waits': sorted(set(spec['waits']) - used_waits),
                   'unused_store_entries': sorted(set(store) - used_artifacts)}
    return {"trace_id": trace["trace_id"], "task_id": trace["task_id"], "rows": rows,
            "criteria_count": len(spec["criteria"]), "completed": sorted(completed),
            "validator_ablation": trust_claims_ablation, "input_diagnostics": diagnostics}
