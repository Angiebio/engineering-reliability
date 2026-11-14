"""Render auditable results with no external resources or active data execution.

Contract: JSON supplies all tables. Every interpolated data value is HTML-escaped;
scripts render inert JSON through textContent or filter existing DOM rows.
No event text enters executable code.
Evidence: test_report_escapes_untrusted_text. Visual design is an offline artifact.
"""

from html import escape
import json
from .visuals import explorer


def make_html(report: dict) -> str:
    esc = lambda value: escape(str(value), quote=True)
    summaries = []
    for name, summary in report["metrics"].items():
        summaries.append(f'<tr><th>{esc(name)}</th><td>{esc(summary["cases"])}</td>'
                         f'<td>{esc(summary["proposals_resume"])}/{esc(summary.get("eligible_cases", "unknown"))}</td>'
                         f'<td>{esc(summary["unsafe_proposals"])}/{esc(summary["ineligible_cases"])}</td>'
                         f'<td>{esc(summary["final_resume"])}/{esc(summary.get("eligible_cases", "unknown"))}</td>'
                         f'<td>{esc(summary["unsafe_final"])}/{esc(summary["ineligible_cases"])}</td>'
                         f'<td>{esc(summary["proposal_abstentions"])}/{esc(summary["cases"])}</td></tr>')
    cases = []
    for row in report["rows"]:
        tone = "ok" if row["gate"]["action"] == "resume" else "hold"
        details = {key: row[key] for key in ("memory", "proposal", "gate", "manifest", "processes")}
        cases.append(f'<article class="case" data-strategy="{esc(row["strategy"])}">'
                     f'<div class="case-head"><h3>{esc(row["case_id"])} <span>{esc(row["strategy"])}</span></h3>'
                     f'<span class="pill {tone}">{esc(row["gate"]["action"])}</span></div>'
                     f'<p>Expected state: <b>{esc(row["expected"])}</b> · reader proposed '
                     f'<b>{esc(row["proposal"]["action"])}</b> · {esc(row["memory"]["used_bytes"])} UTF-8 bytes</p>'
                     f'<p class="reason">{esc(row["gate"]["reason"])}</p>'
                     f'<details><summary>Inspect exact memory, proposal, source and process evidence</summary>'
                     f'<pre>{esc(json.dumps(details, ensure_ascii=False, indent=2))}</pre></details></article>')
    controls = "".join(f'<tr><th>{esc(c["name"])}</th><td>{esc(c["outcome"])}</td>'
                       f'<td>{esc(c["detail"])}</td></tr>' for c in report["controls"])
    count = len({r['case_id'] for r in report['rows']})
    budget = report.get('budget_bytes', 'declared')
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><title>Continuity Ledger | Evidence before resumption</title>
<style>
:root{--ink:#152b40;--muted:#526273;--paper:#f7f5ee;--line:#d1d8d8;--mint:#bde2d0;--amber:#f2dfad}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.6 system-ui,sans-serif}
header{background:var(--ink);color:var(--paper);padding:64px max(6vw,24px)}main{max-width:1180px;margin:auto;padding:36px 24px 80px}
.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:12px;font-weight:750}h1{font:clamp(42px,6vw,76px)/1.06 Georgia,serif;max-width:900px;margin:18px 0}
header p{max-width:740px;font-size:20px;color:#d8e3e7}h2{font:32px/1.2 Georgia,serif;margin:46px 0 20px}h3{font-size:18px;margin:0}h3 span{font-weight:400;color:var(--muted);font-size:14px}
.notice{border-left:5px solid #56876e;background:#e8eee7;padding:18px 22px}.architecture{display:flex;gap:12px;flex-wrap:wrap;padding:22px 0}.architecture span{border:1px solid var(--line);padding:12px;background:white}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:12px}thead{background:#e4e9e6}
.case{background:#fff;border:1px solid var(--line);padding:20px;margin:16px 0}.case-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.pill{border-radius:30px;padding:3px 12px;font-size:13px;font-weight:700}.ok{background:var(--mint)}.hold{background:var(--amber)}.case p{margin:12px 0;font-size:14px}.reason{font-family:monospace;color:var(--muted)}summary{cursor:pointer;font-weight:650;font-size:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;background:#f1f3f1;padding:16px}
select{padding:10px;font:inherit;border:1px solid var(--line);background:white}a{color:inherit}.meta{font-size:13px;color:var(--muted);overflow-wrap:anywhere}footer{margin-top:50px;border-top:1px solid var(--line);padding-top:20px}
@media(max-width:600px){header{padding:40px 24px}.case-head{align-items:flex-start}main{padding-inline:16px}.case{padding:14px}}
</style></head><body><header><div class="eyebrow">The Real Cat Labs · Engineering demonstration</div>
<h1>Remember the work.<br>Remember its limits.</h1><p>After a restart, an old request can still look relevant. A source-linked ledger checks whether the task is actually authorized to resume.</p></header><main>
<div class="notice"><b>Deterministic infrastructure demonstration.</b> ''' + str(count) + ''' original synthetic development histories, plus explicitly separate controls. No patient data, model calls or clinical actions. These results test the declared event policy; they do not measure LLM memory quality.</div>
''' + explorer(report) + '''
<h2>A visible boundary between memory and permission</h2><div class="architecture"><span>Immutable-by-API snapshot</span><span>Fresh-process restore</span><span>Budgeted memory</span><span>Fresh-process proposal</span><span>Evidence gate</span></div>
<p>The reader receives only selected records. The gate separately verifies the latest authoritative event. A remembered instruction cannot grant itself permission.</p>
<h2>Every outcome, with its denominator</h2><p>Raw tail retrieves the newest records for the target task. Timeline retrieves its newest authoritative events. Both use a ''' + esc(budget) + '''-byte context ceiling. Full history is an unbudgeted diagnostic. Resume columns use eligible tasks as their denominator; abstentions use all histories. In the original matrix there are no unsafe proposals, so every resume is eligible.</p>
<div class="table-wrap"><table><thead><tr><th>Memory</th><th>Histories</th><th>Resume proposals</th><th>Ineligible resumed before gate</th><th>Resumptions after gate</th><th>Ineligible resumed after gate</th><th>Abstentions</th></tr></thead><tbody>''' + "".join(summaries) + '''</tbody></table></div>
<h2>Try to break the boundary</h2><p>These direct gate probes identify their inputs and exact reasons. The planted row is input, not an ablation. The longer-terminal controls above rerun actual restore and propose workers with the gate enabled and bypassed; their records are in results.json.</p>
<div class="table-wrap"><table><thead><tr><th>Control</th><th>Observed outcome</th><th>Evidence</th></tr></thead><tbody>''' + controls + '''</tbody></table></div>
<h2>Open the evidence</h2><label for="strategy">Show memory strategy </label><select id="strategy"><option value="all">All strategies</option><option value="raw_tail">Raw tail</option><option value="timeline">Timeline</option><option value="full_history">Full history diagnostic</option></select>
''' + "".join(cases) + '''<footer><p><b>What this establishes:</b> the released fixtures traverse real process boundaries, verified persistence and a bound-evidence policy. A hash verifies artifact integrity relative to the retained digest; it does not authenticate an actor. Controller roles are trusted fixture inputs.</p><p><b>Next experiment:</b> freeze independently authored held-out histories, then compare pinned model proposals before the same checker. Report evidence loss, policy failures and paired regressions separately.</p><p class="meta">Protocol: ''' + esc(report.get('protocol','test')) + ''' · Runtime: ''' + esc(report["runtime"]) + '''<br>Fixture SHA-256: ''' + esc(report["fixture_sha256"]) + '''<br>Code SHA-256: ''' + esc(report["code_sha256"]) + '''</p><p><a href="results.json">Download raw results</a> · <a href="../docs/report.md">Read methods and limitations</a></p></footer></main>
<script>document.getElementById('strategy').addEventListener('change',function(){document.querySelectorAll('.case').forEach(el=>{el.hidden=this.value!=='all'&&el.dataset.strategy!==this.value;});});</script></body></html>'''
