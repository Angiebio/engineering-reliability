"""Properties exposed by the outside review, including adjacent guard boundaries."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from continuity import __main__ as runner
from continuity.core import Event, canonical, check_proposal, propose, render_memory, validate_ledger
from continuity.diagnostics import budget_sweep, natural_histories, sweep_svg, transition_brackets
from continuity.fixtures import fixture_bank
from continuity.visuals import budget_explorer, explorer, verdict


class RecheckProperties(unittest.TestCase):
    def setUp(self):
        self.histories, self.labels = fixture_bank()

    def test_gate_off_preserves_nonresume_proposals(self):
        history = next(h for h in natural_histories(self.histories, self.labels) if h['case_id'] == 'natural-case13')
        with tempfile.TemporaryDirectory() as directory:
            for budget, expected in ((640, 'hold'), (64, 'abstain')):
                with self.subTest(budget=budget), patch.object(runner, 'BUDGET', budget):
                    row = runner.replay_case(Path(directory), history, 'completed', 'raw_tail', gate_enabled=False)
                    self.assertEqual(row['proposal']['action'], expected)
                    self.assertEqual(row['gate']['action'], expected)
                    self.assertEqual(row['gate']['reason'], 'gate_bypassed')

    def test_exact_binding_covers_nontext_fields(self):
        source = Event('request', 'task', 1, 'request', 'controller', 'Same source text')
        events = validate_ledger([source.record()])
        for change in ({'sequence': 2}, {'kind': 'approve'}, {'supersedes': 'other'}, {'event_id': 'missing'}):
            with self.subTest(change=change):
                proposal = {'task_id': 'task', 'action': 'resume', 'evidence': {**source.record(), **change}}
                self.assertEqual(check_proposal(events, 'task', proposal)['reason'], 'unbound_evidence')

    def test_main_matrix_path_also_gates_long_terminal_history(self):
        history = next(h for h in natural_histories(self.histories, self.labels) if h['case_id'] == 'natural-case14')
        history['case_id'] = 'case14'
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run(Path(directory), histories=[history], labels={'case14': self.labels['case14']})
        raw = next(row for row in result['rows'] if row['strategy'] == 'raw_tail')
        self.assertEqual(raw['proposal']['action'], 'resume')
        self.assertEqual((raw['gate']['action'], raw['gate']['reason']), ('hold', 'stale_evidence'))

    def test_negative_control_rejects_wrong_guard_reason(self):
        original = runner.check_proposal
        def wrong_reason(events, task, proposal):
            result = original(events, task, proposal)
            if result['reason'] == 'unbound_evidence':
                result['reason'] = 'stale_evidence'
            return result
        with patch.object(runner, 'check_proposal', side_effect=wrong_reason), self.assertRaisesRegex(RuntimeError, 'negative control failed: Changed source text'):
            runner.negative_controls(self.histories)

    def test_active_task_still_requires_latest_authority(self):
        records = [Event('request', 'task', 1, 'request', 'controller', 'Start').record(),
                   Event('block', 'task', 2, 'block', 'controller', 'Blocked', 'request').record(),
                   Event('approve', 'task', 3, 'approve', 'controller', 'Fresh approval', 'block').record()]
        events = validate_ledger(records)
        old = {'task_id': 'task', 'action': 'resume', 'evidence': records[0]}
        current = {**old, 'evidence': records[2]}
        self.assertEqual((check_proposal(events, 'task', old)['action'], check_proposal(events, 'task', old)['reason']), ('hold', 'stale_evidence'))
        self.assertEqual(check_proposal(events, 'task', current)['action'], 'resume')

    def test_budget_floor_and_exact_envelope_boundary(self):
        for budget in (63, True):
            with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, 'integer >=64'):
                render_memory((), 't', 'raw_tail', budget)
        self.assertEqual(render_memory((), 't', 'raw_tail', 64)['context']['events'], [])
        task = 't' * 80
        exact = len(canonical({'task_id': task, 'events': []}))
        with self.assertRaisesRegex(ValueError, 'empty context envelope'):
            render_memory((), task, 'raw_tail', exact - 1)
        for budget in (exact, exact + 1):
            self.assertEqual(render_memory((), task, 'raw_tail', budget)['used_bytes'], exact)

    def test_event_text_cap_counts_utf8_at_both_sides(self):
        for text in ('x' * 8192, 'é' * 4096):
            self.assertEqual(Event.parse(Event('request', 'task', 1, 'request', 'controller', text).record()).text, text)
            with self.assertRaisesRegex(ValueError, 'exceeds 8192 UTF-8 bytes'):
                Event.parse(Event('request', 'task', 1, 'request', 'controller', text + 'x').record())

    def test_ledger_event_cap_both_sides(self):
        records = [Event('request', 'task', 1, 'request', 'controller', 'Start').record()]
        records += [Event(f'n{i}', 'task', i, 'note', 'external', 'Note').record() for i in range(2, 10001)]
        self.assertEqual(len(validate_ledger(records)), 10000)
        with self.assertRaisesRegex(ValueError, '1..10000 events'):
            validate_ledger(records + [Event('last', 'task', 10001, 'note', 'external', 'Note').record()])

    def test_renderer_filters_tasks_and_controller_notes(self):
        records = [Event('a', 'task', 1, 'request', 'controller', 'Start').record(),
                   Event('b', 'other', 2, 'request', 'controller', 'Other').record(),
                   Event('n', 'task', 3, 'note', 'controller', 'A controller note is still a note').record()]
        events = validate_ledger(records)
        self.assertEqual([e['event_id'] for e in render_memory(events, 'task', 'timeline', 1000)['context']['events']], ['a'])
        self.assertEqual([e['event_id'] for e in render_memory(events, 'task', 'raw_tail', 1000)['context']['events']], ['a', 'n'])

    def test_natural_suffix_changes_only_length_and_exposes_fixture_choice(self):
        originals = {h['case_id']: h for h in self.histories}
        for history in natural_histories(self.histories, self.labels):
            original = originals[history['case_id'].removeprefix('natural-')]
            for before, after in zip(original['events'], history['events']):
                self.assertEqual({k: v for k, v in before.items() if k != 'text'}, {k: v for k, v in after.items() if k != 'text'})
                if before['kind'] in ('complete', 'pause', 'block', 'revoke'):
                    self.assertTrue(after['text'].startswith(before['text']))
                    self.assertEqual(len(after['text']) - len(before['text']), 200)
                else:
                    self.assertEqual(before['text'], after['text'])

    def test_all_verdicts_follow_expected_proposal_and_gate(self):
        cases = [(None, 'resume', 'resume', 'expectation_unavailable'),
                 ('active', 'resume', 'resume', 'correct_resume'),
                 ('completed', 'resume', 'resume', 'unsafe_allowed'),
                 ('active', 'abstain', 'hold', 'missed_eligible'),
                 ('completed', 'resume', 'hold', 'unsafe_caught'),
                 ('completed', 'hold', 'hold', 'correct_hold')]
        for expected, proposal, gate, observed in cases:
            with self.subTest(expected=expected, proposal=proposal, gate=gate):
                self.assertEqual(verdict({'expected': expected, 'proposal': {'action': proposal}, 'gate': {'action': gate}}), observed)

    def test_explorer_counts_change_with_observed_rows(self):
        from test_visuals import VisualTests
        base = VisualTests().report()
        for caught, bypassed in ((0, 0), (1, 2), (4, 1)):
            report = copy.deepcopy(base)
            report['natural_rows'] = [{'proposal': {'action': 'resume'}, 'gate': {'action': 'hold'}} for _ in range(caught)]
            report['gate_off_rows'] = [{'gate': {'action': 'resume'}} for _ in range(bypassed)]
            page = explorer(report)
            self.assertIn(f'{caught} caught stale resumptions', page)
            self.assertIn(f'{bypassed} unsafe resumptions', page)

    def test_sweep_svg_marks_and_caption_follow_supplied_points(self):
        sweep = budget_sweep(self.histories, self.labels, [541, 542, 746], reference_budget=542)
        sweep['points'][1]['strategies']['raw_tail']['eligible_resumed'] = 4
        root = ET.fromstring(sweep_svg(sweep))
        marks = [node for node in root.iter() if node.get('data-strategy')]
        expected = {(str(p['budget_bytes']), name): str(p['strategies'][name]['eligible_resumed']) for p in sweep['points'] for name in ('raw_tail', 'timeline')}
        self.assertEqual({(n.get('data-budget'), n.get('data-strategy')): n.get('data-count') for n in marks}, expected)
        self.assertEqual(len(marks), len(expected))
        for mark in marks:
            budget, count = int(mark.get('data-budget')), int(mark.get('data-count'))
            # Inspect the marks a reader sees, not only attached data labels.
            # The fixed plotting frame spans x=80..980 and y=290..120.
            self.assertAlmostEqual(float(mark.get('cx')), 80 + (budget - 541) / (746 - 541) * 900, places=2)
            self.assertAlmostEqual(float(mark.get('cy')), 290 - count / 12 * 170, places=2)
            if mark.get('data-strategy') == 'timeline':
                self.assertEqual(mark.get('fill'), 'none')
            else:
                self.assertNotEqual(mark.get('fill'), 'none')
        text = ''.join(root.itertext())
        self.assertIn('At 542 bytes, raw tail resumes 4/12', text)
        self.assertNotIn('9/12 result at 640', text)
        self.assertFalse(any(node.tag.endswith('polyline') for node in root.iter()))

    def test_sweep_tallies_actual_gate_outputs_separately_from_proposals(self):
        # Deliberately wrong gates make both counters nontrivial. A tally cannot
        # quietly substitute proposals or assume the very invariant it reports.
        active = self.histories[0]
        with patch('continuity.diagnostics.check_proposal', return_value={'action': 'hold', 'reason': 'injected_hold'}):
            point = budget_sweep([active], {active['case_id']: 'active'}, [1000])['points'][0]
        self.assertEqual(point['strategies']['timeline']['cases'][0]['proposal'], 'resume')
        self.assertEqual(point['strategies']['timeline']['eligible_resumed'], 0)
        closed = self.histories[12]
        with patch('continuity.diagnostics.check_proposal', return_value={'action': 'resume', 'reason': 'injected_bypass'}):
            point = budget_sweep([closed], {closed['case_id']: 'completed'}, [1000])['points'][0]
        self.assertEqual(point['strategies']['timeline']['unsafe_final'], 1)

    def test_cliff_samples_and_mobile_brackets_are_measured(self):
        sweep = budget_sweep(self.histories, self.labels, [284, 285, 286, 287, 288, 734, 735, 740, 741, 745, 746])
        values = {p['budget_bytes']: p['strategies']['raw_tail']['eligible_resumed'] for p in sweep['points']}
        self.assertEqual((values[284], values[285], values[287], values[288]), (9, 6, 6, 3))
        self.assertEqual([values[b] for b in (734, 735, 740, 741, 745, 746)], [9, 10, 10, 11, 11, 12])
        page = budget_explorer({'sweep': sweep})
        for point in transition_brackets(sweep):
            self.assertIn(f'data-left="{point["left_bytes"]}" data-right="{point["right_bytes"]}"', page)
            self.assertIn(f'{point["before"]} → {point["after"]} eligible resumptions', page)
        self.assertIn('timeline can also propose stale resumptions', page)


if __name__ == '__main__':
    unittest.main()
