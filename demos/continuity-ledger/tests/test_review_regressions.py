"""Discriminating regressions for Flame's observed coverage gaps."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from continuity import __main__ as runner
from continuity.core import Event, canonical, check_proposal, propose, render_memory, validate_ledger
from continuity.diagnostics import SWEEP_BUDGETS, budget_sweep, natural_histories
from continuity.fixtures import fixture_bank


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.histories, self.labels = fixture_bank()

    def reduced(self, index=13):
        history = self.histories[index]
        return [history], {history['case_id']: self.labels[history['case_id']]}

    def test_current_head_forgery_is_unbound(self):
        history = self.histories[0]
        events = validate_ledger(history['events'])
        proposal = propose(render_memory(events, history['task_id'], 'timeline', 640)['context'])
        self.assertEqual(check_proposal(events, history['task_id'], proposal)['action'], 'resume')
        proposal['evidence']['text'] += ' Forged current permission.'
        result = check_proposal(events, history['task_id'], proposal)
        self.assertEqual(result['action'], 'hold')
        self.assertEqual(result['reason'], 'unbound_evidence')

    def test_natural_stale_proposal_comes_from_reader(self):
        caught = []
        for history in natural_histories(self.histories, self.labels):
            events = validate_ledger(history['events'])
            proposal = propose(render_memory(events, history['task_id'], 'raw_tail', 640)['context'])
            if proposal['action'] == 'resume':
                gate = check_proposal(events, history['task_id'], proposal)
                self.assertEqual((gate['action'], gate['reason']), ('hold', 'stale_evidence'))
                caught.append(history['case_id'])
        self.assertEqual(caught, ['natural-case14', 'natural-case18', 'natural-case22'])

    def test_natural_control_traverses_run_and_real_ablation(self):
        histories, labels = self.reduced()
        with tempfile.TemporaryDirectory() as temporary:
            result = runner.run(Path(temporary), histories=histories, labels=labels)
        row = next(row for row in result['natural_rows'] if row['strategy'] == 'raw_tail')
        bypass = result['gate_off_rows'][0]
        self.assertEqual(row['proposal']['action'], 'resume')
        self.assertEqual((row['gate']['action'], row['gate']['reason']), ('hold', 'stale_evidence'))
        self.assertEqual(bypass['proposal'], row['proposal'])
        self.assertEqual((bypass['gate']['action'], bypass['gate']['reason']), ('resume', 'gate_bypassed'))
        self.assertFalse(bypass['gate_enabled'])
        self.assertEqual(result['process_invocations'], 14)
        for observed in (row, bypass):
            self.assertNotEqual(observed['processes']['proposal'], os.getpid())
            self.assertNotEqual(observed['processes']['restore'], os.getpid())

    def test_budget_transition_points(self):
        self.assertEqual(runner.BUDGET, 640)
        self.assertEqual((min(SWEEP_BUDGETS), max(SWEEP_BUDGETS)), (200, 1000))
        self.assertTrue({541, 542, 640, 745, 746}.issubset(SWEEP_BUDGETS))
        points = budget_sweep(self.histories, self.labels, [541, 542, 745, 746])['points']
        self.assertEqual([p['strategies']['raw_tail']['eligible_resumed'] for p in points], [12, 9, 11, 12])
        self.assertTrue(all(p['strategies']['timeline']['eligible_resumed'] == 12 for p in points))

    def test_unicode_changes_record_selection(self):
        task = 't' * 80
        texts = ['Start the café review packet.', '注意：外部メモ — これは承認ではありません。' * 3,
                 'Emoji note 🔥🔥🔥 ' * 6, 'Plain ASCII note about the checklist wording only.']
        records = [Event('e' * 79 + '1', task, 1, 'request', 'controller', texts[0]).record()]
        records += [Event('e' * 79 + str(i), task, i, 'note', 'external', text).record() for i, text in enumerate(texts[1:], 2)]
        raw = canonical({'task_id': task, 'events': records})
        budget = len(raw.decode('utf-8'))
        self.assertEqual((len(raw), budget), (1577, 1396))
        selected = render_memory(validate_ledger(records), task, 'raw_tail', budget)
        self.assertEqual(len(selected['context']['events']), 3)
        self.assertEqual(selected['used_bytes'], 1280)
        self.assertLessEqual(len(canonical(selected['context'])), budget)

    def test_worker_rejects_label_fields(self):
        # Parent schema rejection is checked before transport, independently of
        # the worker's own defense; otherwise a child guard masks its deletion.
        with patch.object(runner.subprocess, 'run', side_effect=AssertionError('transport must not run')):
            for request in ({'operation': 'propose', 'context': {}, 'expected': 'active'},
                            {'operation': 'restore', 'directory': '.', 'manifest': {}, 'task_id': 'task',
                             'strategy': 'raw_tail', 'budget': 640, 'expected': 'active'}):
                with self.subTest(operation=request['operation']), self.assertRaisesRegex(ValueError, 'worker input fields'):
                    runner.worker(request)

    def test_run_worker_input_contract_and_label_timing(self):
        histories, labels = self.reduced(0)
        original = runner.worker
        captured = []
        def inspect(request):
            expected = ({'operation', 'directory', 'manifest', 'task_id', 'strategy', 'budget'}
                        if request['operation'] == 'restore' else {'operation', 'context'})
            self.assertEqual(set(request), expected)
            if request['operation'] == 'restore':
                self.assertFalse((Path(request['directory']).parent / 'labels.json').exists())
            captured.append(copy.deepcopy(request))
            return original(request)
        with tempfile.TemporaryDirectory() as temporary, patch.object(runner, 'worker', side_effect=inspect):
            runner.run(Path(temporary), histories=histories, labels=labels)
        self.assertEqual(len(captured), 6)

    def test_same_process_reply_is_rejected(self):
        reply = SimpleNamespace(stdout=canonical({'pid': os.getpid(), 'value': {}}))
        with patch.object(runner.subprocess, 'run', return_value=reply), self.assertRaisesRegex(RuntimeError, 'fresh-process'):
            runner.worker({'operation': 'propose', 'context': {}})

    def test_worker_reports_snapshot_failure_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            from continuity.storage import persist
            manifest = persist(Path(temporary), self.histories[0]['events'])
            (Path(temporary) / manifest['filename']).write_bytes(b'broken')
            with self.assertRaisesRegex(RuntimeError, 'snapshot integrity check failed'):
                runner.worker({'operation': 'restore', 'directory': temporary, 'manifest': manifest,
                               'task_id': self.histories[0]['task_id'], 'strategy': 'raw_tail', 'budget': 640})

    def test_worker_root_cannot_shadow_stdlib(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            shutil.copytree(Path(__file__).resolve().parents[1] / 'continuity', directory / 'continuity')
            (directory / 'dataclasses.py').write_text('raise RuntimeError("SHADOWED")', encoding='utf-8')
            run = subprocess.run([sys.executable, '-I', '-B', str(directory / 'continuity/worker.py')],
                                 input=canonical({'operation': 'propose', 'context': {'task_id': 'task', 'events': []}}),
                                 capture_output=True, check=True)
            self.assertEqual(json.loads(run.stdout)['value']['action'], 'abstain')

    def test_failed_generation_keeps_previous_complete_artifacts(self):
        histories, labels = self.reduced(0)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'artifacts'
            runner.run(destination, histories=histories, labels=labels)
            before = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
            with patch.object(runner, 'worker', side_effect=RuntimeError('injected failure')), self.assertRaisesRegex(RuntimeError, 'injected failure'):
                runner.run(destination, histories=histories, labels=labels)
            after = {p.relative_to(destination).as_posix(): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_successful_rerun_prunes_orphan_snapshots(self):
        histories, labels = self.reduced(0)
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'artifacts'
            (destination / 'snapshots').mkdir(parents=True)
            (destination / 'snapshots/orphan.json').write_text('{}', encoding='utf-8')
            result = runner.run(destination, histories=histories, labels=labels)
            expected = {row['manifest']['filename'] for row in result['rows']}
            self.assertEqual({p.name for p in (destination / 'snapshots').iterdir()}, expected)

    def test_unrelated_output_files_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary)
            (destination / 'important.txt').write_text('keep', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'non-artifact'):
                runner.run(destination)
            self.assertEqual((destination / 'important.txt').read_text(encoding='utf-8'), 'keep')


if __name__ == '__main__':
    unittest.main()
