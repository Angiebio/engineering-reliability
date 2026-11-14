"""Project actual SQL observations with denominators attached to every figure.

Contract: text is escaped, geometry is finite and bounded, and desktop/mobile
views use the same measured values. Unknown is distinct from an empty cohort.
Invariant: nodes retain trial identities and bars share a zero-based scale.
Rationale: a plotted claim is inspectable only if its wiring is tested too.
Failure: invalid numbers raise before output; no remote resources are loaded.
Evidence: test_bar_geometry_and_labels, test_provenance_edges_and_duplicate_marker,
test_exact_integer_display, test_compact_comparison_keeps_all_marks_in_view.
"""
from collections import Counter
from html import escape
import json
import math
import textwrap

from .core import MAX_RECORDS, MAX_VALUE


def esc(value):
    """Treat source strings as labels, never SVG/HTML syntax."""
    return escape(str(value), quote=True)


def display(value):
    """Integers remain exact; floats use Python's shortest round-trip decimal.

    No six-significant-digit rounding may erase the very discrepancy shown.
    Mutation: RM-DISPLAY. Evidence: test_exact_integer_display.
    """
    if value is None:
        return 'unknown'
    if type(value) is int or (type(value) is float and value.is_integer()):
        return f'{int(value):,}'
    return repr(value) if type(value) is float else str(value)


def number(value):
    # All filter joins are INNER JOINs. Worst-case row count is the greater of
    # the trial count and site/intervention product, not their sum. This chosen
    # fixture limit is a resource bound, not a real-registry capacity claim.
    # Evidence: test_aggregate_geometry_exceeds_single_record_cap.
    aggregate_limit = max(MAX_RECORDS, MAX_RECORDS**2) * MAX_VALUE
    if type(value) not in (int, float) or not 0 <= value <= aggregate_limit or not math.isfinite(value):
        raise ValueError('Invalid chart geometry')
    return value


def context(scenario):
    result = scenario['result']
    filters = result['filters']
    return (f"{scenario['title']} | country={filters['country'] or 'all'}; kind={filters['intervention_kind'] or 'all'} | "
            f"{len(result['cohort'])} {'trial' if len(result['cohort']) == 1 else 'trials'}; {len(result['joined_rows'])} query rows | invented, trial-wide values")


def svg_open(width, height, identity, title, description):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
            f'aria-labelledby="{esc(identity)}-title {esc(identity)}-desc">'
            f'<title id="{esc(identity)}-title">{esc(title)}</title><desc id="{esc(identity)}-desc">{esc(description)}</desc>'
            f'<rect width="{width}" height="{height}" fill="#fffdf7"/>'
            '<g font-family="system-ui,sans-serif" fill="#16382f" font-size="15">')


def provenance_svg(scenario):
    result = scenario['result']
    cohort, joined = result['cohort'], result['joined_rows']
    height = 165 + max(len(cohort), len(joined), 1) * 76
    positions = {trial['id']: 155 + index * 76 for index, trial in enumerate(cohort)}
    country_by_site = {site['id']: site['country'] or 'unknown country' for site in scenario.get('data', {}).get('sites', [])}
    paths, nodes, seen = [], [], set()
    for index, row in enumerate(joined):
        y = 155 + index * 76
        # Each edge begins at its own trial, not at the first visually convenient
        # node. Mutation: RM-EDGE. Evidence: test_provenance_edges_and_duplicate_marker.
        source_y = positions[row['id']]
        repeated = row['id'] in seen
        seen.add(row['id'])
        paths.append(f'<path class="source-edge" data-trial="{esc(row["id"])}" data-row="{index}" d="M260 {source_y} C330 {source_y} 340 {y} 400 {y}" stroke="{("#a74b32" if repeated else "#688477")}"/>')
        paths.append(f'<path d="M620 {y} C680 {y} 700 {source_y} 760 {source_y}" stroke="#9db3a9"/>')
        source = ' / '.join(str(v) for v in (row['site_id'], country_by_site.get(row['site_id']), row['intervention_id']) if v is not None) or 'trial row; no site join'
        # The duplicate tag is visible evidence of multiplicity, not decoration.
        # Mutation: RM-DUPLICATE. Evidence: test_provenance_edges_and_duplicate_marker.
        duplicate = ' · duplicate trial' if repeated else ''
        nodes.append(f'<g class="joined-node"><rect x="400" y="{y-24}" width="220" height="54" rx="4" fill="{("#f8e9df" if repeated else "#edf1eb")}"/>'
                     f'<text x="413" y="{y-4}" font-weight="600">{esc(row["id"])} · {esc(display(row["enrollment"]))}</text>'
                     f'<text x="413" y="{y+17}" font-size="11">{esc(source + duplicate)}</text></g>')
    for row in cohort:
        y = positions[row['id']]
        for x, cls in ((30, 'trial-node'), (760, 'cohort-node')):
            nodes.append(f'<g class="{cls}" data-trial="{esc(row["id"])}"><rect x="{x}" y="{y-24}" width="230" height="54" rx="4" fill="#dcece3"/>'
                         f'<text x="{x+14}" y="{y-4}" font-weight="600">{esc(row["id"])} · enrollment {esc(display(row["enrollment"]))}</text>'
                         f'<text x="{x+14}" y="{y+17}" font-size="12">rate {esc(display(row["rate"]))} participants/month</text></g>')
    head = svg_open(1020, height, 'identity-' + scenario['id'], context(scenario), 'Connections follow actual SQL rows; duplicate rows retain their source trial identity.')
    return head + f'<text x="30" y="28" font-size="14">{esc(context(scenario))}</text>' + '''
<text x="30" y="80" font-weight="700">Selected trial identities</text><text x="400" y="80" font-weight="700">Rows produced by the query</text><text x="760" y="80" font-weight="700">One observation per trial</text>
<text x="30" y="102" font-size="12">Trial-wide source values</text><text x="400" y="102" font-size="12">Matching sites / interventions multiply rows</text><text x="760" y="102" font-size="12">Equal values remain separate</text>
<g fill="none" stroke-width="1.5">''' + ''.join(paths) + '</g>' + ''.join(nodes) + ('<text x="30" y="155">No trials (n=0).</text>' if not cohort else '') + '</g></svg>'


def comparisons_svg(scenario, compact=False):
    result = scenario['result']
    wrong, right = result['incorrect'], result['corrected']
    width, origin, span = (340, 20, 270) if compact else (1000, 210, 550)
    header = textwrap.wrap(context(scenario), 40 if compact else 112)
    header_end = 24 + 19 * len(header)
    parts = [f'<text x="20" y="{24+i*19}" font-size="{11 if compact else 14}">{esc(line)}</text>' for i, line in enumerate(header)]
    totals = [wrong['enrollment_sum'], right['enrollment_sum']]
    peak = max([number(n) for n in totals if n is not None] + [1])
    # Both labels are paired with their measured methods, and both bars start at
    # the same zero origin. Mutation: RM-BAR-LABEL.
    # Mutation: RM-BAR-ORIGIN.
    # Evidence: test_bar_geometry_and_labels.
    labels = ('Joined-row sum', 'Trial-identity sum')
    bar_origin = origin
    for index, (label, value, color, method) in enumerate(zip(labels, totals, ('#b45e3c', '#2a7559'), ('incorrect', 'corrected'))):
        y = header_end + 35 + index * (84 if compact else 64)
        bar_width = span * number(value) / peak if value is not None else 0
        rendered = 'no trials (n=0)' if right['trial_count'] == 0 else display(value)
        parts.append(f'<text class="bar-label" data-method="{method}" x="20" y="{y-9 if compact else y+18}">{label}</text>')
        parts.append(f'<rect class="enrollment-bar" data-method="{method}" x="{bar_origin}" y="{y}" width="{bar_width}" height="24" fill="{color}"/>')
        parts.append(f'<text class="bar-value" data-method="{method}" x="{20 if compact else origin+bar_width+10}" y="{y+45 if compact else y+18}" font-weight="700">{esc(rendered)}</text>')
    next_top = y + 100
    rates = [number(v) for v in right['rate_values']]
    maximum = max(rates + [1]) * 1.2
    dot_origin, dot_span = (30, 270) if compact else (220, 550)
    for index, (label, record, color, method) in enumerate((('DISTINCT rate values', wrong, '#b45e3c', 'incorrect'), ('One rate per trial', right, '#2a7559', 'corrected'))):
        validated = [number(v) for v in record['rate_values']]
        tallest = max(Counter(validated).values(), default=1)
        # Space each stack above its baseline and below its own title. The test
        # checks lane bounds as well as the viewBox, including dense equal rates.
        # Evidence: test_dense_equal_rates_stay_inside_svg, test_dot_lane_boundaries.
        lane_top = next_top + 30
        baseline = lane_top + 16 + 18 * (tallest - 1)
        parts.append(f'<g class="rate-lane" data-method="{method}" data-top="{lane_top}" data-bottom="{baseline}"><text x="20" y="{next_top}">{label}</text>')
        parts.append(f'<line x1="{dot_origin}" y1="{baseline}" x2="{dot_origin+dot_span}" y2="{baseline}" stroke="#ccd5cd"/>')
        seen = {}
        for value in validated:
            repeat = seen.get(value, 0)
            seen[value] = repeat + 1
            x = dot_origin + dot_span * value / maximum
            parts.append(f'<circle class="rate-observation" cx="{x}" cy="{baseline-9-18*repeat}" r="7" fill="{color}"/>')
        # The triangle uses the measured median, not an illustrative midpoint.
        # Mutation: RM-MEDIAN. Evidence: test_median_markers_use_actual_medians.
        median = record['rate_median']
        if median is not None:
            x = dot_origin + dot_span * number(median) / maximum
            parts.append(f'<path class="median-marker" d="M{x} {baseline+2} l-6 11 h12 Z" fill="{color}"/>')
        for tick in sorted({0, *rates}):
            parts.append(f'<text class="rate-tick" x="{dot_origin + dot_span*tick/maximum}" y="{baseline+32}" text-anchor="middle" font-size="11">{esc(display(tick))}</text>')
        parts.append(f'<text x="20" y="{baseline+57}" font-size="13">n={record["rate_n"]}; median {esc(display(median))}</text></g>')
        next_top = baseline + 107
    caption = ['Synthetic rate: participants per month, per trial.', 'Unweighted median; middle pair averaged for even n.']
    for index, line in enumerate(caption):
        parts.append(f'<text x="20" y="{next_top+index*19}" font-size="{11 if compact else 13}">{line}</text>')
    height = next_top + 44
    identity = ('compact-' if compact else '') + 'comparison-' + scenario['id']
    return svg_open(width, height, identity, context(scenario), 'Bars start at zero on a common scale. Each dot is one observed rate; triangles are medians.') + ''.join(parts) + '</g></svg>'


def geography_svg(scenario, compact=False):
    """Show every recorded country and pair methods on a shared zero scale.

    Evidence: test_geography_bars_bind_every_group_method_and_value checks both
    layouts, missing and zero values, map order, exact labels and scale. Country
    filtering is the lab's controlled extension, disclosed in the HTML report.
    """
    result = scenario['result']
    correct, wrong = result['geography'], {g['country']: g for g in result['incorrect']['geography']}
    # A geography figure names its grouped output, not the unrelated statistics
    # query's row count. The map always joins sites, even without a filter.
    # Evidence: test_geographic_header_uses_country_group_denominator.
    geographic_context = context(scenario).replace(f"{len(result['joined_rows'])} query rows",
                                                  f"{len(correct)} country groups; map always joins sites")
    width, span = (340, 260) if compact else (1000, 600)
    header = textwrap.wrap(geographic_context, 40 if compact else 112)
    parts = [f'<text x="20" y="{24+i*18}" font-size="{11 if compact else 14}">{esc(line)}</text>' for i, line in enumerate(header)]
    y = 38 + len(header) * 18
    maximum = max([number(g['trial_enrollment_sum']) for g in [*correct, *wrong.values()] if g['trial_enrollment_sum'] is not None] + [1])
    for group in correct:
        country = group['country']
        parts.append(f'<text x="20" y="{y}" font-weight="700">{esc(country)} · {group["trial_count"]} {"trial" if group["trial_count"] == 1 else "trials"}; known n={group["known_enrollment_n"]}</text>')
        y += 20
        for method, record, color in (('Joined', wrong[country], '#b45e3c'), ('Identity', group, '#2a7559')):
            value = record['trial_enrollment_sum']
            bar = number(value) / maximum * span if value is not None else 0
            parts.append(f'<rect class="geography-bar" data-country="{country}" data-method="{method}" x="20" y="{y}" width="{bar}" height="18" fill="{color}"/>')
            parts.append(f'<text x="20" y="{y+35}" font-size="13">{method}: {esc(display(value))}</text>')
            y += 58
        y += 15
    if not correct:
        parts.append(f'<text x="20" y="{y}">No known-country group.</text>')
        y += 30
    parts.append(f'<text x="20" y="{y}" font-size="{11 if compact else 14}">Trial-wide totals; overlapping countries are not additive.</text>')
    return svg_open(width, y+25, ('compact-' if compact else '')+'geography-'+scenario['id'], geographic_context, 'TrialCat map joins sites even with no geographic filter. Bars compare joined sums with unique trial-country pairs.') + ''.join(parts) + '</g></svg>'


def sweep_svg(points, compact=False):
    """Plot stored SQL results and derive every numeric caption from those rows.

    Evidence: test_sweep_coordinates_and_ticks_match_every_record and
    test_sweep_legend_changes_with_values challenge coordinates and prose
    independently, in both layouts. Zero is the shared vertical origin.
    """
    width, left, span = (340, 40, 270) if compact else (1000, 80, 840)
    maximum = max([number(p['stats'][key]['enrollment_sum']) for p in points for key in ('incorrect', 'corrected')] + [1])
    x = lambda i: left + i / max(1, len(points)-1) * span
    y = lambda v: 310 - number(v) / maximum * 190
    counts = sorted({p['stats']['corrected']['trial_count'] for p in points})
    cohort_label = f'{counts[0]} trial' + ('' if counts[0] == 1 else 's') if len(counts) == 1 else 'a varying trial cohort'
    parts = [f'<text x="20" y="30" font-weight="700">Add a site. Observe {esc(cohort_label)}.</text>']
    for value in (0, maximum / 2, maximum):
        parts.append(f'<line class="sweep-grid" x1="{left}" x2="{left+span}" y1="{y(value)}" y2="{y(value)}" stroke="#dce4dc"/>')
        parts.append(f'<text class="sweep-y-tick" x="{left-5}" y="{y(value)+4}" text-anchor="end" font-size="10">{display(value)}</text>')
    for key, color, dash in (('incorrect', '#b45e3c', ' stroke-dasharray="7 4"'), ('corrected', '#2a7559', '')):
        coords = ' '.join(f'{x(i)},{y(p["stats"][key]["enrollment_sum"])}' for i,p in enumerate(points))
        parts.append(f'<polyline data-method="{key}" points="{coords}" fill="none" stroke="{color}" stroke-width="3"{dash}/>')
        for i,p in enumerate(points):
            value = p['stats'][key]['enrollment_sum']
            parts.append(f'<circle cx="{x(i)}" cy="{y(value)}" r="4" fill="{color}"/>')
            if not compact or i in (0,5,10):
                parts.append(f'<text x="{x(i)}" y="{y(value)+18 if key == "corrected" else y(value)-10}" text-anchor="middle" font-size="12">{display(value)}</text>')
    for i,p in enumerate(points):
        parts.append(f'<text x="{x(i)}" y="335" text-anchor="middle" font-size="11">{p["extra_sites"]}</text>')
    identities = sorted({p['stats']['corrected']['enrollment_sum'] for p in points})
    identity_label = display(identities[0]) if len(identities) == 1 else f'{display(min(identities))} to {display(max(identities))}'
    first, last = points[0], points[-1]
    description = (f'{first["extra_sites"]} to {last["extra_sites"]} extra sites; {cohort_label}. '
                   f'Joined sum {display(first["stats"]["incorrect"]["enrollment_sum"])} to {display(last["stats"]["incorrect"]["enrollment_sum"])}; identity sum {identity_label}.')
    captions = ['Extra matching sites; each tick is a measured position.',
                f'Dashed: joined sum. Solid: identity sum ({identity_label}).',
                'Invented cohort; every point executes SQLite.']
    caption_y = 365
    for caption in captions:
        for line in textwrap.wrap(caption, 40 if compact else 112):
            parts.append(f'<text x="20" y="{caption_y}" font-size="{11 if compact else 13}">{esc(line)}</text>')
            caption_y += 18
        caption_y += 6
    return svg_open(width, caption_y+5, 'compact-sweep' if compact else 'site-sweep', 'Site multiplicity sweep', description) + ''.join(parts) + '</g></svg>'


def responsive(scenario, renderer, name):
    return f'<div class="visual quantitative desktop" data-figure="{name}">{renderer(scenario)}</div><div class="visual quantitative compact" data-figure="{name}">{renderer(scenario, compact=True)}</div>'


def make_html(report):
    options, panels = [], []
    for index, scenario in enumerate(report['scenarios']):
        result = scenario['result']
        options.append(f'<option value="{esc(scenario["id"])}">{esc(scenario.get("category", "Example"))} · {esc(scenario["title"])}</option>')
        rows = []
        for label, key in (('Distinct trial count', 'trial_count'), ('Trial-wide enrollment sum', 'enrollment_sum'), ('Known rate observations', 'rate_n'), ('Unweighted median rate', 'rate_median')):
            rendered = [display(result[method][key]) for method in ('incorrect', 'corrected')]
            if key == 'enrollment_sum' and result['corrected']['trial_count'] == 0:
                rendered = ['no trials (n=0)'] * 2
            rows.append(f'<tr><th>{label}</th><td>{esc(rendered[0])}</td><td>{esc(rendered[1])}</td></tr>')
        groups = ''.join(f'<tr><td>{g["country"]}</td><td>{g["trial_count"]}</td><td>{g["known_enrollment_n"]}</td><td>{esc(display(g["trial_enrollment_sum"]))}</td></tr>' for g in result['geography']) or '<tr><td colspan="4">No known-country group.</td></tr>'
        panels.append(f'''<section class="scenario" id="{esc(scenario['id'])}" {('hidden' if index else '')}>
<p class="tag">{esc(scenario.get('category', 'Example'))}</p><h2>{esc(scenario['title'])}</h2><p>{esc(scenario['description'])}</p>
<p class="caption">Country: {esc(result['filters']['country'] or 'all')} · Intervention: {esc(result['filters']['intervention_kind'] or 'all')} · Invented trial-wide values</p>
{responsive(scenario, comparisons_svg, 'comparison')}
<p class="caption">Rate unit: participants per month, per trial, supplied as a synthetic value. Median is unweighted; for even n it averages the middle two observations. Bars share a zero origin within each scenario. Exact values appear below.</p>
<table><thead><tr><th>Metric</th><th>Flawed query</th><th>Identity-correct</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p><code>SUM(DISTINCT enrollment)</code> gives <b>{esc(display(result['incorrect']['misleading_distinct_sum']))}</b>; equal-valued independent trials must remain independent.</p>
<h3>The country map joins sites even without a filter.</h3>{responsive(scenario, geography_svg, 'geography')}
<table class="country-table"><thead><tr><th>Country</th><th>Trials</th><th>Known enrollment n</th><th>Trial-wide enrollment</th></tr></thead><tbody>{groups}</tbody></table>
<p class="note">Historical map fidelity: unfiltered calls match the inspected TrialCat bug. With an explicit country filter, this lab applies the filter to both arms as a controlled extension; the historical map ignored that filter.</p>
<p class="note">These are total enrollments of trials with sites in a country, <b>not participants enrolled in that country</b>. Countries overlap and totals are not additive.</p>
<h3>Inspect the row identities</h3><div class="visual identity" tabindex="0" aria-label="Scrollable identity graph">{provenance_svg(scenario)}</div>
<p class="caption">Connections follow actual SQL rows. Orange rows repeat a trial. On a phone this optional identity graph scrolls; the quantitative comparisons above fit the screen.</p>
<p>{result['corrected']['trial_count']} selected {"trial" if result['corrected']['trial_count'] == 1 else "trials"}; {result['corrected']['known_enrollment_n']} known enrollments; {result['corrected']['rate_n']} known rates. Excluded IDs: {esc(', '.join(result['excluded_trial_ids']) or 'none')}.</p>
<details><summary>Inspect source tables, SQL, parameters and observations</summary><pre>{esc(json.dumps({'source_tables':scenario['data'],'result':result},indent=2))}</pre></details>
<p><a href="figures/{esc(scenario['id'])}-identity.svg">Identity SVG</a> · <a href="figures/{esc(scenario['id'])}-comparison.svg">Comparison SVG</a> · <a href="figures/{esc(scenario['id'])}-geography.svg">Country SVG</a></p></section>''')
    points = report.get('site_sweep', [])
    sweep = ''
    if points:
        table = ''.join(f'<tr><td>{p["extra_sites"]}</td><td>{display(p["stats"]["incorrect"]["enrollment_sum"])}</td><td>{display(p["stats"]["corrected"]["enrollment_sum"])}</td></tr>' for p in points)
        sweep = '<section id="sweep"><h2>Turn the site dial.</h2><p>The cohort remains three trials. Each position runs both the filtered statistics query and the unfiltered country-map query.</p><label for="site-dial">Extra US sites on T1</label><input id="site-dial" type="range" min="0" max="10" value="0"><output id="site-readout"></output><p id="map-readout"></p><div class="visual desktop">' + sweep_svg(points) + '</div><div class="visual compact">' + sweep_svg(points, True) + '</div><table><thead><tr><th>Extra sites</th><th>Joined sum</th><th>Identity sum</th></tr></thead><tbody>' + table + '</tbody></table><p><a href="figures/site-sweep.svg">Download measured sweep</a></p></section>'
    data = json.dumps(points, ensure_ascii=False).replace('<', '\\u003c')
    first = report['scenarios'][0]['result']
    hero = f"Same {first['corrected']['trial_count']} trials: joined total {display(first['incorrect']['enrollment_sum'])} · identity-correct total {display(first['corrected']['enrollment_sum'])}."
    return TEMPLATE.replace('<!--HERORESULT-->', esc(hero)).replace('<!--OPTIONS-->', ''.join(options)).replace('<!--PANELS-->', ''.join(panels)).replace('<!--SWEEP-->', sweep).replace('<!--DATA-->', data)


TEMPLATE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Registry Metric Lab | Count identities before values</title><style>
:root{--ink:#16382f;--muted:#52665f;--paper:#f4f1e7;--line:#c5cfc6;--green:#2a7559}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 system-ui,sans-serif}header{padding:24px max(24px,6vw);background:var(--ink);color:#fffdf3}h1{font:clamp(34px,4vw,54px)/1.08 Georgia,serif;margin:15px 0}header p{max-width:950px;margin:12px 0}.hero-result{font-size:24px;color:#e5d8a5}main{max-width:1200px;margin:auto;padding:24px}h2{font:31px/1.2 Georgia,serif;margin:20px 0 10px}h3{font-size:20px}.notice{padding:12px 18px;border-left:4px solid var(--green);background:#e4ece1}.picker{display:flex;align-items:center;gap:18px;flex-wrap:wrap;margin:22px 0}select{font:inherit;max-width:100%;padding:10px;border:1px solid var(--line);background:#fffdf7}.tag{font-size:13px;font-weight:700;color:#84502f}.visual{background:#fffdf7;border:1px solid var(--line);margin:18px 0}.visual svg{display:block;width:100%}.identity{overflow:auto}.identity svg{min-width:1000px}.caption,.note{font-size:14px;color:var(--muted)}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;vertical-align:top;padding:10px 8px;border-bottom:1px solid var(--line)}thead{background:#e5e9df}details{padding:16px;background:#fffdf7;border:1px solid var(--line);margin:20px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace}a{color:var(--green)}:focus-visible{outline:3px solid #b45e3c;outline-offset:3px}footer{border-top:1px solid var(--line);margin-top:35px;padding-top:18px;font-size:14px;color:var(--muted)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.compact{display:none}[hidden]{display:none!important}#site-dial{width:100%;accent-color:var(--green)}#site-readout{display:block;font-weight:700;font-size:20px}@media(max-width:740px){.desktop{display:none}.compact{display:block}main{padding:16px}.hero-result{font-size:21px}h2{font-size:27px}table{font-size:12px}th,td{padding:8px 4px}}
</style></head><body><header><p>The Real Cat Labs · Health data engineering</p><h1>Count trial identities.<br>Then calculate the metric.</h1><p class="hero-result"><!--HERORESULT--></p><p>A matching site selects a trial. It must not give that trial another vote in a trial-level sum.</p></header><main><div class="notice"><b>Synthetic engineering demonstration.</b> Invented records; actual SQLite outputs. No clinical data, live registry or model calls.</div><div class="picker"><label for="scenario-picker">Explore a failure or control</label><select id="scenario-picker" autocomplete="off"><!--OPTIONS--></select></div><div id="scenario-status" class="sr-only" aria-live="polite"></div><!--PANELS--><!--SWEEP--><footer><p>Identity-grain aggregation prevents join multiplication. It does not validate proxy rates or reveal site-level enrollment.</p><p><a href="results.json">Results and source hashes</a> · <a href="../docs/report.md">Methods and limits</a> · <a href="../README.md">Run from source</a></p><p>Host the package root to preserve documentation links. Reproduce: <code>python -B -m registry_metrics --out artifacts</code>.</p></footer></main><script type="application/json" id="sweep-data"><!--DATA--></script><script>
'use strict';const picker=document.getElementById('scenario-picker');function syncScenario(){document.querySelectorAll('.scenario').forEach(panel=>panel.hidden=panel.id!==picker.value);document.getElementById('scenario-status').textContent='Showing '+picker.options[picker.selectedIndex].text;}picker.addEventListener('change',syncScenario);document.addEventListener('DOMContentLoaded',syncScenario);window.addEventListener('pageshow',syncScenario);syncScenario();
const points=JSON.parse(document.getElementById('sweep-data').textContent),dial=document.getElementById('site-dial');if(dial){const format=value=>value===null?'unknown':value.toLocaleString('en-US');const show=()=>{const p=points[Number(dial.value)];document.getElementById('site-readout').textContent=p.extra_sites+' extra '+(p.extra_sites===1?'site':'sites')+': joined '+format(p.stats.incorrect.enrollment_sum)+'; identity '+format(p.stats.corrected.enrollment_sum);const before=Object.fromEntries(p.world.incorrect.geography.map(g=>[g.country,g.trial_enrollment_sum])),after=Object.fromEntries(p.world.geography.map(g=>[g.country,g.trial_enrollment_sum]));document.getElementById('map-readout').textContent='Unfiltered country map: US joined '+format(before.US)+' vs identity '+format(after.US)+'; CA joined '+format(before.CA)+' vs identity '+format(after.CA)+'. All values are trial-wide enrollments.';};dial.addEventListener('input',show);show();}
</script></body></html>'''
