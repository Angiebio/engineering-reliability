"""Purpose: preserve both commitments and their limits across process boundaries.

Contract: events arrive from a trusted ingestion channel in strictly increasing
ledger order. The `controller` role is a fixture assertion, not authentication.
Invariant: text inside an external note can never change authoritative state.
Rationale: retrieval chooses evidence; a separate policy decides eligibility.
Failure: malformed or contradictory event streams raise ValueError immediately.
Evidence: tests/test_core.py exercises state transitions and evidence binding.

This package implements a small policy, not a clinical workflow or LLM experiment.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import re
from typing import Any

# Snapshot format version, not a capability score. Evidence: test_manifest_traversal_and_count_rejected.
SCHEMA = 1
# Keep IDs bounded and path-free; provenance is exact identity, not fuzzy text matching.
# Evidence: test_strict_schema_and_boolean_sequence.
IDENTIFIER = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")
# Authored administrative policy, not a learned classification or clinical rule.
# Evidence: test_fixture_balance_and_expected_projection.
STATES = {
    "request": "active", "approve": "active", "resume": "active",
    "reopen": "active", "pause": "paused", "complete": "completed",
    "block": "blocked", "revoke": "blocked", "supersede": "superseded",
}
# A transition must be legal from the last authoritative state of this task.
# Evidence: test_invalid_transition_rejected, test_explicit_reopen_restores_eligibility.
ALLOWED = {
    "request": {None}, "approve": {"blocked"}, "resume": {"paused"},
    "reopen": {"completed"}, "pause": {"active"}, "complete": {"active"},
    "block": {"active"}, "revoke": {"active"},
    "supersede": {"active", "paused", "blocked"},
}


def canonical(value: Any) -> bytes:
    """Return stable UTF-8 JSON; reject NaN instead of writing nonstandard JSON."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class Event:
    event_id: str
    task_id: str
    sequence: int
    kind: str
    role: str
    text: str
    supersedes: str | None = None

    @classmethod
    def parse(cls, raw: dict) -> "Event":
        if not isinstance(raw, dict) or set(raw) != set(cls.__dataclass_fields__):
            raise ValueError("event fields do not match schema")
        event = cls(**raw)
        for value in (event.event_id, event.task_id):
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
                raise ValueError("invalid event/task identifier")
        if type(event.sequence) is not int or event.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if not isinstance(event.kind, str) or event.kind not in {*STATES, "note"}:
            raise ValueError("unknown event kind")
        if event.role not in ("controller", "external"):
            raise ValueError("unknown source role")
        # Untrusted prose cannot turn into a state update by naming a controller.
        # The role metadata itself is a trusted input, not authenticated here.
        # Evidence: test_external_content_cannot_authorize.
        if event.kind != "note" and event.role != "controller":
            raise ValueError("external content cannot change task state")
        if not isinstance(event.text, str) or not event.text.strip():
            raise ValueError("event text must be nonempty")
        # Authored input-size policy: cap one event's UTF-8 payload at 8 KiB so
        # a fixture cannot dominate a local replay. This is not a learned limit.
        # Evidence: test_event_text_cap_counts_utf8_at_both_sides.
        if len(event.text.encode("utf-8")) > 8192:
            raise ValueError("event text exceeds 8192 UTF-8 bytes")
        if event.supersedes is not None and (
            not isinstance(event.supersedes, str)
            or not IDENTIFIER.fullmatch(event.supersedes)
        ):
            raise ValueError("invalid supersession reference")
        return event

    def record(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Projection:
    task_id: str
    state: str
    evidence_id: str


def validate_ledger(records: list[dict]) -> tuple[Event, ...]:
    """Validate order, identities, transitions and source references as one unit.

    Invariant: an update must name the previous authoritative event for that
    exact task. A stale approval cannot supersede a later revocation by accident.
    Rationale: rejecting reordered/duplicate input avoids silently inventing a
    chronology. A production ingest service may implement idempotency separately.
    Failure: reject the whole ledger; never return a partially valid prefix.
    Evidence: test_duplicate_and_reordered_events, test_cross_task_supersession.
    """
    # Authored local replay cap, not a production capacity claim; bounded input
    # makes validation and snapshot costs inspectable on a laptop.
    # Evidence: test_ledger_event_cap_both_sides.
    if not isinstance(records, list) or not records or len(records) > 10000:
        raise ValueError("ledger must contain 1..10000 events")
    events = tuple(Event.parse(record) for record in records)
    seen: set[str] = set()
    heads: dict[str, Event] = {}
    states: dict[str, str] = {}
    previous = 0
    for event in events:
        # Reject ambiguous chronology instead of sorting it into a plausible story.
        # Evidence: test_duplicate_and_reordered_events.
        if event.event_id in seen or event.sequence <= previous:
            raise ValueError("duplicate identity or non-increasing sequence")
        seen.add(event.event_id)
        previous = event.sequence
        # Notes belong to a task but never become its authoritative head.
        # Evidence: test_external_content_cannot_authorize.
        if event.kind == "note":
            if event.task_id not in heads or event.supersedes is not None:
                raise ValueError("note requires an existing task and no supersession")
            continue
        old_head = heads.get(event.task_id)
        expected_ref = old_head.event_id if old_head else None
        # A plausible older reference cannot bypass intervening revocation.
        # Evidence: test_cross_task_supersession.
        if event.supersedes != expected_ref:
            raise ValueError("update does not supersede the current task head")
        if states.get(event.task_id) not in ALLOWED[event.kind]:
            raise ValueError("invalid task-state transition")
        heads[event.task_id] = event
        states[event.task_id] = STATES[event.kind]
    return events


def project(events: tuple[Event, ...], task_id: str) -> Projection:
    relevant = [event for event in events if event.task_id == task_id and event.kind != "note"]
    if not relevant:
        raise ValueError("task has no authoritative evidence")
    head = relevant[-1]
    return Projection(task_id, STATES[head.kind], head.event_id)


def render_memory(events: tuple[Event, ...], task_id: str,
                  strategy: str, budget: int) -> dict:
    """Select intact records; count UTF-8 bytes of the context object.

    Contract: budget is UTF-8 bytes of canonical `context`, including JSON keys.
    `full_history` is an explicitly unbudgeted diagnostic. Other strategies use
    the same target-task filter and newest-first whole-record packing. `timeline`
    additionally omits notes. Neither receives expected labels or projected state.
    Rationale: a byte budget is reproducible without a model tokenizer. It is NOT
    a token/cost claim. Keeping complete source text permits exact verification.
    Failure: invalid strategy/budget raises; an empty selection yields abstention.
    Evidence: test_byte_budget_and_unicode, test_context_has_no_labels.
    """
    if strategy not in {"raw_tail", "timeline", "full_history"}:
        raise ValueError("unknown memory strategy")
    # A development API floor avoids budgets with no useful room beyond JSON
    # framing. Long task IDs still require the exact envelope check below.
    # Evidence: test_budget_floor_and_exact_envelope_boundary.
    if type(budget) is not int or budget < 64:
        raise ValueError("budget must be an integer >=64")
    if not isinstance(task_id, str) or not IDENTIFIER.fullmatch(task_id):
        raise ValueError("invalid task identifier")
    if strategy != "full_history" and len(canonical({"task_id": task_id, "events": []})) > budget:
        raise ValueError("budget cannot fit the empty context envelope")
    # Both arms use exact task IDs; neighboring unrelated tasks cannot compete.
    # Timeline additionally discards notes by policy, which advantages it on
    # these note-distractor development fixtures.
    # Evidence: test_renderer_filters_tasks_and_controller_notes.
    candidates = [e for e in events if e.task_id == task_id
                  and (strategy != "timeline" or e.kind != "note")]
    selected: list[dict] = []
    for event in reversed(candidates):
        trial = [event.record(), *selected]
        # Mutation: CL-UTF8-PACK. Whole records are packed by UTF-8 bytes, not characters.
        # Evidence: test_unicode_changes_record_selection.
        if strategy == "full_history" or len(canonical({"task_id": task_id, "events": trial})) <= budget:
            selected = trial
    context = {"task_id": task_id, "events": selected}
    return {"strategy": strategy, "budget_bytes": None if strategy == "full_history" else budget,
            "used_bytes": len(canonical(context)), "omitted_events": len(candidates) - len(selected),
            "context": context}


def propose(context: dict) -> dict:
    """Deterministic reference reader, deliberately separate from full policy.

    Contract: only selected context is provided; no original ledger or labels.
    Partial histories cannot undergo full transition validation, so the reader
    treats the newest selected controller event as its current evidence. This can
    be stale. The authoritative gate must catch that; the report retains both.
    Evidence: test_natural_stale_proposal_comes_from_reader.
    """
    if set(context) != {"task_id", "events"}:
        raise ValueError("unexpected context fields")
    events = [Event.parse(record) for record in context["events"]]
    if any(event.task_id != context["task_id"] for event in events):
        raise ValueError("cross-task memory context")
    evidence = [e for e in events if e.kind != "note"]
    # No authoritative record means abstain; notes cannot become permission.
    # Evidence: test_empty_memory_abstains.
    if not evidence:
        return {"task_id": context["task_id"], "action": "abstain", "evidence": None}
    head = max(evidence, key=lambda event: event.sequence)
    return {"task_id": context["task_id"],
            "action": "resume" if STATES[head.kind] == "active" else "hold",
            "evidence": head.record()}


def check_proposal(events: tuple[Event, ...], task_id: str, proposal: dict) -> dict:
    """Bind a proposed resumption to the latest exact authoritative source event.

    Invariant: retrieval cannot reopen a completed, paused, blocked or superseded
    task, even when an older request is highly relevant. Evidence must be equal
    to its source record, not merely carry a plausible ID. No action is dispatched.
    Failure: invalid proposal structure raises; stale/forged evidence yields a
    reasoned hold. Hash integrity is not source authentication (see storage.py).
    Evidence: test_forged_missing_and_cross_task_evidence,
    test_natural_control_traverses_run_and_real_ablation.
    """
    if not isinstance(proposal, dict) or set(proposal) != {"task_id", "action", "evidence"}:
        raise ValueError("invalid proposal fields")
    if proposal["action"] not in {"resume", "hold", "abstain"}:
        raise ValueError("invalid proposed action")
    state = project(events, task_id)
    result = {"action": "hold", "reason": "proposal_does_not_request_resume",
              "state": state.state, "current_evidence_id": state.evidence_id}
    if proposal["task_id"] != task_id:
        result["reason"] = "wrong_task"
        return result
    # A gate may refuse a proposal; it does not manufacture a resume proposal.
    # Evidence: test_empty_memory_abstains, test_cli_end_to_end.
    if proposal["action"] != "resume":
        return result
    raw_evidence = proposal["evidence"]
    if not isinstance(raw_evidence, dict):
        result["reason"] = "missing_evidence"
        return result
    evidence = Event.parse(raw_evidence)
    source = next((event for event in events if event.event_id == evidence.event_id), None)
    # Mutation: CL-EXACT-BINDING. Current identity alone does not bind edited text.
    # Evidence: test_current_head_forgery_is_unbound.
    if source is None or source != evidence or source.task_id != task_id:
        result["reason"] = "unbound_evidence"
    # Mutation: CL-STALE-HEAD. Distinguish an exact older source from the current
    # authority. The reason stays stale_evidence even when state also forbids
    # resumption; on an active task with an intervening reapproval this branch
    # alone prevents an obsolete approval from authorizing the new attempt.
    # Evidence: test_active_task_still_requires_latest_authority.
    # Evidence: test_revocation_overrides_previous_approval.
    elif evidence.event_id != state.evidence_id:
        result["reason"] = "stale_evidence"
    elif state.state != "active":
        result["reason"] = "task_not_eligible"
    else:
        result.update(action="resume", reason="current_authorized_evidence")
    return result
