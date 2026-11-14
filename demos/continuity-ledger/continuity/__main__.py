"""One command produces the evidence report: python -m continuity --out artifacts.

Purpose: exercise the real transport, persistence, proposal and gate call path.
Contract: labels are excluded from worker stdin and written only after workers
finish. Workers still have filesystem access: this is not an OS sandbox.
Child processes use the current interpreter,
isolated Python import mode and a 15-second timeout; no model API is contacted.
Invariant: raw proposals are recorded before gating; failures cannot be scored as
successful holds. Any unexpected worker error stops the run with a nonzero exit.
Evidence: test_subprocess_roundtrip_and_replay and test_cli_end_to_end.
"""

import argparse
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

from .core import canonical, check_proposal, digest, project, validate_ledger
from .fixtures import fixture_bank
from .diagnostics import budget_sweep, natural_histories, sweep_svg
from .report import make_html
from .storage import persist, restore

PACKAGE = Path(__file__).resolve().parent
# Development-fixture comparison point, not an optimal or held-out budget.
# Evidence: test_budget_transition_points shows the neighboring 542/746 changes.
BUDGET = 640
# Count the transport operations actually executed during this run. A formula
# based on output row counts cannot notice copied gate-off rows. Context-local
# state also keeps nested/independent runs from borrowing another run's count.
# Evidence: test_cli_end_to_end spies on transport and checks every gate-off twin.
_WORKER_CALLS = ContextVar('continuity_worker_calls', default=None)


def worker(request: dict) -> dict:
    """Cross the process boundary and surface the child's actual failure reason."""
    expected = ({'operation', 'directory', 'manifest', 'task_id', 'strategy', 'budget'}
                if request.get('operation') == 'restore' else {'operation', 'context'})
    # Mutation: CL-WORKER-SCHEMA. Extra evaluator fields must not reach stdin.
    # Evidence: test_worker_rejects_label_fields.
    if set(request) != expected:
        raise ValueError('worker input fields do not match declared operation')
    try:
        reply = subprocess.run([sys.executable, "-I", "-B", str(PACKAGE / "worker.py")],
                               input=canonical(request), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=True, timeout=15)
    except subprocess.CalledProcessError as error:
        reason = (error.stderr or b'').decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'worker {request.get("operation")} failed: {reason}') from error
    response = json.loads(reply.stdout)
    calls = _WORKER_CALLS.get()
    if calls is not None:
        calls.append(request['operation'])
    # Mutation: CL-PID-BOUNDARY. A same-process substitute is not restart evidence.
    # Evidence: test_same_process_reply_is_rejected.
    if response["pid"] == os.getpid():
        raise RuntimeError("fresh-process boundary was not crossed")
    return response


def metrics(rows: list[dict]) -> dict:
    result = {}
    for strategy in ("raw_tail", "timeline", "full_history"):
        group = [row for row in rows if row["strategy"] == strategy]
        eligible = lambda row: row["expected"] == "active"
        proposed = lambda row: row["proposal"]["action"] == "resume"
        final = lambda row: row["gate"]["action"] == "resume"
        tp = sum(eligible(row) and proposed(row) for row in group)
        fp = sum(not eligible(row) and proposed(row) for row in group)
        fn = sum(eligible(row) and not proposed(row) for row in group)
        result[strategy] = {
            "cases": len(group), "eligible_cases": sum(eligible(row) for row in group),
            "ineligible_cases": sum(not eligible(row) for row in group),
            "proposals_resume": sum(proposed(row) for row in group),
            "proposal_abstentions": sum(row["proposal"]["action"] == "abstain" for row in group),
            "unsafe_proposals": fp, "final_resume": sum(final(row) for row in group),
            "unsafe_final": sum(not eligible(row) and final(row) for row in group),
            "eligible_not_resumed": sum(eligible(row) and not final(row) for row in group),
            "proposal_f1": 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None,
            "proposal_confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn},
        }
    return result


def negative_controls(histories: list[dict]) -> list[dict]:
    """Direct gate unit probes; the displayed planted row is explicitly input.

    The actual gate-off experiment lives in run() and reruns natural failures
    through the shared transport path. These direct probes assert reason codes.
    """
    completed = next((h for h in histories if project(validate_ledger(h['events']), h['task_id']).state != 'active'), None)
    if completed is None:
        return []
    events = validate_ledger(completed["events"])
    task = completed["task_id"]
    old = next(event for event in events if event.task_id == task and event.kind == "request")
    stale = {"task_id": task, "action": "resume", "evidence": old.record()}
    gated = check_proposal(events, task, stale)
    if gated["action"] != "hold" or gated['reason'] != 'stale_evidence':
        raise RuntimeError("stale-proposal negative control did not fail")
    # Forge the current head of an eligible task so staleness cannot mask a
    # disconnected text-binding check. Evidence: test_current_head_forgery_is_unbound.
    active_events = validate_ledger([old.record()])
    forged = {**stale, "evidence": {**old.record(), "text": "Fabricated permission"}}
    altered = check_proposal(active_events, task, forged)
    missing = check_proposal(events, task, {**stale, "evidence": None})
    wrong = check_proposal(events, task, {**stale, "task_id": "other13"})
    controls = [
        {"name": "Stale request after completion", "outcome": gated["action"], "detail": gated["reason"]},
        {"name": "Proposal before gate (planted)", "outcome": stale["action"],
         "detail": "This is the authored input, not an ablation result. The actual gate-off rerun is recorded separately."},
        {"name": "Changed source text", "outcome": altered["action"], "detail": altered["reason"]},
        {"name": "Missing evidence", "outcome": missing["action"], "detail": missing["reason"]},
        {"name": "Different task identity", "outcome": wrong["action"], "detail": wrong["reason"]},
    ]
    expected_reasons = {'Stale request after completion': 'stale_evidence', 'Changed source text': 'unbound_evidence',
                        'Missing evidence': 'missing_evidence', 'Different task identity': 'wrong_task'}
    for control in controls:
        if control['name'] in expected_reasons and (control["outcome"] != "hold" or control['detail'] != expected_reasons[control['name']]):
            raise RuntimeError("negative control failed: " + control["name"])
    return controls


def replay_case(output: Path, history: dict, expected: str, strategy: str, *, gate_enabled=True) -> dict:
    """Run one real restore/propose transport pair, then the selected gate arm.

    The ablation only removes admission checking. It invokes both workers again
    and records their outputs; it never echoes a hard-coded expected action.
    Evidence: test_natural_control_traverses_run_and_real_ablation.
    """
    manifest = persist(output / 'snapshots', history['events'])
    # Mutation: CL-RESTORE-INPUT. No evaluator label belongs in this request.
    # Evidence: test_run_worker_input_contract_and_label_timing.
    restored = worker({'operation': 'restore', 'directory': str((output / 'snapshots').resolve()),
                       'manifest': manifest, 'task_id': history['task_id'], 'strategy': strategy, 'budget': BUDGET})
    memory = restored['value']
    # Mutation: CL-PROPOSE-INPUT. The reference reader sees only selected context.
    # Evidence: test_run_worker_input_contract_and_label_timing.
    proposed = worker({'operation': 'propose', 'context': memory['context']})
    proposal = proposed['value']
    authoritative = restore(output / 'snapshots', manifest)
    if gate_enabled:
        # Mutation: CL-GATE-WIRING. The shared runner must inspect exact current evidence.
        # Evidence: test_natural_control_traverses_run_and_real_ablation.
        gated = check_proposal(authoritative, history['task_id'], proposal)
    else:
        # Unsafe experiment only; no action dispatcher exists in either arm.
        # Preserve hold and abstain as well as resume: bypass removes the gate,
        # not the reader. Evidence: test_gate_off_preserves_nonresume_proposals.
        state = project(authoritative, history['task_id'])
        gated = {'action': proposal['action'], 'reason': 'gate_bypassed',
                 'state': state.state, 'current_evidence_id': state.evidence_id}
    return {'case_id': history['case_id'], 'task_id': history['task_id'], 'strategy': strategy,
            'expected': expected, 'manifest': manifest, 'memory': memory, 'proposal': proposal, 'gate': gated,
            'gate_enabled': gate_enabled,
            'processes': {'evaluator': os.getpid(), 'restore': restored['pid'], 'proposal': proposed['pid']}}


def _build(output: Path, histories: list[dict], labels: dict) -> dict:
    """Build a complete generation in a private directory before publication."""
    (output / "histories.json").write_bytes(canonical(histories))
    rows = []
    for history in histories:
        events = validate_ledger(history["events"])
        expected = labels[history["case_id"]]
        if project(events, history["task_id"]).state != expected:
            raise RuntimeError("fixture expectation disagrees with authoritative projection")
        for strategy in ("raw_tail", "timeline", "full_history"):
            rows.append(replay_case(output, history, expected, strategy))
    natural = natural_histories(histories, labels)
    natural_rows, ablations = [], []
    for history in natural:
        expected = labels[history['case_id'].removeprefix('natural-')]
        for strategy in ('raw_tail', 'timeline', 'full_history'):
            natural_rows.append(replay_case(output, history, expected, strategy))
        ablations.append(replay_case(output, history, expected, 'raw_tail', gate_enabled=False))
    # Any naturally stale resumption must be held by the same runner used above.
    # This fails when the call site is bypassed, not only when core gate code changes.
    # Evidence: test_natural_control_traverses_run_and_real_ablation.
    for row in natural_rows:
        if row['proposal']['action'] == 'resume' and row['expected'] != 'active':
            if row['gate']['action'] != 'hold' or row['gate']['reason'] != 'stale_evidence':
                raise RuntimeError('natural stale proposal escaped the replay gate')
    # Labels are emitted after all workers exit. This reduces accidental data
    # availability, but does not turn trusted local processes into a sandbox.
    # Evidence: test_run_worker_input_contract_and_label_timing.
    (output / 'labels.json').write_bytes(canonical(labels))
    (output / 'natural-histories.json').write_bytes(canonical(natural))
    source = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(PACKAGE.glob("*.py"))}
    report = {"protocol": "continuity-ledger-v2", "runtime": platform.python_version(),
              "kind": "deterministic development-fixture demonstration", "budget_unit": "UTF-8 bytes",
              "fixture_sha256": digest(histories), "labels_sha256": digest(labels),
              "code_sha256": digest(source), "code_files": source, "model_calls": 0,
              "budget_bytes": BUDGET, 'process_invocations': len(_WORKER_CALLS.get() or []),
              "metrics": metrics(rows), "controls": negative_controls(histories), "rows": rows,
              'natural_rows': natural_rows, 'gate_off_rows': ablations,
              'sweep': budget_sweep(histories, labels, reference_budget=BUDGET)}
    (output / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8", newline='\n')
    (output / "index.html").write_text(make_html(report), encoding="utf-8", newline='\n')
    (output / 'budget-sweep.json').write_bytes(canonical(report['sweep']))
    (output / 'budget-sweep.svg').write_text(sweep_svg(report['sweep']), encoding='utf-8', newline='\n')
    return report


def run(output: Path, *, histories=None, labels=None) -> dict:
    """Publish only a completed generation, keeping a failed rerun consistent.

    Only a recognized generated-artifact directory may be replaced. The previous
    complete generation is retained on failure; nothing from a failed run leaks
    into it. This single-writer rename protocol is not a concurrent server store.
    Evidence: test_failed_generation_keeps_previous_complete_artifacts,
    test_successful_rerun_prunes_orphan_snapshots.
    """
    output = Path(output)
    if output.is_symlink():
        raise ValueError('output cannot be a symlink')
    output = output.resolve()
    owned = {'histories.json', 'labels.json', 'natural-histories.json', 'results.json', 'index.html',
             'snapshots', 'budget-sweep.json', 'budget-sweep.svg'}
    if output.exists() and (not output.is_dir() or any(p.name not in owned or p.is_symlink() for p in output.iterdir())):
        raise ValueError('refusing to replace a directory containing non-artifact files')
    if histories is None and labels is None:
        histories, labels = fixture_bank()
    elif histories is None or labels is None:
        raise ValueError('histories and labels must be supplied together')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='continuity-publish-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        prepared = temporary / 'prepared'
        prepared.mkdir()
        token = _WORKER_CALLS.set([])
        try:
            result = _build(prepared, histories, labels)
        finally:
            _WORKER_CALLS.reset(token)
        previous = temporary / 'previous'
        had_previous = output.exists()
        if had_previous:
            output.rename(previous)
        try:
            prepared.rename(output)
        except BaseException:
            if had_previous:
                previous.rename(output)
            raise
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({"output": str(args.out.resolve()), "metrics": result["metrics"],
                      "controls": result["controls"]}, indent=2))


if __name__ == "__main__":
    main()
