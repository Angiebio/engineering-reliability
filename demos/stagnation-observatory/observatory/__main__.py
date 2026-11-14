"""Generate results.json, summary.svg and the offline interactive report.

Purpose: connect fixture evidence, actual replay and denominated evaluation.
Contract: trusted specs and pins enter replay separately from agent events and
artifact bytes. Labels encode the same policy by construction, not useful work.
Invariant: observed outcomes and figure counts come from retained replay data;
policy annotations name the recorded configuration, whose values are authored.
Rationale: a skeptical reader should reproduce the chart from its source data.
Failure: validation errors stop the run; controls fail if wiring is disconnected.
Evidence: test_cli_reproduces_results and metric accounting tests.
"""
import argparse
import json
from pathlib import Path
import platform
from .core import canonical, replay, sha256
from . import core
from .fixtures import FAMILIES, PARAPHRASES, event, fixture_bank
from .report import make_html, summary_svg, cadence_svg


def predicted(row: dict, strategy: str) -> bool:
    return row['status'] == 'alert' if strategy == 'progress' else row[strategy + '_alert']


def evaluate(traces: list[dict], labels: dict, harness: dict) -> tuple[list[dict], dict]:
    records = []
    confusion = {name: dict(tp=0, fp=0, fn=0, tn=0) for name in ('exact', 'lexical', 'progress')}
    for trace in traces:
        output = replay(trace, **harness[trace['trace_id']])
        label = labels[trace['trace_id']]
        positive = set(label['positive_event_ids'])
        expected_ticks = [r['event']['tick'] for r in output['rows'] if r['event']['event_id'] in positive]
        summary = {'expected_first_tick': min(expected_ticks) if expected_ticks else None}
        for name in confusion:
            alerts = [r['event']['tick'] for r in output['rows'] if predicted(r, name)]
            summary[name] = {'alerts': len(alerts), 'first_alert_tick': min(alerts) if alerts else None}
            for row in output['rows']:
                actual = row['event']['event_id'] in positive
                called = predicted(row, name)
                key = 'tp' if actual and called else 'fp' if called else 'fn' if actual else 'tn'
                confusion[name][key] += 1
        records.append({'trace_id': trace['trace_id'], 'label': label, 'replay': output, 'summary': summary})
    metrics = {}
    for name, count in confusion.items():
        total = sum(count.values())
        metrics[name] = {**count, 'events': total,
                         'precision': round(count['tp']/(count['tp']+count['fp']), 4) if count['tp']+count['fp'] else None,
                         'recall': round(count['tp']/(count['tp']+count['fn']), 4) if count['tp']+count['fn'] else None,
                         'false_alerts_per_100_events': round(count['fp'] / total * 100, 4)}
    return records, metrics


def controls(traces: list[dict], labels: dict, harness: dict) -> list[dict]:
    import copy
    cosmetic = next(t for t in traces if labels[t['trace_id']]['family'] == 'cosmetic_work')
    inputs = harness[cosmetic['trace_id']]
    checked, bypassed = replay(cosmetic, **inputs), replay(cosmetic, **inputs, trust_claims_ablation=True)
    count = lambda result: sum(row['status'] == 'alert' for row in result['rows'])
    if count(checked) == 0 or count(bypassed) != 0:
        raise RuntimeError('evidence-validator ablation did not change outcome')
    good = next(t for t in traces if labels[t['trace_id']]['family'] == 'verified_work')
    good_inputs = harness[good['trace_id']]
    corrupt_inputs = copy.deepcopy(good_inputs)
    corrupt_inputs['store']['output1'] += ' '
    missing_inputs = copy.deepcopy(good_inputs)
    del missing_inputs['store']['output1']
    bad = replay(good, **corrupt_inputs)['rows'][0]
    absent = replay(good, **missing_inputs)['rows'][0]
    if bad['status'] != 'evidence_error' or absent['status'] != 'evidence_error':
        raise RuntimeError('invalid evidence control failed')
    sparse = copy.deepcopy(good)
    sparse['trace_id'] = 'sparse-checkpoint'
    # A completed artifact at tick five does not retroactively prove what was
    # happening at tick four. This control exposes the monitor's observability
    # assumption: useful work without intermediate acceptance evidence can alert.
    for index in (1, 2, 3):
        sparse['events'][index] = event(sparse['task_id'], index + 1, 'The longer document check is still running.')
    sparse_result = replay(sparse, **good_inputs)
    sparse_alerts = [r['event']['tick'] for r in sparse_result['rows'] if r['status'] == 'alert']
    if sparse_alerts != [4] or sparse_result['rows'][4]['status'] != 'progress':
        raise RuntimeError('sparse-checkpoint limitation control changed')
    near = copy.deepcopy(next(t for t in traces if labels[t['trace_id']]['family'] == 'exact_loop'))
    near_inputs = harness[near['trace_id']]
    near['trace_id'] = 'near-match-text'
    near['events'] = [event(near['task_id'], tick, f'Checked {tick} of 40 packet sections.') for tick in range(1, 7)]
    near_result = replay(near, **near_inputs)
    if any(row['exact_alert'] for row in near_result['rows']) or not any(row['lexical_alert'] for row in near_result['rows']):
        raise RuntimeError('near-match control failed to separate text baselines')
    return [
        {'title': 'Validator connected', 'description': 'Changing files fail separately supplied item criteria. No new criterion is accepted.',
         'outcome': f'{count(checked)} no-progress alerts; {len(checked["completed"])} criteria accepted'},
        {'title': 'Validator bypassed on purpose', 'description': 'Trusting result claims turns cosmetic changes into apparent progress. This unsafe arm demonstrates the validator matters.',
         'outcome': f'{count(bypassed)} no-progress alerts; {len(bypassed["completed"])} claims accepted'},
        {'title': 'Evidence integrity checked', 'description': 'Bytes that no longer match the separately pinned digest, and missing artifacts, become evidence errors. Matching a pin does not prove authorship or work quality.',
         'outcome': bad['reason'] + ' / ' + absent['reason']},
        {'title': 'Useful work can lack a checkpoint', 'kind': 'sparse_checkpoint',
         'description': 'A long check supplies no new artifact until tick five. The monitor alerts at tick four, then accepts the result. This is an observability limitation, not proof that the work was stalled.',
         'outcome': 'Alert at tick 4; verified progress at tick 5', 'trace': sparse, 'replay': sparse_result,
         'harness_inputs': good_inputs},
        {'title': 'Near-match text separates the baselines', 'kind': 'lexical_separation',
         'description': 'A changing counter keeps the exact strings distinct while lexical similarity exceeds its threshold. This control is outside the policy matrix.',
         'outcome': f"Exact alerts: {sum(r['exact_alert'] for r in near_result['rows'])}; lexical alerts: {sum(r['lexical_alert'] for r in near_result['rows'])}",
         'trace': near, 'replay': near_result, 'harness_inputs': near_inputs},
    ]


def cadence_sweep(traces: list[dict], labels: dict, harness: dict) -> dict:
    """Measure the event-cadence boundary on invented completed tasks.

    Contract: six accepted milestones with five gaps, each containing k status
    events, compared with a no-result trace of the same length. All plotted
    counts are replay outputs; expected counts are regression expectations only.
    Invariant: cadence controls never enter the main policy-conformance matrix.
    Rationale: healthy work can trigger alerts when evidence arrives too slowly.
    Evidence: test_cadence_three_status_events_exposes_five_alerts.
    """
    import copy
    original = next(t for t in traces if labels[t['trace_id']]['family'] == 'verified_work')
    inputs = harness[original['trace_id']]
    points = []
    for gap in range(7):
        healthy = {'trace_id': f'cadence-healthy-{gap}', 'task_id': original['task_id'], 'events': []}
        for index, milestone in enumerate(original['events']):
            if index:
                for _ in range(gap):
                    tick = len(healthy['events']) + 1
                    healthy['events'].append(event(healthy['task_id'], tick, 'The longer document check is still running.'))
            record = copy.deepcopy(milestone)
            record['tick'] = len(healthy['events']) + 1
            record['event_id'] = f"event{record['tick']}"
            healthy['events'].append(record)
        stalled = {'trace_id': f'cadence-stalled-{gap}', 'task_id': original['task_id'],
                   'events': [event(original['task_id'], tick, PARAPHRASES[(tick - 1) % len(PARAPHRASES)])
                              for tick in range(1, len(healthy['events']) + 1)]}
        healthy_replay, stalled_replay = replay(healthy, **inputs), replay(stalled, **inputs)
        count = lambda result: sum(row['status'] == 'alert' for row in result['rows'])
        points.append({'status_messages': gap, 'healthy_alerts': count(healthy_replay),
                       'stalled_alerts': count(stalled_replay), 'events_per_trace': len(healthy['events']),
                       'healthy_trace': healthy, 'stalled_trace': stalled,
                       'healthy_replay': healthy_replay, 'stalled_replay': stalled_replay})
    return {'description': f'{len(original["events"])} accepted milestones, {len(original["events"]) - 1} gaps of k status events. No-result comparison uses the same event count. Authored controls, outside the matrix.',
            'milestones': len(original['events']), 'gaps': len(original['events']) - 1,
            'stall_window': core.STALL_WINDOW, 'harness_inputs': inputs, 'points': points}


def run(output: Path) -> dict:
    traces, labels, harness = fixture_bank()
    rows, metrics = evaluate(traces, labels, harness)
    sources = {p.name: sha256(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}
    result = {'protocol': 'stagnation-observatory-v2', 'python': platform.python_version(),
              'kind': 'deterministic development-fixture demonstration', 'model_calls': 0,
              'families': list(FAMILIES), 'fixture_sha256': sha256(canonical(traces)),
              'harness_sha256': sha256(canonical(harness)),
              'labels_sha256': sha256(canonical(labels)), 'code_sha256': sources,
              'metrics': metrics, 'controls': controls(traces, labels, harness), 'traces': rows,
              'cadence': cadence_sweep(traces, labels, harness)}
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (('traces.json', traces), ('labels.json', labels), ('results.json', result),
                        ('specifications.json', {key: value['spec'] for key, value in harness.items()}),
                        ('pinned-digests.json', {key: value['pinned_digests'] for key, value in harness.items()}),
                        ('artifact-store.json', {key: value['store'] for key, value in harness.items()})):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    for name, content in (('index.html', make_html(result)), ('summary.svg', summary_svg(result)),
                          ('cadence.svg', cadence_svg(result))):
        (output / name).write_text(content, encoding='utf-8', newline='\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('artifacts'))
    args = parser.parse_args()
    result = run(args.out)
    print(json.dumps({'traces': len(result['traces']), 'metrics': result['metrics'], 'output': str(args.out)}, indent=2))


if __name__ == '__main__':
    main()
