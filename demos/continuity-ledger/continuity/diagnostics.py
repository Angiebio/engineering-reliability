"""Run fixture sensitivity checks through the actual renderer, reader and gate.

Contract: these controls remain outside the original 24-history matrix. The
budget sweep executes in-process, not through a simulated or claimed restart.
Invariant: each count is recomputed from retained per-case decisions.
Rationale: note lengths and packing order explain the non-monotonic headline.
Failure: bad input raises through the same public core functions as the runner.
Evidence: test_budget_transition_points, test_natural_stale_proposal_comes_from_reader.
"""
import copy
from html import escape
from .core import check_proposal, propose, render_memory, validate_ledger

# Selected development budgets include both sides of every displayed transition.
# This is a sensitivity grid, not a threshold chosen on held-out histories.
# Evidence: test_budget_transition_points.
SWEEP_BUDGETS = sorted(set(range(200, 1001, 20)) | {243, 244, 284, 285, 286, 287, 288, 488, 489, 541, 542, 734, 735, 740, 741, 745, 746})


def natural_histories(histories: list[dict], labels: dict) -> list[dict]:
    """Lengthen terminal records so whole-record packing can omit current state.

    The administrative detail is authored, not a production event. It changes
    length without changing state. An older short active record can then fit
    while its longer terminal successor does not. This is a reader failure that
    occurs naturally from retained context, not an injected proposal literal.
    """
    # The 200-character administrative suffix is an authored development stress
    # parameter, not a measured optimum. It makes a terminal record longer than
    # an older request without changing state; other lengths can change failures.
    # Evidence: test_natural_suffix_changes_only_length_and_exposes_fixture_choice.
    filing = (' Filed as packet REF-2026-11-0042 with the signed checklist, reviewer initials, the archive'
              ' location and a short summary of what changed since the previous review cycle, so the next'
              ' reviewer can audit it without reopening the work.')[:200]
    result = []
    for original in histories:
        if labels[original['case_id']] == 'active':
            continue
        history = copy.deepcopy(original)
        history['case_id'] = 'natural-' + history['case_id']
        for event in history['events']:
            if event['kind'] in ('complete', 'pause', 'block', 'revoke'):
                event['text'] += filing
        result.append(history)
    return result


def budget_sweep(histories: list[dict], labels: dict, budgets=None, *, reference_budget=640) -> dict:
    """Measure eligible resumptions and unsafe decisions at sampled byte budgets."""
    bank = [(history, validate_ledger(history['events'])) for history in histories]
    points = []
    for budget in SWEEP_BUDGETS if budgets is None else budgets:
        point = {'budget_bytes': budget, 'strategies': {}}
        for strategy in ('raw_tail', 'timeline'):
            cases = []
            for history, events in bank:
                memory = render_memory(events, history['task_id'], strategy, budget)
                proposal = propose(memory['context'])
                gate = check_proposal(events, history['task_id'], proposal)
                cases.append({'case_id': history['case_id'], 'expected': labels[history['case_id']],
                              'proposal': proposal['action'], 'gate': gate['action'], 'reason': gate['reason'],
                              'used_bytes': memory['used_bytes'],
                              'retained_ids': [event['event_id'] for event in memory['context']['events']]})
            point['strategies'][strategy] = {
                'eligible_resumed': sum(c['expected'] == 'active' and c['gate'] == 'resume' for c in cases),
                'eligible_count': sum(c['expected'] == 'active' for c in cases),
                'unsafe_proposals': sum(c['expected'] != 'active' and c['proposal'] == 'resume' for c in cases),
                'unsafe_final': sum(c['expected'] != 'active' and c['gate'] == 'resume' for c in cases),
                'ineligible_count': sum(c['expected'] != 'active' for c in cases), 'cases': cases}
        points.append(point)
    return {'execution': 'in-process calls to render_memory, propose and check_proposal',
            'scope': 'Original authored histories; sampled context-byte budgets; outside process replay matrix',
            'reference_budget_bytes': reference_budget, 'points': points}


def transition_brackets(sweep: dict) -> list[dict]:
    """Describe observed changes without interpolating unmeasured byte budgets."""
    points = sorted(sweep['points'], key=lambda point: point['budget_bytes'])
    return [{'left_bytes': left['budget_bytes'], 'right_bytes': right['budget_bytes'],
             'before': left['strategies']['raw_tail']['eligible_resumed'],
             'after': right['strategies']['raw_tail']['eligible_resumed']}
            for left, right in zip(points, points[1:])
            if left['strategies']['raw_tail']['eligible_resumed'] != right['strategies']['raw_tail']['eligible_resumed']]


def sweep_svg(sweep: dict) -> str:
    """Plot measured sensitivity; carry the fixture dependence inside the SVG."""
    points = sorted(sweep['points'], key=lambda point: point['budget_bytes'])
    if not points:
        return ''
    maximum = max(p['strategies']['raw_tail']['eligible_count'] for p in points) or 1
    left, right = min(p['budget_bytes'] for p in points), max(p['budget_bytes'] for p in points)
    x = lambda budget: 80 + (budget - left) / max(1, right - left) * 900
    y = lambda count: 290 - count / maximum * 170
    reference = next((point for point in points if point['budget_bytes'] == sweep.get('reference_budget_bytes')), None)
    caption = ('At ' + str(reference['budget_bytes']) + ' bytes, raw tail resumes '
               + str(reference['strategies']['raw_tail']['eligible_resumed']) + '/' + str(maximum)
               + '; this is a fixture-dependent result.' if reference else 'Only measured points are shown; no value between them is inferred.')
    bits = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 460" role="img" aria-labelledby="budget-title budget-desc">',
            '<title id="budget-title">More memory can retain less useful evidence</title>',
            '<desc id="budget-desc">Measured eligible resumptions at sampled UTF-8 context budgets. Note lengths and whole-record packing create the raw-tail dip; this is not model performance.</desc>',
            '<rect width="1080" height="460" fill="#fff"/>',
            '<text x="30" y="40" font-family="Georgia,serif" font-size="27" fill="#152b40">More memory can retain less useful evidence</text>',
            '<text x="30" y="70" font-family="sans-serif" font-size="15" fill="#526273">In-process sensitivity sweep · actual renderer, reader and gate · authored histories</text>']
    for count in (0, maximum // 2, maximum):
        bits.append(f'<line x1="80" x2="980" y1="{y(count)}" y2="{y(count)}" stroke="#c2cecd"/><text x="62" y="{y(count)+5}" text-anchor="end" font-family="sans-serif">{count}</text>')
    # Samples do not justify a straight line through a packing discontinuity.
    # Each mark binds its budget/count for the SVG parse test and visible tooltip.
    # Evidence: test_sweep_svg_marks_and_caption_follow_supplied_points.
    for name, color in [('timeline', '#28745e'), ('raw_tail', '#ad562e')]:
        for point in points:
            count = point['strategies'][name]['eligible_resumed']
            radius, fill = (6, 'none') if name == 'timeline' else (3.5, color)
            bits.append(f'<circle data-strategy="{name}" data-budget="{point["budget_bytes"]}" data-count="{count}" cx="{x(point["budget_bytes"]):.2f}" cy="{y(count):.2f}" r="{radius}" fill="{fill}" stroke="{color}" stroke-width="1.5"><title>{name}: {count}/{maximum} at {point["budget_bytes"]} bytes</title></circle>')
    markers = {left, right}
    if reference:
        markers.add(reference['budget_bytes'])
    for budget in sorted(markers):
        if left <= budget <= right:
            bits.append(f'<line x1="{x(budget)}" x2="{x(budget)}" y1="100" y2="297" stroke="#6a7c81" stroke-dasharray="2 5"/><text x="{x(budget)}" y="320" text-anchor="middle" font-family="sans-serif">{budget}</text>')
    bits.extend([f'<text x="80" y="98" font-family="sans-serif" font-size="14">Eligible resumptions / {maximum}</text>',
                 '<text x="530" y="348" text-anchor="middle" font-family="sans-serif">UTF-8 bytes of the context object (transport wrapper excluded)</text>',
                 '<text x="80" y="376" font-family="sans-serif" fill="#ad562e">Raw tail: filled dots</text><text x="330" y="376" font-family="sans-serif" fill="#28745e">Timeline: hollow rings</text>',
                 '<text x="30" y="405" font-family="sans-serif" font-size="16">' + escape(caption) + '</text>',
                 '<text x="30" y="428" font-family="sans-serif" font-size="16">Dots are measured samples, not a continuous curve. Packing can change sharply between samples.</text>',
                 '<text x="30" y="450" font-family="sans-serif" font-size="14">Original matrix: no unsafe proposals by construction. Separate long-terminal controls expose stale proposals.</text></svg>'])
    return ''.join(bits)
