"""Review regressions at the trusted harness and exported-artifact boundary."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from observatory.__main__ import cadence_sweep, controls, evaluate, run
from observatory.core import replay
from observatory.fixtures import fixture_bank


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.traces, self.labels, self.harness = fixture_bank()

    def test_cadence_records_the_policy_that_executed(self):
        with patch('observatory.core.STALL_WINDOW', 4):
            sweep = cadence_sweep(self.traces, self.labels, self.harness)
        self.assertEqual(sweep['stall_window'], 4)
        self.assertEqual([point['healthy_alerts'] for point in sweep['points']], [0, 0, 0, 0, 5, 10, 15])

    def test_cadence_three_status_events_exposes_five_alerts(self):
        sweep = cadence_sweep(self.traces, self.labels, self.harness)
        self.assertEqual([p['status_messages'] for p in sweep['points']], list(range(7)))
        self.assertEqual([p['healthy_alerts'] for p in sweep['points']], [0, 0, 0, 5, 10, 15, 20])
        for point in sweep['points']:
            self.assertEqual(len(point['healthy_replay']['completed']), 6)
            self.assertEqual(point['healthy_replay']['rows'][-1]['status'], 'progress')
            self.assertEqual(point['events_per_trace'], 6 + 5 * point['status_messages'])

    def test_cadence_comparator_has_same_budget_and_no_accepted_milestones(self):
        sweep = cadence_sweep(self.traces, self.labels, self.harness)
        for point in sweep['points']:
            self.assertEqual(len(point['healthy_trace']['events']), len(point['stalled_trace']['events']))
            self.assertEqual(point['stalled_alerts'], point['events_per_trace'] - 2)
            self.assertEqual(point['stalled_replay']['completed'], [])
            self.assertFalse(any(row['new_progress'] for row in point['stalled_replay']['rows']))

    def test_controls_separate_lexical_signal_without_entering_main_matrix(self):
        control_records = controls(self.traces, self.labels, self.harness)
        near = next(record for record in control_records if record.get('kind') == 'lexical_separation')
        sparse = next(record for record in control_records if record.get('kind') == 'sparse_checkpoint')
        self.assertEqual(sum(row['exact_alert'] for row in near['replay']['rows']), 0)
        self.assertEqual(sum(row['lexical_alert'] for row in near['replay']['rows']), 4)
        self.assertEqual([row['event']['tick'] for row in sparse['replay']['rows'] if row['status'] == 'alert'], [4])
        rows, metrics = evaluate(self.traces, self.labels, self.harness)
        self.assertEqual(len(rows), 24)
        for name, expected in [('exact', [44, 36, 16, 56]), ('lexical', [44, 36, 16, 56]), ('progress', [60, 0, 0, 92])]:
            self.assertEqual([metrics[name][key] for key in ('tp', 'fp', 'fn', 'tn')], expected)

    def test_exported_separate_inputs_reproduce_recorded_decisions(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            result = run(output)
            read = lambda name: json.loads((output / name).read_text(encoding='utf-8'))
            specs, pins, stores = read('specifications.json'), read('pinned-digests.json'), read('artifact-store.json')
            recorded = {row['trace_id']: row['replay'] for row in result['traces']}
            for trace in read('traces.json'):
                self.assertEqual(set(trace), {'trace_id', 'task_id', 'events'})
                key = trace['trace_id']
                actual = replay(trace, spec=specs[key], pinned_digests=pins[key], store=stores[key])
                self.assertEqual(actual, recorded[key])

    def test_all_generated_files_use_lf_and_regenerate_identically(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / 'first', Path(temporary) / 'second'
            run(first)
            run(second)
            self.assertEqual({p.name for p in first.iterdir()}, {
                'traces.json', 'labels.json', 'results.json', 'specifications.json',
                'pinned-digests.json', 'artifact-store.json', 'index.html', 'summary.svg', 'cadence.svg'})
            for artifact in first.iterdir():
                with self.subTest(artifact=artifact.name):
                    raw = artifact.read_bytes()
                    self.assertNotIn(b'\r', raw)
                    self.assertEqual(raw, (second / artifact.name).read_bytes())


if __name__ == '__main__':
    unittest.main()
