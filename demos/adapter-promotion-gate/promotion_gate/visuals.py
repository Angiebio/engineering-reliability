"""Presentation projection of the recorded release audit, never a second gate.

Purpose: show why successful evaluation and permission to serve are different.
Contract: lifecycle frames use recorded before/after snapshots and the gallery's
recorded initialization. Action names supply labels; reasons supply categories.
Invariant: absent per-check measurements are never drawn as successful checks.
Rationale: a green pipeline can imply evidence the run did not actually capture.
Failure: unknown audit actions and inconsistent final serving state raise errors.
Evidence: tests/test_visuals.py checks rollback, denial, provenance and escaping.
"""
from html import escape
import json
import textwrap

STAGES = {
    "manifest_mismatch": "Artifact integrity", "artifact_mismatch": "Artifact integrity",
    "stale_evidence": "Evidence freshness", "stale_baseline": "Baseline identity",
    "nonfinite_json": "Report validity", "invalid_metric": "Report validity",
    "canary_failed": "Required canaries", "canary_schema": "Required canaries",
    "missing_canary": "Required canaries", "duplicate_canary": "Required canaries",
    "insufficient_gain": "Metric policy", "excess_regression": "Metric policy",
    "capacity": "Registry capacity", "invalid_transition": "Lifecycle policy",
    "unauthorized": "Release authority", "shadow": "Admitted to shadow",
    "rollback_restored": "Rollback completed",
}


def replay_frames(case: dict) -> list[dict]:
    """Project recorded state snapshots; action names supply labels only.

    Evidence: test_every_frame_uses_recorded_state. No transition table lives in
    this projection. The persistence validator checks audit/state consistency.
    """
    labels = {'admit': 'Admitted to shadow', 'approve': 'Explicitly approved',
              'serve': 'Candidate begins serving', 'rollback': 'Prior artifact restored'}
    initial = case['initial_snapshot']
    frames = [{'label': 'Initial registry', 'candidate_state': initial['record_states'].get('candidate', 'not admitted'),
               'serving': initial['serving'], 'serving_sha256': initial['serving_sha256'],
               'revision': 0, 'origin': 'Recorded initial registry', 'checks': []}]
    audit_by_revision = {record['revision']: record for record in case['audit']}
    for operation in case['operations']:
        action = operation['operation']
        if action not in labels:
            raise ValueError('Unknown recorded operation')
        snapshot = operation['after_state']
        if not operation['denial']:
            record = audit_by_revision.get(operation['revision'])
            if record is None or record['state_snapshot'] != snapshot or record['action'] != ('admit_shadow' if action == 'admit' else action):
                raise ValueError('Operation snapshot differs from committed audit')
        elif operation['before_state'] != snapshot or operation['before_sha256'] != operation['after_sha256']:
            raise ValueError('Recorded denial changed state')
        frames.append({'label': 'Operation denied; state preserved' if operation['denial'] else labels[action],
                       'candidate_state': snapshot['record_states'].get('candidate', 'not admitted'),
                       'serving': snapshot['serving'], 'serving_sha256': snapshot['serving_sha256'],
                       'revision': operation['revision'],
                       'origin': 'Recorded denial: ' + operation['denial'] if operation['denial'] else 'Recorded audit action: ' + ('admit_shadow' if action == 'admit' else action),
                       'checks': operation['checks'], 'before_sha256': operation['before_sha256'],
                       'after_sha256': operation['after_sha256']})
    if case['final_snapshot'] != case['operations'][-1]['after_state'] or frames[-1]['serving'] != case['serving']:
        raise ValueError('Presentation disagrees with final recorded state')
    return frames


def ladder_rows(result: dict) -> list:
    """Require every recorded stage to have a visible column before rendering.

    Unknown stages must fail the CLI rather than vanish into a successful image.
    Evidence: test_ladder_rejects_unknown_stages_before_publication.
    """
    stages = result['check_stages']
    if not stages or len(set(stages)) != len(stages):
        raise ValueError('Ladder stage catalog is empty or duplicated')
    rows = [(index + 1, case, operation) for index, case in enumerate(result['cases']) for operation in case['operations']]
    for _, _, operation in rows:
        for check in operation['checks']:
            if check['stage'] not in stages:
                raise ValueError('Unknown recorded ladder stage: ' + check['stage'])
            if check['status'] not in {'passed', 'stopped'}:
                raise ValueError('Unknown recorded ladder status')
    return rows


def ladder_cards(result: dict) -> str:
    """Keep row identity beside each measured check on small screens.

    Both figure forms consume the same recorded rows; cards do not infer a gate
    outcome from a scenario title. Evidence: test_ladder_cards_preserve_all_rows.
    """
    cards = []
    for number, case, operation in ladder_rows(result):
        checks = operation['checks']
        reached = {check['stage'] for check in checks}
        marks = ''.join('<li>' + escape(check['stage'].replace('_', ' ')) + ': <strong>'
                        + ('Passed' if check['status'] == 'passed' else 'Stopped: ' + escape(check['reason']))
                        + '</strong></li>' for check in checks)
        unreached = ', '.join(stage.replace('_', ' ') for stage in result['check_stages'] if stage not in reached)
        cards.append(f'<details class="gate-row" data-case="{number}" data-operation="{escape(operation["operation"])}">'
                     f'<summary>{number:02d}. {escape(case["name"])} / {escape(operation["operation"])}'
                     f' — {escape(operation["denial"] or "committed")}</summary><ol>{marks}</ol>'
                     f'<p>Not evaluated: {escape(unreached) if unreached else "none"}.</p></details>')
    return ('<style>.gate-row{padding:14px;border:1px solid #c5d0ce;margin:8px 0;background:white}'
            '.gate-row summary{overflow-wrap:anywhere}.gate-row li,.gate-row p{font-size:14px}'
            '</style><section id="gate-ladder"><h2>Which check stopped the change?</h2>'
            '<p>Every row is a recorded operation. Expand it for the ordered checks; unreached checks stay explicit. '
            'Canaries are authored booleans, not executed model safety tests. '
            '<a href="gate-stages.svg">Open or export the full ladder SVG</a>.</p>' + ''.join(cards) + '</section>')


def ladder_svg(result: dict) -> str:
    """A measured ladder: numbered cells are reached blocks, hatching is unevaluated."""
    stages = result['check_stages']
    rows = ladder_rows(result)
    # Wrap full scenario labels instead of dropping qualifiers such as
    # "no authentication". Evidence: test_ladder_preserves_full_authority_label.
    labels = [textwrap.wrap(f"{number:02d} {case['name']} / {operation['operation']}", width=72)
              for number, case, operation in rows]
    stride = max(31, 18 * max(map(len, labels), default=1) + 12)
    width, height = 1580, 150 + len(rows) * stride + 170
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="ladder-title ladder-desc">',
              '<title id="ladder-title">Checks actually reached, and exactly where an operation stopped</title>',
              '<desc id="ladder-desc">One row per executed operation. Checkmark means policy block passed, cross means stopped with a reason, and hatching means not evaluated. Canary statements are authored booleans; no canary test ran. Full before and after registry hashes are in results.json.</desc>',
              '<defs><pattern id="unreached" width="6" height="6" patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#f1f3f1"/><path d="M0 6L6 0" stroke="#cbd3d0"/></pattern></defs>',
              f'<rect width="{width}" height="{height}" fill="#fff"/>',
              '<text x="24" y="36" font-family="Georgia,serif" font-size="26" fill="#152c3b">Which check stopped the change?</text>',
              '<text x="24" y="63" font-family="sans-serif" font-size="14">Recorded operations · ✓ passed policy block · × stopped here · hatched = not evaluated</text>',
              '<text x="24" y="87" font-family="sans-serif" font-size="13">Canaries are authored boolean claims. These are policy checks, not executed model safety tests.</text>']
    left, cell = 550, 46
    for index, stage in enumerate(stages):
        pieces.append(f'<text x="{left + index * cell + 18}" y="118" font-family="sans-serif" font-size="12" text-anchor="middle">{index + 1}</text>')
    for index, (case_number, case, operation) in enumerate(rows):
        y = 130 + index * stride
        for line, label in enumerate(labels[index]):
            pieces.append(f'<text x="24" y="{y+18+line*18}" font-family="sans-serif" font-size="12">{escape(label)}</text>')
        reached = {check['stage']: (position+1, check) for position, check in enumerate(operation['checks'])}
        for column, stage in enumerate(stages):
            x = left + column * cell
            found = reached.get(stage)
            fill = 'url(#unreached)' if found is None else '#d7eadd' if found[1]['status'] == 'passed' else '#f0d1be'
            marker = '—' if found is None else ('✓' if found[1]['status'] == 'passed' else '×') + str(found[0])
            pieces.append(f'<rect x="{x}" y="{y}" width="39" height="25" fill="{fill}"/><text x="{x+19}" y="{y+17}" text-anchor="middle" font-family="sans-serif" font-size="12">{marker}</text>')
        note = operation['denial'] or 'committed'
        note += ' · ' + ('hash unchanged' if operation['before_sha256'] == operation['after_sha256'] else 'hash changed')
        pieces.append(f'<text x="{left+len(stages)*cell+8}" y="{y+18}" font-family="sans-serif" font-size="12">{escape(note)}</text>')
    bottom = 145 + len(rows)*stride
    for index, stage in enumerate(stages):
        x, y = (24 if index < 7 else 790), bottom + (index % 7)*21
        pieces.append(f'<text x="{x}" y="{y}" font-family="sans-serif" font-size="13">{index+1}: {escape(stage.replace("_", " "))}</text>')
    return ''.join(pieces) + '</svg>'


def visual_payload(result: dict) -> dict:
    return {"cases": [{"name": case["name"], "reason": case["observed"],
                        "category": STAGES.get(case["observed"], "Unclassified outcome"),
                        "denied": case["rejection_preserved_registry"] is True,
                        "frames": replay_frames(case), "audit": case["audit"]}
                       for case in result["cases"]]}


def explorer(result: dict) -> str:
    payload = (json.dumps(visual_payload(result), ensure_ascii=True, allow_nan=False)
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return STYLE + '''<section id="promotion-visual" aria-labelledby="pv-heading">
<div class="pv-eyebrow">Explore a recorded release path</div><h2 id="pv-heading">A candidate can pass a gate<br>and still have no right to serve.</h2>
<p>Choose a real scenario from this run, then step through its recorded state changes.
Denials appear without inventing a successful transition.</p>
<label class="pv-label">Recorded scenario <select id="pv-case"></select></label>
<div class="pv-grid"><div class="pv-panel"><div class="pv-diagram-title">Candidate lifecycle</div>
<svg id="pv-diagram" viewBox="0 0 300 400" role="img" aria-label="Recorded candidate lifecycle"></svg>
<p class="pv-caption">Filled node = candidate state at the selected step. The baseline keeps serving until an explicit serving transition is recorded.</p></div>
<div class="pv-panel"><div class="pv-stepper"><button type="button" id="pv-prev" aria-label="Previous recorded step">←</button>
<label for="pv-step">Recorded step <span id="pv-step-count"></span></label><button type="button" id="pv-next" aria-label="Next recorded step">→</button></div>
<input id="pv-step" type="range" min="0" max="0" value="0" aria-label="Recorded lifecycle step">
<h3 id="pv-step-title"></h3><p id="pv-origin"></p>
<div class="pv-serving"><span>Artifact serving at this step</span><strong id="pv-serving"></strong></div>
<dl class="pv-evidence"><div><dt>Registry revision</dt><dd id="pv-revision"></dd></div>
<div><dt>Scenario final outcome</dt><dd id="pv-reason"></dd></div><div><dt>Final outcome category</dt><dd id="pv-category"></dd></div></dl>
<p id="pv-summary" aria-live="polite"></p><p class="pv-caption">Category is an interpretation of the recorded reason code.
Canary outcomes are authored true/false statements in a synthetic report; no canary test was executed. Passed cells mean the policy accepted those statements; unreached checks are not plotted as passes.</p></div></div>
<div id="pv-checks" class="pv-checks" aria-live="polite"></div>
<ol id="pv-audit" class="pv-audit" aria-label="Recorded transition sequence"></ol>
<details><summary>Read the exact recorded audit</summary><pre id="pv-raw"></pre></details>
<div class="pv-note"><b>What the visual makes checkable</b><p>Admission only reaches shadow. Approval and serving are separate decisions.
Rollback restores the previous serving artifact. A failed operation must leave the registry unchanged.</p></div>
<h3>Every operation, in the gate-stage ladder</h3><p>Numbers inside reached cells show actual execution order. Hatched cells were not evaluated. Full before/after hashes accompany each operation in the raw record.</p><p><a href="gate-stages.svg">Download the measured ladder SVG</a></p><details><summary>Open all recorded check stages (scroll horizontally)</summary><div class="pv-ladder" tabindex="0" role="region" aria-label="Scrollable recorded gate-stage ladder">''' + ladder_svg(result) + '''</div></details>
</section><script type="application/json" id="pv-data">''' + payload + '''</script>''' + SCRIPT


STYLE = '''<style>
#promotion-visual{margin:44px 0 58px}#promotion-visual h2{font-size:38px;line-height:1.12;margin:10px 0 20px;max-width:850px}.pv-eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.16em;color:#246f5b;font-weight:700}.pv-label{display:grid;gap:6px;font-size:14px;font-weight:650;max-width:650px;margin:26px 0}.pv-label select{font:inherit;padding:12px;border:1px solid #b7c7c3;background:white;width:100%}.pv-grid{display:grid;grid-template-columns:1fr 1.1fr;gap:24px}.pv-panel{min-width:0;background:white;border:1px solid #c5d0ce;padding:26px}.pv-diagram-title{font-size:15px;font-weight:700}.pv-panel svg{width:100%;display:block;max-height:440px}.pv-ladder{overflow:auto}.pv-ladder svg{display:block;min-width:1580px}.pv-checks{padding:18px;background:#fff;border:1px solid #c5d0ce;margin-top:20px}.pv-checks ol{display:flex;gap:8px;flex-wrap:wrap;padding:0;list-style:none}.pv-checks li{padding:8px 12px;border:1px solid #bac8c1}.pv-checks .stopped{background:#f0d1be}.pv-checks .passed{background:#d7eadd}.pv-hash{font:12px ui-monospace,monospace;overflow-wrap:anywhere}.pv-caption{font-size:13px;color:#526672;line-height:1.5}.pv-stepper{display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:14px}.pv-stepper button{height:38px;width:42px;border:1px solid #a6bdb4;background:white;color:#152c3b;font:22px system-ui;cursor:pointer}.pv-stepper button[aria-disabled="true"]{opacity:.35;cursor:default}#pv-step{width:100%;accent-color:#246f5b;margin:18px 0}#pv-step-title{font:26px/1.2 Georgia,serif;margin:8px 0}#pv-origin{font-size:14px;overflow-wrap:anywhere}.pv-serving{background:#e1eee6;padding:18px 20px;margin:22px 0}.pv-serving span{display:block;font-size:13px}.pv-serving strong{font:34px/1.4 Georgia,serif}.pv-evidence{font-size:14px}.pv-evidence>div{display:grid;grid-template-columns:145px 1fr;gap:10px;border-bottom:1px solid #d5dedb;padding:10px 0}.pv-evidence dt{color:#526672}.pv-evidence dd{margin:0;overflow-wrap:anywhere}#pv-summary{font-size:15px}.pv-audit{padding:0;list-style:none;display:flex;gap:8px;flex-wrap:wrap;margin:22px 0}.pv-audit li{background:#e7eeea;padding:8px 12px;font-size:13px}.pv-audit li[aria-current="step"]{background:#246f5b;color:white}.pv-note{border-left:4px solid #246f5b;background:#e4ece7;padding:20px 24px;margin:28px 0}.pv-note p{margin:8px 0;font-size:15px}#promotion-visual input:focus-visible,#promotion-visual button:focus-visible,#promotion-visual select:focus-visible{outline:3px solid #246f5b;outline-offset:3px}
@media(max-width:760px){.pv-grid{grid-template-columns:1fr}.pv-panel{padding:18px}#promotion-visual h2{font-size:30px}.pv-evidence>div{grid-template-columns:125px 1fr}.pv-label select{font-size:13px}}
</style>'''

SCRIPT = '''<script>
(()=>{const data=JSON.parse(document.getElementById('pv-data').textContent).cases;if(!data.length)return;
const select=document.getElementById('pv-case'),range=document.getElementById('pv-step');
data.forEach((item,index)=>{const option=document.createElement('option');option.value=index;option.textContent=item.name;select.append(option);});
const full=data.findIndex(item=>item.reason==='rollback_restored');select.value=full<0?0:full;
const put=(id,value)=>document.getElementById(id).textContent=value;const ns='http://www.w3.org/2000/svg';const svg=document.getElementById('pv-diagram');
function node(tag,attrs,text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
function render(reset){const item=data[Number(select.value)];range.max=item.frames.length-1;if(reset)range.value=0;const index=Number(range.value),frame=item.frames[index];
put('pv-step-count',`${index+1} of ${item.frames.length}`);put('pv-step-title',frame.label);put('pv-origin',frame.origin);put('pv-serving',frame.serving);put('pv-revision',frame.revision);put('pv-reason',item.reason);put('pv-category',item.category);
put('pv-summary',item.denied?'This scenario records a denied operation. Its registry bytes were unchanged at denial.':'This scenario records successful lifecycle operations; eligibility alone never begins serving.');
document.getElementById('pv-prev').setAttribute('aria-disabled',String(index===0));document.getElementById('pv-next').setAttribute('aria-disabled',String(index===item.frames.length-1));
svg.replaceChildren();node('title',{},`Candidate state: ${frame.candidate_state}; serving artifact: ${frame.serving}`);
const labels=['not admitted','shadow','approved','serving','rolled_back'];const human=['Not admitted','Shadow evaluation','Explicitly approved','Serving requests','Rolled back: approval revoked'];
labels.forEach((state,i)=>{const y=10+i*76,active=state===frame.candidate_state;if(i<4){node('line',{x1:150,y1:y+54,x2:150,y2:y+74,stroke:'#b6c6c0','stroke-width':2});}
node('rect',{x:10,y,width:280,height:54,rx:6,fill:active?'#246f5b':'#edf1ee'});node('text',{x:150,y:y+32,'text-anchor':'middle','font-size':state==='rolled_back'?15:18,fill:active?'white':'#526672'},human[i]);});
const checkPanel=document.getElementById('pv-checks');checkPanel.replaceChildren();const heading=document.createElement('strong');heading.textContent='Checks actually reached in this operation';checkPanel.append(heading);const checks=document.createElement('ol');frame.checks.forEach((check,i)=>{const li=document.createElement('li');li.className=check.status;li.textContent=(i+1)+'. '+check.stage.replaceAll('_',' ')+' '+(check.status==='passed'?'✓ passed':'× stopped: '+check.reason);checks.append(li);});checkPanel.append(checks);if(!frame.checks.length){const note=document.createElement('p');note.textContent='Initial state: no operation has run yet.';checkPanel.append(note);}if(frame.before_sha256){const hash=document.createElement('p');hash.className='pv-hash';hash.textContent='Registry before: '+frame.before_sha256+' / after: '+frame.after_sha256;checkPanel.append(hash);}
const audit=document.getElementById('pv-audit');audit.replaceChildren();item.frames.forEach((f,i)=>{const li=document.createElement('li');li.textContent=`${i+1}. ${f.label}`;if(i===index)li.setAttribute('aria-current','step');audit.append(li);});
put('pv-raw',JSON.stringify(item.audit,null,2));}
select.addEventListener('change',()=>render(true));range.addEventListener('input',()=>render(false));
document.getElementById('pv-prev').addEventListener('click',()=>{range.value=Math.max(0,Number(range.value)-1);render(false);});
document.getElementById('pv-next').addEventListener('click',()=>{range.value=Math.min(Number(range.max),Number(range.value)+1);render(false);});render(true);})();
</script>'''
