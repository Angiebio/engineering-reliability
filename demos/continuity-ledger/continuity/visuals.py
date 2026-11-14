"""Graphical views of recorded evidence, with no new inference or policy decisions.

Purpose: make memory loss and the proposal/authority boundary legible before code.
Contract: source events come from the recorded full-history arm; selected IDs come
from each recorded memory context. No fixture is reconstructed from its label.
Invariant: retention marks, actions, and plotted counts match the released JSON.
Rationale: a process diagram alone hides which evidence was actually discarded.
Failure: incomplete test reports omit the explorer rather than invent source data.
Evidence: tests/test_visuals.py checks source binding, budgets and script escaping.
"""
from html import escape
import json
from .diagnostics import sweep_svg, transition_brackets


def visual_payload(report: dict) -> dict:
    """Derive a presentation-only projection from complete recorded rows.

    Full history is a source reference, not an equal-budget competitor. Only the
    target task is shown; the UI says so. The selected arm's outcome remains the
    recorded outcome, even when it abstained or differs from the source reference.
    """
    sources = {}
    rows = report.get('rows', []) + report.get('natural_rows', [])
    for row in rows:
        if row.get("strategy") == "full_history" and "context" in row.get("memory", {}):
            sources[row["case_id"]] = row["memory"]["context"]["events"]
    records = []
    for row in rows:
        if row.get("case_id") not in sources or "context" not in row.get("memory", {}):
            continue
        records.append({"case_id": row["case_id"], "strategy": row["strategy"],
                        "source_events": sources[row["case_id"]],
                        "retained_ids": [event["event_id"] for event in row["memory"]["context"]["events"]],
                        "used_bytes": row["memory"]["used_bytes"],
                        "budget_bytes": row["memory"]["budget_bytes"],
                        "proposal": row["proposal"], "gate": row["gate"],
                        'expected': row.get('expected'),
                        'scope': 'outside matrix: longer terminal records' if row['case_id'].startswith('natural-') else 'original policy matrix',
                        'verdict': verdict(row)})
    return {"records": records}


def verdict(row: dict) -> str:
    """Compare the recorded decision with its separately supplied expectation."""
    if row.get('expected') is None:
        return 'expectation_unavailable'
    if row['gate']['action'] == 'resume':
        return 'correct_resume' if row['expected'] == 'active' else 'unsafe_allowed'
    if row['expected'] == 'active':
        return 'missed_eligible'
    return 'unsafe_caught' if row['proposal']['action'] == 'resume' else 'correct_hold'


def safe_json(value: object) -> str:
    # Escaping HTML delimiters prevents a source string closing a JSON script tag.
    # The browser later inserts source text with textContent, never innerHTML.
    return (json.dumps(value, ensure_ascii=True, allow_nan=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def outcome_figure(report: dict) -> str:
    """Show eligible resumptions as counted marks, with the actual denominator."""
    groups = []
    for name, summary in report.get("metrics", {}).items():
        values = [summary.get(key) for key in ("eligible_cases", "final_resume", "eligible_not_resumed")]
        if not all(type(value) is int and 0 <= value <= 1000 for value in values):
            continue
        eligible, resumed, held = values
        if eligible != resumed + held or eligible == 0:
            continue
        label = {"raw_tail": "Raw tail", "timeline": "Structured timeline",
                 "full_history": "Full history · no budget"}.get(name, name)
        marks = "".join(f'<rect x="{i * 25}" y="0" width="19" height="27" rx="3" '
                        f'fill="{"#397762" if i < resumed else "#d6dee0"}" stroke="#526273" stroke-width="1.5"/>' for i in range(eligible))
        groups.append(f'<div class="cv-outcome-row"><div><b>{escape(label)}</b><br>'
                      f'<span>{resumed}/{eligible} eligible tasks resumed</span></div>'
                      f'<svg viewBox="0 0 {eligible * 25} 27" role="img" '
                      f'aria-label="{resumed} resumed; {held} not resumed, of {eligible} eligible tasks">'
                      f'{marks}</svg></div>')
    if not groups:
        return ""
    return ('<figure class="cv-outcomes"><figcaption><b>Did eligible work survive the memory budget?</b><br>'
            'One mark per eligible task. Filled = resumed; gray = not resumed.</figcaption>'
            + "".join(groups) + '<p class="cv-caption">These counts depend on authored note lengths, the chosen byte budget and whole-record packing. '
            'Timeline excludes the notes used as distractors. The separate sweep shows the sensitivity; these are deterministic fixture outcomes, not LLM performance.</p></figure>')


def budget_explorer(report: dict) -> str:
    """A dial selects measured points; JavaScript never invents another run."""
    sweep = report.get('sweep')
    if not sweep:
        return ''
    brackets = ''.join(f'<li data-left="{point["left_bytes"]}" data-right="{point["right_bytes"]}"><b>{point["left_bytes"]}–{point["right_bytes"]} bytes</b><span>{point["before"]} → {point["after"]} eligible resumptions</span></li>'
                       for point in transition_brackets(sweep))
    return '''<section id="budget-explorer" aria-labelledby="budget-heading"><h2 id="budget-heading">Turn the budget. Watch the packing boundary.</h2>
<p>Every point below runs the actual renderer, reader and gate in-process. It is a sensitivity check on the original authored histories, separate from restart evidence.</p>
<div class="budget-chart" tabindex="0" role="region" aria-label="Budget sensitivity figure">''' + sweep_svg(sweep) + '''</div>
<label for="budget-dial">Recorded context budget <output id="budget-value"></output></label>
<input id="budget-dial" type="range" min="0" max="''' + str(len(sweep['points'])-1) + '''" value="0" aria-label="Select a recorded budget point">
<div id="budget-readout" aria-live="polite"></div><div class="budget-mobile-steps"><h3>Observed raw-tail changes</h3><p>Each bracket connects consecutive measured points. Counts between sampled budgets are not inferred.</p><ul>''' + brackets + '''</ul></div><p class="cv-caption budget-scope">The points use authored histories and whole-record packing; these are not model scores. More budget can retain distracting notes before the current instruction fits. The original matrix has no unsafe proposals by construction. In the longer-terminal family, timeline can also propose stale resumptions at smaller budgets: it needs the gate too.</p>
<p><a href="budget-sweep.svg">Download the figure with its scope</a> · <a href="budget-sweep.json">Download every measured point and case decision</a></p></section>
<script type="application/json" id="budget-data">''' + safe_json(sweep) + '''</script><script>(()=>{const sweep=JSON.parse(document.getElementById('budget-data').textContent);const points=sweep.points;const dial=document.getElementById('budget-dial');const initial=points.findIndex(p=>p.budget_bytes===sweep.reference_budget_bytes);dial.value=initial<0?0:initial;function show(){const point=points[Number(dial.value)];document.getElementById('budget-value').textContent=point.budget_bytes+' UTF-8 bytes';const root=document.getElementById('budget-readout');root.replaceChildren();Object.entries(point.strategies).forEach(([name,m])=>{const p=document.createElement('p');p.dataset.strategy=name;p.textContent=(name==='raw_tail'?'Raw tail':'Timeline')+': '+m.eligible_resumed+'/'+m.eligible_count+' eligible tasks resumed; unsafe proposals '+m.unsafe_proposals+'/'+m.ineligible_count+' before gate, '+m.unsafe_final+'/'+m.ineligible_count+' after gate.';root.append(p);});}dial.addEventListener('input',show);show();})();</script>'''


def explorer(report: dict) -> str:
    payload = visual_payload(report)
    figure = outcome_figure(report)
    if not payload["records"]:
        return figure
    unsafe = sum(type(s.get("unsafe_proposals")) is int and s["unsafe_proposals"] or 0
                 for s in report.get("metrics", {}).values())
    main_count = len(report.get("rows", []))
    budget = report.get('budget_bytes', next((r['budget_bytes'] for r in payload['records'] if r['budget_bytes'] is not None), 'unknown'))
    natural = report.get('natural_rows', [])
    caught = sum(r['proposal']['action'] == 'resume' and r['gate']['action'] == 'hold' for r in natural)
    bypassed = sum(r['gate']['action'] == 'resume' for r in report.get('gate_off_rows', []))
    return STYLE + '''<section id="continuity-visual" aria-labelledby="cv-heading">
<div class="cv-section-label">Explore the mechanism</div><h2 id="cv-heading">What survived. What still has authority.</h2>
<p>Choose a task and memory view. The source timeline shows every target-task event;
the retention lane shows exactly which records reached the fresh reader.</p>
<div class="cv-controls"><label>Task <select id="cv-case"></select></label>
<label>Memory view <select id="cv-arm"><option value="raw_tail">Raw tail · ''' + escape(str(budget)) + ''' bytes</option>
<option value="timeline">Structured timeline · ''' + escape(str(budget)) + ''' bytes</option><option value="full_history">Full history · unbudgeted</option></select></label></div>
<div class="cv-grid"><figure class="cv-panel"><figcaption>Source order → retained evidence</figcaption>
<div class="cv-timeline-scroll" tabindex="0" role="region" aria-label="Source timeline; scroll to retain readable labels"><svg id="cv-timeline" role="img" aria-label="Source event order and retention"></svg></div>
<p class="cv-caption">Solid dot = retained. Hollow dot = omitted. Ring = latest authoritative event.
Typed notes cannot change task state.</p></figure>
<div class="cv-panel"><p id="cv-budget" class="cv-budget"></p><p id="cv-expected"></p><strong id="cv-verdict" class="cv-verdict"></strong><p id="cv-scope" class="cv-caption"></p>
<div class="cv-flow"><div><span>1 · Reader proposal</span><strong id="cv-proposal"></strong><small id="cv-citation"></small></div>
<div class="cv-arrow" aria-hidden="true">↓</div><div><span>2 · Current ledger authority</span><strong id="cv-state"></strong><small id="cv-current"></small></div>
<div class="cv-arrow" aria-hidden="true">↓</div><div id="cv-decision-box"><span>3 · Gate outcome</span><strong id="cv-decision"></strong><small id="cv-reason"></small></div></div>
<p id="cv-summary" aria-live="polite"></p>
<p class="cv-caption">The gate reads the full authoritative ledger. The reader only sees the selected memory.
A favorable gate outcome is not credited to the memory renderer.</p></div></div>
<details class="cv-source"><summary>Read the source text behind this diagram</summary><div id="cv-sources"></div></details>
<div class="cv-control-note"><b>Where the gate changes a decision</b><p>The ''' + str(main_count) + ''' history/strategy outcomes contain ''' + str(unsafe) + ''' unsafe proposals.
Zero unsafe proposals there follows from its authored record lengths, and zero unsafe final actions is a policy invariant.
The separate longer-terminal controls produce <strong>''' + str(caught) + ''' caught stale resumptions</strong> from the actual reader.
A real gate-off rerun produces <strong>''' + str(bypassed) + ''' unsafe resumptions</strong>. The separate planted stale-request control is explicitly labeled input, not an ablation.</p></div>
''' + figure + '''</section>''' + budget_explorer(report) + '''<script type="application/json" id="cv-data">''' + safe_json(payload) + '''</script>''' + SCRIPT


STYLE = '''<style>
#continuity-visual{margin:40px 0 64px}.cv-section-label{font-size:12px;text-transform:uppercase;letter-spacing:.16em;color:#397762;font-weight:700}#continuity-visual h2{margin-top:10px;font-size:38px;max-width:720px}.cv-controls{display:flex;gap:24px;flex-wrap:wrap;margin:26px 0}.cv-controls label{display:grid;gap:6px;font-size:14px;font-weight:650}.cv-controls select{max-width:100%;min-width:210px;font-size:15px}.cv-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:24px}.cv-panel{margin:0;background:white;border:1px solid #d1d8d8;padding:24px;min-width:0}.cv-panel figcaption{font-weight:700;font-size:15px;margin-bottom:18px}#cv-timeline{width:100%;display:block}.cv-caption{font-size:13px;color:#526273;line-height:1.5}.cv-budget{font-size:15px;margin:0 0 20px}.cv-flow>div:not(.cv-arrow){background:#edf1ed;padding:15px 20px;border-left:4px solid #84988f}.cv-flow span,.cv-flow small{display:block;font-size:13px;overflow-wrap:anywhere}.cv-flow strong{display:block;font:30px/1.3 Georgia,serif;margin:5px 0}.cv-arrow{text-align:center;font-size:25px;color:#657c77;line-height:1.4}#cv-decision-box{border-color:#397762;background:#e0eee5}#cv-summary{font-size:15px}.cv-source{margin-top:18px;border-bottom:1px solid #d1d8d8;padding:16px 0}.cv-source ol{padding-left:22px}.cv-source li{margin:14px 0;font-size:14px}.cv-control-note{margin-top:30px;padding:20px 24px;background:#f2e9d5;border-left:4px solid #9f7a35}.cv-control-note p{font-size:15px;margin:8px 0}.cv-outcomes{margin:32px 0 0;padding:26px;background:white;border:1px solid #d1d8d8}.cv-outcomes figcaption{font-size:15px;margin-bottom:20px}.cv-outcome-row{display:grid;grid-template-columns:250px 1fr;gap:20px;align-items:center;margin:22px 0;font-size:14px}.cv-outcome-row svg{width:100%;max-width:420px}.cv-outcome-row span{color:#526273;font-size:13px}select:focus-visible,summary:focus-visible{outline:3px solid #397762;outline-offset:3px}
.cv-timeline-scroll{overflow-x:auto;max-width:100%}#cv-timeline{min-width:430px}.cv-verdict{display:block;padding:10px 12px;background:#e0eee5;border-left:4px solid #397762}.cv-verdict[data-verdict="missed_eligible"],.cv-verdict[data-verdict="unsafe_allowed"]{background:#f6ded1;border-color:#a54b28}.cv-verdict[data-verdict="unsafe_caught"]{background:#f2e9d5;border-color:#9f7a35}.cv-timeline-scroll:focus-visible{outline:3px solid #397762}.budget-chart{overflow-x:auto}.budget-chart svg{display:block;width:100%;min-width:740px}#budget-dial{width:100%;accent-color:#397762}#budget-readout{display:grid;grid-template-columns:1fr 1fr;gap:20px}#budget-readout p{padding:15px;background:white;border:1px solid #d1d8d8;font-size:15px}
@media(max-width:760px){.cv-grid{grid-template-columns:1fr}.cv-panel{padding:18px}.cv-controls{gap:14px}.cv-controls label{width:100%}.cv-outcome-row{grid-template-columns:1fr;gap:8px}.cv-outcomes{padding:18px}#continuity-visual h2{font-size:30px}#budget-readout{grid-template-columns:1fr;gap:0}}
.budget-chart svg{min-width:1080px}.budget-mobile-steps{display:none}.budget-scope{font-size:15px}.budget-mobile-steps ul{list-style:none;padding:0}.budget-mobile-steps li{display:grid;gap:3px;padding:12px;margin:8px 0;background:white;border-left:4px solid #ad562e;font-size:15px}.budget-mobile-steps p{font-size:14px}@media(max-width:760px){.budget-chart{display:none}.budget-mobile-steps{display:block}.budget-scope{font-size:15px}}
</style>'''

SCRIPT = '''<script>
(()=>{const root=document.getElementById('continuity-visual');if(!root)return;
const rows=JSON.parse(document.getElementById('cv-data').textContent).records;
const cases=[...new Set(rows.map(r=>r.case_id))];const caseSelect=document.getElementById('cv-case');
cases.forEach(id=>{const option=document.createElement('option');option.value=id;option.textContent=id+(id.startsWith('natural-')?' · outside matrix':'');caseSelect.append(option);});
// Prefer an observed unsafe proposal that the gate caught; eligibility and
// failure are explicit recorded fields, not inferred from an abstention alone.
const interesting=rows.find(r=>r.strategy==='raw_tail'&&r.verdict==='unsafe_caught')||rows.find(r=>r.strategy==='raw_tail'&&r.verdict==='missed_eligible');if(interesting)caseSelect.value=interesting.case_id;
const arm=document.getElementById('cv-arm');const put=(id,text)=>{document.getElementById(id).textContent=text;};
const ns='http://www.w3.org/2000/svg';const svg=document.getElementById('cv-timeline');
function node(tag,attrs,text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
function render(){const row=rows.find(r=>r.case_id===caseSelect.value&&r.strategy===arm.value);if(!row)return;
const retained=new Set(row.retained_ids);svg.replaceChildren();const height=70+row.source_events.length*75;svg.setAttribute('viewBox',`0 0 430 ${height}`);
node('title',{},`${row.case_id}: ${retained.size} of ${row.source_events.length} target-task events retained`);
node('line',{x1:25,y1:34,x2:25,y2:height-45,stroke:'#c2cecd','stroke-width':2});
row.source_events.forEach((event,index)=>{const y=40+index*75;const kept=retained.has(event.event_id);const current=event.event_id===row.gate.current_evidence_id;
node('circle',{cx:25,cy:y,r:8,fill:kept?'#397762':'white',stroke:kept?'#397762':'#8b9ca3','stroke-width':2});
if(current)node('circle',{cx:25,cy:y,r:14,fill:'none',stroke:'#152b40','stroke-width':2});
node('text',{x:51,y:y-4,fill:'#152b40','font-size':16,'font-weight':650},`${event.sequence} · ${event.kind} · ${kept?'retained':'omitted'}`);
node('text',{x:51,y:y+17,fill:'#526273','font-size':14},event.event_id+(current?' · latest authority':''));
node('text',{x:51,y:y+38,fill:'#526273','font-size':14},event.text.length>47?event.text.slice(0,44)+'…':event.text);});
put('cv-budget',`${row.used_bytes} ${row.budget_bytes===null?'bytes · unbudgeted diagnostic':`/ ${row.budget_bytes} UTF-8 bytes`} · ${retained.size}/${row.source_events.length} target-task records retained`);
put('cv-proposal',row.proposal.action);put('cv-citation',row.proposal.evidence?'Cites '+row.proposal.evidence.event_id:'No authoritative evidence retained');
put('cv-state',row.gate.state);put('cv-current','Current event: '+row.gate.current_evidence_id);put('cv-decision',row.gate.action);put('cv-reason',row.gate.reason);
const verdicts={correct_resume:'✓ Correct resume',correct_hold:'✓ Correct hold',missed_eligible:'! Missed eligible task',unsafe_caught:'! Unsafe proposal caught',unsafe_allowed:'! Unsafe resumption allowed',expectation_unavailable:'Expectation unavailable'};put('cv-expected','Expected task state: '+row.expected);put('cv-verdict',verdicts[row.verdict]);document.getElementById('cv-verdict').dataset.verdict=row.verdict;put('cv-scope',row.scope);document.getElementById('cv-decision-box').style.borderColor=(row.verdict==='missed_eligible'||row.verdict==='unsafe_allowed')?'#a54b28':'#397762';document.getElementById('cv-decision-box').style.background=(row.verdict==='missed_eligible'||row.verdict==='unsafe_allowed')?'#f6ded1':'#e0eee5';
put('cv-summary',`${row.case_id}: the reader proposed ${row.proposal.action}; the gate returned ${row.gate.action}.`);
const source=document.getElementById('cv-sources');source.replaceChildren();const list=document.createElement('ol');
row.source_events.forEach(event=>{const item=document.createElement('li');const title=document.createElement('b');title.textContent=`${event.event_id} · ${event.kind} · ${retained.has(event.event_id)?'retained':'omitted'}`;item.append(title);const text=document.createElement('p');text.textContent=event.text;item.append(text);list.append(item);});source.append(list);}
caseSelect.addEventListener('change',render);arm.addEventListener('change',render);render();})();
</script>'''
