"""Reproducible failure gallery using invented evaluation statements.

Purpose: let a reviewer inspect what the boundary accepts and rejects.
Contract: no models, network calls, clinical records, or real performance data.
Invariant: expected outcomes are checked; a mismatch makes the CLI exit nonzero.
Rationale: the demo measures policy execution, not adapter safety or model quality.
Failure: unexpected exceptions propagate; expected denials retain their reason code.
Evidence: tests/test_gate.py plus this public CLI's scenario assertions.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import platform
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import CHECK_STAGES, GateError, Registry, canonical, encoded, sha256, state_snapshot
from .visuals import explorer, ladder_svg, ladder_cards

# Fixed authored clock keeps fixture provenance reproducible, not current evidence.
# Evidence: test_public_gallery.
NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
BASELINE = b"synthetic adapter baseline v1\n"
CANDIDATE = b"synthetic adapter candidate v2\n"


def report_fixture() -> dict:
    return {"kind": "synthetic_fixture", "gain": 0.04, "regression": 0.005,
            "canaries": [{"id": key, "passed": True}
                         for key in ("privacy", "schema", "tool_boundary")]}


def write_bundle(folder: Path, report: dict | None = None, *,
                 evaluated_at: datetime = NOW, baseline: bytes = BASELINE,
                 candidate: bytes = CANDIDATE) -> str:
    """Author a fixture and return its trust anchor; never a production signer.

    Rationale: the tests deliberately write malformed fixture reports to prove
    that production parsing rejects them. allow_nan=True is confined to this
    fixture writer, never used by the registry or report output writer.
    """
    folder.mkdir(parents=True, exist_ok=True)
    values = {"candidate": ("candidate.bin", candidate),
              "baseline": ("baseline.bin", baseline),
              "report": ("evaluation.json", json.dumps(report if report is not None else report_fixture(),
                  sort_keys=True, separators=(",", ":"), allow_nan=True).encode("utf-8"))}
    artifacts = {}
    for role, (name, payload) in values.items():
        (folder / name).write_bytes(payload)
        artifacts[role] = {"file": name, "sha256": sha256(payload)}
    manifest = canonical({"schema_version": 1, "evaluated_at": evaluated_at.isoformat(),
                          "artifacts": artifacts})
    (folder / "manifest.json").write_bytes(manifest)
    return sha256(manifest)


def observed_success(state: dict) -> str:
    """Derive the claimed outcome from persisted state and serving-byte identity.

    Mutation: PG-GALLERY-OBSERVATION. Evidence: test_gallery_detects_disconnected_rollback.
    A successful call alone is insufficient: the recorded serving target and its
    actual artifact digest must establish the advertised restoration.
    """
    record = state['records'].get('candidate', {})
    baseline_serving = state['serving'] == 'baseline' and state['records']['baseline']['sha256'] == sha256(BASELINE)
    if record.get('state') == 'rolled_back' and baseline_serving:
        return 'rollback_restored'
    if record.get('state') == 'shadow' and baseline_serving:
        return 'shadow'
    return 'unexpected_persistent_state'


def run_gallery() -> dict:
    cases = []
    with tempfile.TemporaryDirectory(prefix="promotion-demo-") as temporary:
        root = Path(temporary)

        def exercise(name, expected, configure=None, action="admit", capacity=8):
            folder = root / str(len(cases))
            registry = Registry(folder / "registry.json", capacity=capacity, clock=lambda: NOW)
            registry.initialize(BASELINE)
            fixture = report_fixture()
            options = {}
            if configure:
                configure(fixture, options)
            anchor = write_bundle(folder / "bundle", fixture, **options)
            # The review anchor is captured separately before any admission.
            # Fixture author and reviewer are simulated; this is not authentication.
            (folder / 'reviewed-anchor.txt').write_text(anchor + '\n', encoding='utf-8', newline='\n')
            # Admission consumes the separately captured review file, so changing
            # that input affects the real gate, not just a decorative output.
            # Evidence: test_gallery_consumes_reviewed_anchor_file.
            reviewed_anchor = (folder / 'reviewed-anchor.txt').read_text(encoding='utf-8').strip()
            if action == "tamper_artifact":
                (folder / "bundle" / "candidate.bin").write_bytes(b"changed after review")
            if action == "tamper_manifest":
                (folder / "bundle" / "manifest.json").write_bytes(b"{}")
            initial = state_snapshot(registry.read())
            operations = []

            def perform(operation, call):
                before = registry.path.read_bytes()
                before_state = state_snapshot(registry.read())
                denial = None
                try:
                    call()
                except GateError as exc:
                    denial = exc.code
                    raise
                finally:
                    after = registry.path.read_bytes()
                    after_state = state_snapshot(registry.read())
                    operations.append({'operation': operation, 'checks': copy.deepcopy(registry.last_checks),
                                       'denial': denial, 'before_sha256': sha256(before), 'after_sha256': sha256(after),
                                       'before_state': before_state, 'after_state': after_state,
                                       'revision': registry.read()['revision']})

            try:
                perform('admit', lambda: registry.admit('candidate', folder / 'bundle', reviewed_anchor))
                if action == 'serve_shadow':
                    perform('serve', lambda: registry.transition('candidate', 'serve', 'release-manager'))
                elif action == 'unauthorized':
                    perform('approve', lambda: registry.transition('candidate', 'approve', 'model-agent'))
                elif action in ('lifecycle', 'serve_rolled_back', 'expired_serve'):
                    perform('approve', lambda: registry.transition('candidate', 'approve', 'release-manager'))
                    if action == 'expired_serve':
                        registry.clock = lambda: NOW + timedelta(days=8)
                    perform('serve', lambda: registry.transition('candidate', 'serve', 'release-manager'))
                    perform('rollback', lambda: registry.transition('candidate', 'rollback', 'release-manager'))
                    if action == 'serve_rolled_back':
                        perform('serve', lambda: registry.transition('candidate', 'serve', 'release-manager'))
                state = registry.read()
                observed = observed_success(state)
                unchanged = None
            except GateError as exc:
                observed = exc.code
                unchanged = operations[-1]['before_sha256'] == operations[-1]['after_sha256']
                if not unchanged:
                    raise AssertionError(f'{name}: denied operation changed persistent state')
            if observed != expected:
                raise AssertionError(f'{name}: expected {expected}, observed {observed}')
            state = registry.read()
            cases.append({'name': name, 'expected': expected, 'observed': observed,
                          'passed': observed == expected, 'rejection_preserved_registry': unchanged,
                          'serving': state['serving'], 'revision': state['revision'],
                          'candidate_state': state['records'].get('candidate', {}).get('state', 'not admitted'),
                          'serving_sha256': state['records'][state['serving']]['sha256'],
                          'initial_snapshot': initial, 'final_snapshot': state_snapshot(state),
                          'operations': operations, 'audit': state['audit'], 'reviewed_manifest_sha256': reviewed_anchor,
                          'presented_evaluation_report': encoded((folder / 'bundle/evaluation.json').read_bytes()),
                          'stored_evaluation_report': state['records'].get('candidate', {}).get('evaluation_report')})

        exercise("Valid evidence enters shadow", "shadow")
        exercise("High gain cannot override failed privacy canary", "canary_failed",
                 lambda r, o: (r.update(gain=0.99), r["canaries"][0].update(passed=False)))
        exercise("NaN gain", "nonfinite_json", lambda r, o: r.update(gain=float("nan")))
        exercise("Infinite regression", "nonfinite_json", lambda r, o: r.update(regression=float("inf")))
        exercise("Boolean gain", "invalid_metric", lambda r, o: r.update(gain=True))
        exercise("Negative regression", "invalid_metric", lambda r, o: r.update(regression=-0.01))
        exercise("Empty canary suite", "canary_schema", lambda r, o: r.update(canaries=[]))
        exercise("Missing mandatory canary", "missing_canary", lambda r, o: r["canaries"].pop())
        exercise("Duplicate canary", "duplicate_canary",
                 lambda r, o: r["canaries"].append(copy.deepcopy(r["canaries"][0])))
        exercise("Below required gain", "insufficient_gain", lambda r, o: r.update(gain=0.019))
        exercise("Excess regression", "excess_regression", lambda r, o: r.update(regression=0.011))
        exercise("Threshold equality is eligible", "shadow", lambda r, o: r.update(gain=0.02, regression=0.01))
        exercise("Stale evaluation", "stale_evidence", lambda r, o: o.update(evaluated_at=NOW-timedelta(days=8)))
        exercise("Wrong evaluation baseline", "stale_baseline", lambda r, o: o.update(baseline=b"other baseline"))
        exercise("Artifact changed after review", "artifact_mismatch", action="tamper_artifact")
        exercise("Manifest changed after review", "manifest_mismatch", action="tamper_manifest")
        exercise("Capacity is checked before any write", "capacity", capacity=1)
        exercise("Shadow cannot serve", "invalid_transition", action="serve_shadow")
        exercise("Approval requires the release-manager label (self-asserted; no authentication)", "unauthorized", action="unauthorized")
        exercise("Explicit approval, serve and rollback", "rollback_restored", action="lifecycle")
        exercise("Rolled-back candidate cannot be served again", "invalid_transition", action="serve_rolled_back")
        exercise("Evidence expires between approval and serving", "stale_evidence", action="expired_serve")

    package = Path(__file__).parent
    sources = {p.name: sha256(p.read_bytes()) for p in sorted(package.glob("*.py"))}
    return {"schema_version": 2, "kind": "deterministic_synthetic_policy_demonstration",
            "simulated_evaluation_time": NOW.isoformat(), "python": platform.python_version(),
            "source_sha256": sources, "test_sha256": {p.name: sha256(p.read_bytes()) for p in sorted((package.parent / "tests").glob("*")) if p.is_file()}, "check_stages": list(CHECK_STAGES), "scenario_count": len(cases),
            "passed": sum(c["passed"] for c in cases),
            "denials_preserving_state": sum(c["rejection_preserved_registry"] is True for c in cases),
            "limitations": ["Synthetic reports; no adapters were trained or measured.",
                "Canary outcomes are authored true/false statements in a synthetic report; no canary test was executed.",
                "Thresholds apply after JSON binary64 parsing; decimal values can round across a boundary.",
                "Hashes check content against a supplied trust anchor; they are not signatures.",
                "Release-manager is a trusted local caller label, not implemented authentication.",
                "Stored evaluated_at, manifest_sha256 and audit times trust the filesystem; editing evaluated_at alone can change freshness.",
                "Atomic file replacement is not a power-loss durability guarantee."],
            "cases": cases}


def render_html(result: dict) -> str:
    # Invariant: all data is escaped before insertion; fixture text is never markup.
    # Evidence: test_html_escapes_fixture_text.
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for item in result["cases"]:
        status = "Denied" if item["rejection_preserved_registry"] else "Allowed"
        audit = esc(json.dumps(item, indent=2))
        rows.append(f'<tr><td><details><summary>{esc(item["name"])}</summary><pre>{audit}</pre></details></td>'
                    f'<td><span class="tag">{status}</span></td><td><code>{esc(item["observed"])}</code></td>'
                    f'<td>{esc(item["serving"])}</td><td>Matches expected: {"yes" if item["passed"] else "no"}</td></tr>')
    limitations = "".join(f"<li>{esc(value)}</li>" for value in result["limitations"])
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Adapter promotion gate | Evidence report</title>
<style>
:root{color-scheme:light;--ink:#152c3b;--muted:#526672;--paper:#f5f4ef;--line:#c5d0ce;--accent:#246f5b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.65 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:48px 24px}header{border-top:6px solid var(--accent);padding-top:24px}
.eyebrow{text-transform:uppercase;letter-spacing:.16em;font-size:.78rem;font-weight:700;color:var(--accent)}
h1{font:clamp(2.2rem,6vw,4rem)/1.08 Georgia,serif;max-width:760px;margin:16px 0}h2{font:1.65rem Georgia,serif;margin-top:40px}
.intro{font-size:1.15rem;max-width:760px;color:var(--muted)}.stats{display:flex;gap:16px;flex-wrap:wrap;margin:30px 0}
.stat{flex:1;min-width:160px;padding:20px;border:1px solid var(--line);background:white}.stat b{display:block;font-size:2.1rem}
.flow{padding:20px;background:#e4ece7;border-left:4px solid var(--accent);font-weight:600}.table-wrap{overflow:auto}
table{min-width:950px;width:100%;border-collapse:collapse;text-align:left;background:white}th:first-child,td:first-child{min-width:270px}th,td{padding:14px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.76rem;text-transform:uppercase;letter-spacing:.08em}td:last-child{color:var(--accent);font-weight:700;font-size:.8rem}
.tag{font-size:.75rem;border:1px solid var(--line);padding:3px 7px;border-radius:3px}code{font: .82rem ui-monospace,monospace}
summary{cursor:pointer;font-weight:600}summary:focus-visible{outline:3px solid var(--accent)}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.76rem;background:#edf1ef;padding:14px;max-width:600px}
footer{border-top:1px solid var(--line);margin-top:40px;padding-top:20px;color:var(--muted);font-size:.88rem}a{color:var(--accent)}
</style></head><body><main><header><div class="eyebrow">The Real Cat Labs · Engineering evidence</div>
<h1>A better score does not authorize a release.</h1><p class="intro">An inspectable boundary between model-change evidence and serving state.
Open a scenario to see the exact decision, persistent state, and release history.</p></header>
<div class="stats"><div class="stat"><b>''' + esc(result["passed"]) + '''/''' + esc(result["scenario_count"]) + '''</b>scenario expectations met</div>
<div class="stat"><b>''' + esc(result["denials_preserving_state"]) + '''</b>denials preserved state</div><div class="stat"><b>0</b>model calls or clinical records</div></div>
<div class="flow">Architecture: trust anchor → manifest schema → freshness → artifact digests → baseline identity → report schema → metric bounds → canaries → thresholds. Explicit lifecycle calls follow admission.</div>
''' + explorer(result) + ladder_cards(result) + '''
<h2>Inspect the failure gallery</h2><p>These are authored development fixtures. “Matches expected” means the policy produced the authored outcome; it is not a model-performance score. Swipe the labeled table to inspect all columns on a phone.</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="Scrollable scenario outcomes"><table><thead><tr><th>Scenario</th><th>Decision</th><th>Reason</th><th>Serving</th><th>Check</th></tr></thead><tbody>''' + "".join(rows) + '''</tbody></table></div>
<h2>What this establishes</h2><p>The public entrypoint rejects malformed or mismatched evidence before admitting a candidate, preserves prior state on rejection, and separates eligibility from release authority.
The end-to-end case admits, approves, serves, and restores the exact previous artifact.</p><ul>''' + limitations + '''</ul>
<footer>Reproduce: <code>python -m promotion_gate.demo --output artifacts</code><br>
<a href="results.json">Machine-readable results and source hashes</a> · <a href="../docs/report.md">Methods and limitations</a><br>
Simulated evidence clock: ''' + esc(result["simulated_evaluation_time"]) + '''. Runtime: Python ''' + esc(result["python"]) + '''.</footer></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    result = run_gallery()
    # Render and validate every projection before writing a successful result.
    # Evidence: test_invalid_render_does_not_leave_success_artifacts.
    page = render_html(result)
    figure = ladder_svg(result)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "results.json").write_bytes(canonical(result) + b"\n")
    (args.output / "index.html").write_text(page, encoding="utf-8", newline="\n")
    (args.output / "gate-stages.svg").write_text(figure, encoding="utf-8", newline="\n")
    print(f"{result['passed']}/{result['scenario_count']} scenarios passed; "
          f"{result['denials_preserving_state']} denials preserved registry bytes.")
    print(f"Report: {args.output / 'index.html'}")


if __name__ == "__main__":
    main()
