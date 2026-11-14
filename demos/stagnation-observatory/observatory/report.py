"""Project saved decisions into a report with its limits attached to the figures.

Contract: numbers and marks come from retained replay rows; data strings are
escaped at HTML/SVG boundaries and embedded JSON cannot close its script tag.
Invariant: an outside-matrix control never changes the conformance denominator.
Rationale: the easiest figure to reuse must also carry the hardest caveat to omit.
Failure: absent metric/cadence fields fail generation instead of inventing values.
Evidence: test_summary_carries_policy_construction_caveat,
test_cadence_uses_measured_counts, test_report_escapes_script.
"""
from html import escape
import json


def summary_svg(report: dict) -> str:
    progress = report['metrics']['progress']
    trace_count = len(report['traces'])
    event_count = sum(len(trace['replay']['rows']) for trace in report['traces'])
    caveat = (f"Expected labels encode the verified-progress policy, so {progress['tp']}/{progress['fp']} "
              "is conformance by construction. This monitor also sees artifacts and waits; the baselines see text only.")
    pieces = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="440" viewBox="0 0 1100 440" role="img" aria-labelledby="summary-title summary-desc">',
              '<title id="summary-title">Policy conformance on authored examples</title>',
              '<desc id="summary-desc">' + escape(caveat) + ' Counts are event-level, not a held-out capability estimate.</desc>',
              '<rect width="1100" height="440" fill="#f6f4ed"/>',
              '<text x="42" y="45" font-family="Georgia,serif" font-size="28" fill="#142d3d">Policy conformance on authored examples</text>',
              f'<text x="42" y="76" font-family="sans-serif" font-size="15" fill="#526575">{trace_count} development traces · {event_count} events · no held-out data · no model calls</text>']
    maximum = max(max(row['tp'], row['fp']) for row in report['metrics'].values()) or 1
    for index, (name, row) in enumerate(report['metrics'].items()):
        y = 112 + index * 73
        label = {'exact': 'Exact text', 'lexical': 'Lexical similarity', 'progress': 'Verified progress'}[name]
        pieces.append(f'<text x="42" y="{y + 20}" font-family="sans-serif" font-size="16" fill="#142d3d">{escape(label)}</text>')
        for offset, key, color, label in ((0, 'tp', '#217966', 'true alerts'), (25, 'fp', '#b65b33', 'false alerts')):
            width = row[key] / maximum * 520
            pieces.append(f'<rect x="235" y="{y + offset}" width="{width:.2f}" height="18" fill="{color}"/>')
            pieces.append(f'<text x="{245 + width:.2f}" y="{y + offset + 14}" font-family="sans-serif" font-size="14" fill="#142d3d">{row[key]} {label}</text>')
    pieces.extend(['<rect x="26" y="334" width="1048" height="88" fill="#e5ebe5"/>',
                   '<text x="42" y="357" font-family="sans-serif" font-size="15" font-weight="700" fill="#142d3d">Expected labels encode the verified-progress policy, so '
                   + f"{progress['tp']}/{progress['fp']} is conformance by construction.</text>",
                   '<text x="42" y="382" font-family="sans-serif" font-size="15" fill="#142d3d">This monitor also sees artifacts and waits; the baselines see text only.</text>',
                   '<text x="42" y="405" font-family="sans-serif" font-size="14" fill="#526575">Useful work with sparse milestones can still alert. See the separate cadence sweep; no generalization claim.</text></svg>'])
    return ''.join(pieces)


def cadence_svg(report: dict) -> str:
    """Plot measured sweep points, preserving the six-milestone task denominator.

    The comparator has the same event count but never completes; y is alerts per
    trace, not a completion-rate metric. Equal x positions mean equal message
    gaps in the healthy trace. Evidence: test_cadence_uses_measured_counts.
    """
    points = report['cadence']['points']
    window = report['cadence']['stall_window']
    milestones, gaps = report['cadence']['milestones'], report['cadence']['gaps']
    largest = max(max(p['healthy_alerts'], p['stalled_alerts']) for p in points) or 1
    last = max(p['status_messages'] for p in points) or 1
    x = lambda gap: 100 + gap / last * 900
    y = lambda value: 325 - value / largest * 200
    pieces = ['<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="475" viewBox="0 0 1100 475" role="img" aria-labelledby="cadence-title cadence-desc">',
              f'<title id="cadence-title">Healthy work and the {window}-event alert boundary</title>',
              f'<desc id="cadence-desc">Measured alerts per trace. Healthy work completes {milestones} milestones separated by {gaps} equal message gaps. A stalled comparator has the same number of events but no verified milestones. The policy threshold is {window} events without new accepted progress.</desc>',
              '<rect width="1100" height="475" fill="#fff"/>',
              f'<text x="42" y="40" font-family="Georgia,serif" font-size="28" fill="#142d3d">Where the {window}-event policy starts alerting</text>',
              f'<text x="42" y="70" font-family="sans-serif" font-size="15" fill="#526575">Measured alerts per trace · healthy task: {milestones} milestones and {gaps} intervening message gaps</text>']
    for fraction in (0, .25, .5, .75, 1):
        value = largest * fraction
        yy = y(value)
        pieces.append(f'<line x1="100" y1="{yy:.2f}" x2="1000" y2="{yy:.2f}" stroke="#d8e0dc"/><text x="84" y="{yy + 5:.2f}" text-anchor="end" font-family="sans-serif" font-size="13" fill="#526575">{value:g}</text>')
    boundary = x(window)
    pieces.append(f'<line data-policy-boundary="{window}" x1="{boundary:.2f}" y1="105" x2="{boundary:.2f}" y2="334" stroke="#142d3d" stroke-dasharray="3 5"/><text x="{boundary + 9:.2f}" y="112" font-family="sans-serif" font-size="13" fill="#142d3d">Event {window}: alert boundary</text>')
    for key, color, dash in (('healthy_alerts', '#217966', ''), ('stalled_alerts', '#b65b33', ' stroke-dasharray="8 5"')):
        coordinates = ' '.join(f"{x(p['status_messages']):.2f},{y(p[key]):.2f}" for p in points)
        pieces.append(f'<polyline points="{coordinates}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        for p in points:
            xx, yy, value = x(p['status_messages']), y(p[key]), p[key]
            if key == 'healthy_alerts':
                pieces.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="5" fill="{color}"/>')
            else:
                pieces.append(f'<rect x="{xx - 5:.2f}" y="{yy - 5:.2f}" width="10" height="10" fill="{color}"/>')
            pieces.append(f'<text x="{xx:.2f}" y="{yy - 12:.2f}" text-anchor="middle" font-family="sans-serif" font-size="13" fill="{color}">{value}</text>')
    for p in points:
        pieces.append(f'<text x="{x(p["status_messages"]):.2f}" y="351" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#142d3d">{p["status_messages"]}</text>')
    pieces.extend(['<text x="550" y="379" text-anchor="middle" font-family="sans-serif" font-size="14" fill="#526575">Status messages between verified milestones in the healthy trace</text>',
                   '<circle cx="110" cy="410" r="5" fill="#217966"/><text x="126" y="415" font-family="sans-serif" font-size="14" fill="#142d3d">Healthy completed task · solid line</text>',
                   '<rect x="530" y="405" width="10" height="10" fill="#b65b33"/><text x="549" y="415" font-family="sans-serif" font-size="14" fill="#142d3d">Stalled trace of matched length · dashed line</text>',
                   f'<text x="42" y="450" font-family="sans-serif" font-size="14" fill="#526575">At gap k, both traces have {milestones} + {gaps}k events. Counts grow with trace length; these are authored controls, not failure rates.</text></svg>'])
    return ''.join(pieces)


def make_html(report: dict) -> str:
    data = json.dumps(report, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    progress, cadence = report['metrics']['progress'], report['cadence']
    text = (TEMPLATE.replace('<!--REPORT_DATA-->', data)
            .replace('<!--SUMMARY-->', summary_svg(report)).replace('<!--CADENCE-->', cadence_svg(report))
            .replace('<!--PHONE_FIGURES-->', phone_figures(report))
            .replace('<!--PHONE_CADENCE-->', phone_cadence(report)))
    # Public prose uses the same measured counts/policy as its figures. Numeric
    # substitutions are narrowly named template slots, never global replacement.
    values = {'TRACE_COUNT': len(report['traces']), 'POLICY_WINDOW': cadence['stall_window'],
              'PROGRESS_TP': progress['tp'], 'PROGRESS_FP': progress['fp'],
              'MILESTONES': cadence['milestones'], 'GAPS': cadence['gaps']}
    for name, value in values.items():
        text = text.replace('<!--' + name + '-->', str(value))
    return text


def phone_figures(report: dict) -> str:
    """Keep each measured count beside its label without clipping wide SVGs.

    Phone bars and cards project the same records as the desktop exports, with
    all cadence positions present. Evidence: test_phone_figures_match_records.
    """
    labels = {'exact': 'Exact text', 'lexical': 'Lexical similarity', 'progress': 'Verified progress'}
    progress = report['metrics']['progress']
    parts = ['<section class="phone-figures" id="summary-phone" aria-label="Policy conformance counts">']
    for name, metric in report['metrics'].items():
        parts.append(f'<article data-monitor="{name}"><h3>{labels[name]}</h3>'
                     f'<p><strong>{metric["tp"]}</strong> true alerts · <strong>{metric["fp"]}</strong> false alerts</p></article>')
    parts.append(f'<p class="notice">Expected labels encode the policy. {progress["tp"]}/{progress["fp"]} is conformance by construction, not generalization. The monitor sees artifacts and waits; baselines see text only.</p></section>')
    return ''.join(parts)


def phone_cadence(report: dict) -> str:
    points = report['cadence']['points']
    maximum = max(max(point['healthy_alerts'], point['stalled_alerts']) for point in points) or 1
    parts = ['<section class="phone-figures" id="cadence-phone" aria-label="Alerts per trace at every measured gap"><p>Alerts per trace: healthy work and stalled work of matched length.</p>']
    for point in points:
        gap = point['status_messages']
        boundary = ' · policy threshold' if gap == report['cadence']['stall_window'] else ''
        parts.append(f'<article data-gap="{gap}"><h3>{gap} status messages{boundary}</h3>')
        for key, label in (('healthy_alerts', 'Healthy'), ('stalled_alerts', 'Stalled')):
            value = point[key]
            parts.append(f'<div class="phone-bar-row" data-series="{key}" data-value="{value}"><span>{label}</span>'
                         f'<span class="phone-bar-track"><span class="phone-bar {key}" style="width:{value / maximum * 100:.3f}%"></span></span><strong>{value}</strong></div>')
        parts.append('</article>')
    parts.append('</section>')
    return ''.join(parts)


TEMPLATE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stagnation Observatory | Words and verified work</title><style>
:root{--paper:#f6f4ed;--ink:#142d3d;--muted:#526575;--line:#ced7d5;--green:#217966;--orange:#b65b33;--gold:#9d741c;--blue:#476f99}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,sans-serif}header{background:var(--ink);color:var(--paper);padding:24px max(24px,calc((100vw - 1160px)/2))}main{max-width:1208px;margin:auto;padding:22px 24px 56px}.eyebrow{text-transform:uppercase;letter-spacing:.15em;font-size:12px;font-weight:750;color:#b3d6ca}h1{font:clamp(35px,4.2vw,54px)/1.08 Georgia,serif;margin:12px 0}header p{max-width:950px;margin:12px 0 0;color:#d7e4e8;font-size:17px}h2{font:31px/1.2 Georgia,serif;margin:30px 0 14px}h3{font-size:18px;margin:0}.notice{background:#e6eee7;border-left:4px solid var(--green);padding:12px 18px;font-size:14px}.workbench{background:#fff;border:1px solid var(--line);margin-top:20px;padding:20px}.toolbar{display:flex;gap:18px;align-items:end;justify-content:space-between;flex-wrap:wrap}label{font-size:13px;font-weight:650;display:block}select,button{font:inherit;padding:8px 10px;border:1px solid #9cadaa;background:#fff;color:var(--ink);border-radius:3px}select{max-width:100%;min-width:260px}button{cursor:pointer}button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible,.chart-scroll:focus-visible{outline:3px solid #548aaa;outline-offset:3px}button:disabled{opacity:.45;cursor:default}.steps{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:15px 0}.steps input{flex:1;min-width:150px;accent-color:var(--green)}.steps output{min-width:98px;font-size:14px}.legend{display:flex;gap:9px 18px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.glyph{font-weight:800;font-size:16px;display:inline-block;min-width:20px;text-align:center}.legend .waiting{background:#fbf0cd}.timeline-frame{display:grid;grid-template-columns:155px minmax(0,1fr);margin:10px 0}.lane-labels{position:relative;height:280px;background:#fff;z-index:1;border-right:1px solid var(--line)}.lane-labels span{position:absolute;left:0;right:7px;font-size:13px;line-height:20px}.lane-labels span:nth-child(1){top:50px}.lane-labels span:nth-child(2){top:95px}.lane-labels span:nth-child(3){top:140px}.lane-labels span:nth-child(4){top:185px}.chart-scroll{overflow-x:auto;min-width:0}#timeline{display:block;height:280px;width:100%;min-width:650px}.caption{font-size:13px;color:var(--muted)}.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:#f1f4f1;padding:18px;border-top:3px solid var(--line);min-width:0}.panel p{margin:9px 0}.status{display:inline-block;padding:3px 10px;background:#dce4e8;font-weight:750;font-size:13px;border-radius:3px}.status.alert{background:#f2d8ca;color:#7b341a}.status.progress,.status.complete{background:#d4eadd;color:#175340}.status.waiting{background:#f0e5c1;color:#6a4b09}.status.evidence_error{background:#edd5e4;color:#703253}.quote{font:21px/1.4 Georgia,serif}.verdict{font-size:19px;font-weight:650}dl{display:grid;grid-template-columns:auto 1fr;gap:5px 12px;font-size:13px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}details{margin:12px 0}summary{cursor:pointer;font-weight:650}pre{font:12px/1.55 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#edf1ef;padding:14px;max-height:420px;overflow:auto}.summary-svg,.cadence-svg,.table-wrap{overflow:auto}.summary-svg svg,.cadence-svg svg{width:100%;min-width:700px;height:auto}.limitation{border:2px solid var(--orange);background:#fff8ef;padding:18px 22px;margin:0 0 24px}.limitation h3{color:#8b4528}.limitation p{margin:9px 0}.limitation button{border-color:var(--orange)}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}thead{background:#e3e9e5}.controls{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.control{padding:18px;background:#fff;border:1px solid var(--line)}.control strong{display:block}.control p{font-size:14px}.flow{display:flex;flex-wrap:wrap;gap:10px;margin:20px 0}.flow span{background:#e7ede7;padding:9px 12px;font-size:14px}.evidence-line{border-left:3px solid var(--green);padding-left:14px}a{color:var(--green)}footer{border-top:1px solid var(--line);margin-top:32px;padding-top:16px;font-size:13px;color:var(--muted)}.mono,#provenance{overflow-wrap:anywhere}.mono{font-family:ui-monospace,monospace}#selection-scope{margin:8px 0;font-size:13px;color:var(--muted)}@media(max-width:700px){header{padding:24px 20px}main{padding:18px 14px 36px}.workbench{padding:14px}.details-grid,.controls{grid-template-columns:1fr}select{min-width:0;width:100%}.toolbar>div{width:100%}h2{font-size:27px}.steps button{padding:7px}.timeline-frame{grid-template-columns:106px minmax(0,1fr)}.lane-labels span{font-size:11px}.legend{gap:7px 12px}.summary-svg svg,.cadence-svg svg{min-width:730px}.limitation{padding:15px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
.phone-figures{display:none}.phone-figures article{padding:12px;margin:10px 0;border:1px solid var(--line);background:white}.phone-figures h3{font-size:16px}.phone-figures p{font-size:15px}.phone-bar-row{display:grid;grid-template-columns:64px minmax(0,1fr) 28px;gap:8px;align-items:center;margin:7px 0;font-size:14px}.phone-bar-row strong{text-align:right}.phone-bar-track{height:10px;background:#e4e9e5}.phone-bar{display:block;height:100%;background:var(--green)}.phone-bar.stalled_alerts{background:var(--orange)}@media(max-width:700px){.summary-svg,.cadence-svg{display:none}.phone-figures{display:block}}
</style></head><body><header><div class="eyebrow">The Real Cat Labs · Agent reliability engineering</div><h1>New words. Same unfinished work?</h1><p>Compare an agent's words with accepted evidence and bounded waits. Then see where useful work outlasts the monitor's <!--POLICY_WINDOW-->-event window.</p></header><main>
<div class="notice"><strong>Deterministic development demonstration.</strong> <!--TRACE_COUNT--> authored traces test a declared policy. Separate limitation controls are outside that matrix. No model inference, patient data or automatic remediation.</div>
<section class="workbench" aria-labelledby="replay-title"><div class="toolbar"><div><h2 id="replay-title" style="margin-top:0">Follow one trace</h2><label for="scenario">Scenario</label><select id="scenario"></select></div><button id="download-svg">Download this timeline as SVG</button></div><p id="selection-scope"></p>
<div class="steps"><button id="previous" aria-label="Previous event">← Previous</button><input id="step" aria-label="Event in selected trace" type="range" min="0" max="5" value="0"><button id="next" aria-label="Next event">Next →</button><output id="step-label" for="step"></output></div>
<div class="legend" aria-label="Timeline symbols"><span><b class="glyph">●</b>Text repetition</span><span><b class="glyph">■</b>New verified criterion</span><span class="waiting"><b class="glyph">Ⅱ</b>Wait band</span><span><b class="glyph">▲!</b>Alert</span><span><b class="glyph">◆×</b>Evidence error</span><span><b class="glyph">✓</b>Complete</span><span><b class="glyph">·</b>Observing</span></div>
<div class="timeline-frame"><div class="lane-labels" aria-hidden="true"><span>Exact text baseline</span><span>Lexical baseline</span><span>Verified progress</span><span>Wait / alert / state</span></div><div class="chart-scroll" tabindex="0" role="region" aria-label="Scrollable event timeline; lane labels stay fixed"><svg id="timeline" viewBox="0 0 850 280" role="img" aria-labelledby="timeline-title timeline-description"></svg></div></div>
<p class="caption">Columns are ordered event ticks, not seconds. Selecting a step reads a saved decision. On phones, the event plot scrolls while lane labels remain fixed. Wait bands show the separately authorized interval.</p>
<div class="details-grid"><section class="panel"><h3>What the agent said</h3><p id="utterance" class="quote"></p><dl><dt>Event</dt><dd id="event-id"></dd><dt>Kind</dt><dd id="event-kind"></dd><dt>Exact baseline</dt><dd id="exact"></dd><dt>Lexical baseline</dt><dd id="lexical"></dd></dl></section><section class="panel" aria-live="polite"><h3>What the evidence supports</h3><p><span id="status" class="status"></span></p><p id="decision" class="verdict"></p><p id="progress-count"></p><p id="wait-description" class="evidence-line"></p><details><summary>Inspect artifact, criterion and exact decision</summary><pre id="event-json"></pre></details></section></div></section>
<section id="conformance"><h2>Conformance by construction, with a visible limit.</h2><p>The expected labels encode the verified-progress policy. Its <!--PROGRESS_TP--> true alerts and <!--PROGRESS_FP--> false alerts in this matrix therefore measure conformance by construction, not generalization. The monitor receives richer inputs—artifacts and waits—while both baselines see text only. This is not an equal-input algorithm comparison.</p><div id="summary-figure" class="summary-svg"><!--SUMMARY--></div><!--PHONE_FIGURES-->
<aside id="sparse-limitation" class="limitation" aria-labelledby="limitation-title"><h3 id="limitation-title">Useful work can lack a checkpoint</h3><p id="limitation-description"></p><p id="limitation-outcome" class="mono"></p><button id="show-limitation">Replay this limitation · outside the matrix</button></aside>
<h2>How long can useful work go without a milestone?</h2><p>The monitor alerts at <!--POLICY_WINDOW--> agent events without a newly accepted criterion. Partial drafts do not count until an entire criterion is satisfied. The sweep below records that boundary instead of hiding it behind the conformance score.</p><div id="cadence-figure" class="cadence-svg"><!--CADENCE--></div><!--PHONE_CADENCE--><p class="caption">Each healthy trace finishes <!--MILESTONES--> milestones across <!--GAPS--> equal gaps. At gap k, both traces contain <!--MILESTONES--> + <!--GAPS-->k events; trace length therefore grows across the sweep. The stalled comparator has that same event count and no verified milestones. These authored controls are outside the <!--TRACE_COUNT-->-trace matrix, and the counts are not rates of real agent failure.</p><div class="table-wrap"><table><thead><tr><th>Status messages per gap</th><th>Healthy-task alerts</th><th>Matched-length stall alerts</th></tr></thead><tbody id="cadence-table"></tbody></table></div>
<p><a href="summary.svg">Download the conformance SVG with caveat</a> · <a href="cadence.svg">Download the cadence SVG</a></p><div class="table-wrap"><table><thead><tr><th>Monitor</th><th>True alerts</th><th>False alerts</th><th>Missed alerts</th><th>True negatives</th><th>Precision</th><th>Recall</th><th>False alerts / 100 events</th></tr></thead><tbody id="metrics"></tbody></table></div></section>
<h2>A guard has to change the answer.</h2><p>The unsafe ablation deliberately trusts a result claim. Other controls change bytes, omit evidence, or separate the text baselines. These controls remain outside the main conformance denominator.</p><div id="controls" class="controls"></div>
<h2>From source to decision</h2><div class="flow"><span>Harness-owned criteria and waits</span><span>Separately pinned digests</span><span>Agent-supplied artifact bytes</span><span>Task + criterion + exact items</span><span>New milestone only</span><span>Recorded decision to investigate</span></div>
<p>The harness passes the specification and pinned digests separately from the agent trace and artifact store. Bytes that no longer match the separately pinned digest become evidence errors. A digest proves consistency, not authorship or work quality: recreating the expected pinned bytes is accepted. The toy item-ID checker demonstrates the call path; a real workflow needs an appropriate acceptance checker and a protected harness. A wait requires a matching harness declaration, not just a controller role string.</p>
<details><summary>Inspect every matrix trace outcome</summary><div class="table-wrap"><table><thead><tr><th>Trace</th><th>Family</th><th>Events</th><th>Expected positive events</th><th>Exact alerts</th><th>Lexical alerts</th><th>Progress alerts</th><th>First expected / observed tick</th></tr></thead><tbody id="all-traces"></tbody></table></div></details>
<footer><p>Reproduce: <code>python -B -m observatory --out artifacts</code><br><a href="results.json">Raw records, controls and source hashes</a> · <a href="../docs/report.md">Methods and limitations</a> · <a href="../README.md">Source and test commands</a></p><p>For hosting, preserve the whole package directory, including docs and README; serving only artifacts removes those relative documentation links. Malformed traces fail closed with ValueError: the caller must treat that failure as requiring investigation, never as healthy work.</p><p id="provenance"></p></footer></main>
<script type="application/json" id="data"><!--REPORT_DATA--></script><script>
'use strict';
const report=JSON.parse(document.getElementById('data').textContent),byId=id=>document.getElementById(id);
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const titles={exact:'Exact text',lexical:'Lexical similarity',progress:'Verified progress'};
const mainOptions=[1,0,2,3,4,5].flatMap(f=>report.traces.filter(t=>t.label.family===report.families[f]));
const controlOptions=report.controls.filter(c=>c.replay&&c.trace).map(c=>({trace_id:c.trace.trace_id,label:{title:c.title+' · outside the matrix'},replay:c.replay,outside:true,description:c.description}));
const optionOrder=[...mainOptions,...controlOptions];
optionOrder.forEach(trace=>{const option=document.createElement('option');option.value=trace.trace_id;option.textContent=trace.label.title;byId('scenario').append(option);});
let chosen=optionOrder[0],position=2,plotWidth=850;
const outcomes={progress:'New acceptance criterion verified',complete:'All declared criteria are already verified',waiting:'Waiting inside an explicit boundary',alert:'No new verified progress',observing:'Collecting the progress window',evidence_error:'Evidence could not be verified'};
const laneNames=['Exact text baseline','Lexical baseline','Verified progress','Wait / alert / state'];
function draw(){
 const rows=chosen.replay.rows,row=rows[position],ys=[60,105,150,195];plotWidth=Math.max(850,rows.length*75);
 const left=36,right=plotWidth-36,span=right-left,x=i=>left+i*span/Math.max(1,rows.length-1),gap=span/Math.max(1,rows.length-1);
 let svg='<title id="timeline-title">'+esc(chosen.label.title)+'</title><desc id="timeline-description">Lanes from top: exact text baseline, lexical baseline, verified progress, wait or alert state. Circles show text repetition, squares new criteria, shaded bands and double bars waits, triangles with exclamation alerts, diamonds with crosses evidence errors, checkmarks completion. Selected event '+esc(row.event.tick)+'.</desc><rect width="'+plotWidth+'" height="280" fill="#fff"/>';
 rows.forEach((r,i)=>{if(r.wait_active){svg+='<rect data-wait-band="true" x="'+Math.max(0,x(i)-gap/2)+'" y="38" width="'+gap+'" height="177" fill="#fbf0cd"/>';}});
 ys.forEach(yy=>{svg+='<line x1="15" y1="'+yy+'" x2="'+(plotWidth-15)+'" y2="'+yy+'" stroke="#d9e1df"/>';});
 rows.forEach((r,i)=>{const xx=x(i);svg+='<text x="'+xx+'" y="246" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#526575">'+esc(r.event.tick)+'</text>';
 [['exact_alert',0],['lexical_alert',1]].forEach(([key,lane])=>{svg+='<circle data-signal="'+key+'" cx="'+xx+'" cy="'+ys[lane]+'" r="'+(r[key]?8:3)+'" fill="'+(r[key]?'#476f99':'#d9e1df')+'"/>';});
 svg+='<rect data-progress="'+r.new_progress+'" x="'+(xx-7)+'" y="'+(ys[2]-7)+'" width="14" height="14" fill="'+(r.new_progress?'#217966':'#e6ece9')+'"/>';
 if(r.status==='alert'){svg+='<path data-state="alert" d="M '+xx+' 181 L '+(xx+13)+' 207 L '+(xx-13)+' 207 Z" fill="#b65b33"/><text x="'+xx+'" y="202" text-anchor="middle" font-family="sans-serif" font-weight="700" font-size="16" fill="#fff">!</text>';}
 else if(r.status==='evidence_error'){svg+='<path data-state="evidence_error" d="M '+xx+' 181 L '+(xx+14)+' 195 L '+xx+' 209 L '+(xx-14)+' 195 Z" fill="#975782"/><text x="'+xx+'" y="200" text-anchor="middle" font-family="sans-serif" font-size="19" fill="#fff">×</text>';}
 else if(r.status==='waiting'){svg+='<text data-state="waiting" x="'+xx+'" y="202" text-anchor="middle" font-family="sans-serif" font-size="23" font-weight="700" fill="#7d5d15">Ⅱ</text>';}
 else if(r.status==='complete'){svg+='<text data-state="complete" x="'+xx+'" y="202" text-anchor="middle" font-family="sans-serif" font-size="24" font-weight="700" fill="#217966">✓</text>';}
 else{svg+='<circle data-state="'+esc(r.status)+'" cx="'+xx+'" cy="195" r="3" fill="#a4b6ae"/>';}
 });
 svg+='<line x1="'+x(position)+'" x2="'+x(position)+'" y1="30" y2="222" stroke="#142d3d" stroke-width="2"/><text x="'+x(position)+'" y="20" text-anchor="middle" font-family="sans-serif" font-size="13" fill="#142d3d">Selected</text><text x="'+plotWidth/2+'" y="273" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#526575">Event tick (ordered synthetic steps)</text>';
 const timeline=byId('timeline');timeline.setAttribute('viewBox','0 0 '+plotWidth+' 280');timeline.style.minWidth=plotWidth+'px';timeline.innerHTML=svg;
 const plot=timeline.parentElement;if(plot.scrollWidth>plot.clientWidth){plot.scrollLeft=Math.max(0,x(position)-plot.clientWidth*.5);}
 byId('step').max=rows.length-1;byId('step').value=position;byId('step-label').textContent='Event '+(position+1)+' of '+rows.length;
 byId('previous').disabled=position===0;byId('next').disabled=position===rows.length-1;
 byId('selection-scope').textContent=chosen.outside?'Outside the 24-trace matrix · '+chosen.description:'Authored policy-conformance fixture · included in the 152-event matrix';
 byId('utterance').textContent=row.event.text;byId('event-id').textContent=row.event.event_id;byId('event-kind').textContent=row.event.kind;
 byId('exact').textContent=row.exact_alert?'Repetition alert':'No repetition alert';byId('lexical').textContent=(row.lexical_alert?'Repetition alert':'No repetition alert')+' · maximum recent similarity '+row.lexical_similarity;
 byId('status').className='status '+row.status;byId('status').textContent=row.status.replace('_',' ');byId('decision').textContent=outcomes[row.status];
 byId('progress-count').textContent=row.completed_criteria.length+' / '+chosen.replay.criteria_count+' criteria accepted; '+row.idle_agent_events+' agent '+(row.idle_agent_events===1?'event':'events')+' since new progress or wait declaration.';
 byId('wait-description').textContent=row.wait_until===null?'No controller wait is in effect.':(row.wait_active?'Wait active':'Wait expired')+' · expires at tick '+row.wait_until+'. '+row.wake_condition;
 byId('event-json').textContent=JSON.stringify(row,null,2);
}
function selectTrace(id,index=2){chosen=optionOrder.find(t=>t.trace_id===id);position=Math.min(index,chosen.replay.rows.length-1);byId('scenario').value=id;draw();}
byId('scenario').addEventListener('change',()=>selectTrace(byId('scenario').value));
byId('step').addEventListener('input',()=>{position=Number(byId('step').value);draw();});
byId('previous').addEventListener('click',()=>{position=Math.max(0,position-1);draw();});byId('next').addEventListener('click',()=>{position=Math.min(chosen.replay.rows.length-1,position+1);draw();});
byId('download-svg').addEventListener('click',()=>{const labels=laneNames.map((label,i)=>'<text x="10" y="'+([60,105,150,195][i]+5)+'" font-family="sans-serif" font-size="13" fill="#142d3d">'+esc(label)+'</text>').join('');const content='<svg xmlns="http://www.w3.org/2000/svg" width="'+(plotWidth+180)+'" height="280" viewBox="0 0 '+(plotWidth+180)+' 280" role="img"><title>'+esc(chosen.label.title)+'</title><rect width="100%" height="100%" fill="#fff"/>'+labels+'<g transform="translate(180 0)">'+byId('timeline').innerHTML+'</g></svg>';const url=URL.createObjectURL(new Blob([content],{type:'image/svg+xml'}));const anchor=document.createElement('a');anchor.href=url;anchor.download=chosen.trace_id+'-timeline.svg';anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
byId('metrics').innerHTML=Object.entries(report.metrics).map(([name,m])=>'<tr><th>'+esc(titles[name])+'</th>'+['tp','fp','fn','tn','precision','recall','false_alerts_per_100_events'].map(key=>'<td>'+esc(m[key]===null?'undefined':m[key])+'</td>').join('')+'</tr>').join('');
const sparse=report.controls.find(c=>c.kind==='sparse_checkpoint');byId('limitation-description').textContent=sparse.description;byId('limitation-outcome').textContent=sparse.outcome;byId('show-limitation').addEventListener('click',()=>{selectTrace(sparse.trace.trace_id,3);byId('replay-title').scrollIntoView({block:'start'});byId('scenario').focus({preventScroll:true});});
byId('cadence-table').innerHTML=report.cadence.points.map(p=>'<tr><th>'+p.status_messages+'</th><td>'+p.healthy_alerts+'</td><td>'+p.stalled_alerts+'</td></tr>').join('');
byId('controls').innerHTML=report.controls.filter(c=>c.kind!=='sparse_checkpoint').map(c=>'<article class="control"><strong>'+esc(c.title)+'</strong><p>'+esc(c.description)+'</p><p class="mono">'+esc(c.outcome)+'</p></article>').join('');
byId('all-traces').innerHTML=report.traces.map(t=>'<tr><th>'+esc(t.trace_id)+'</th><td>'+esc(t.label.family)+'</td><td>'+t.replay.rows.length+'</td><td>'+t.label.positive_event_ids.length+'</td>'+['exact','lexical','progress'].map(name=>'<td>'+esc(t.summary[name].alerts)+'</td>').join('')+'<td>'+esc(t.summary.expected_first_tick??'none')+' / '+esc(t.summary.progress.first_alert_tick??'none')+'</td></tr>').join('');
byId('provenance').textContent='Protocol '+report.protocol+' · Python '+report.python+' · Fixture SHA-256 '+report.fixture_sha256;draw();
</script></body></html>'''
