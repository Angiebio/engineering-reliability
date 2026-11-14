"""Presentation checks protect evidence binding and inert data transport."""
import json
import unittest

from continuity.core import check_proposal, propose, render_memory, validate_ledger
from continuity.fixtures import fixture_bank
from continuity.visuals import explorer, outcome_figure, safe_json, visual_payload


class VisualTests(unittest.TestCase):
    def report(self):
        histories, _ = fixture_bank()
        history = histories[2]
        events = validate_ledger(history['events'])
        rows = []
        for strategy in ('raw_tail', 'timeline', 'full_history'):
            memory = render_memory(events, history['task_id'], strategy, 640)
            proposal = propose(memory['context'])
            rows.append({'case_id': history['case_id'], 'strategy': strategy, 'memory': memory,
                         'proposal': proposal, 'gate': check_proposal(events, history['task_id'], proposal), 'expected': 'active'})
        return {'rows': rows, 'metrics': {}}

    def test_visual_source_and_retention_are_recorded_data(self):
        report = self.report()
        payload = visual_payload(report)
        full = report['rows'][2]['memory']['context']['events']
        for source, visual in zip(report['rows'], payload['records']):
            self.assertEqual(full, visual['source_events'])
            self.assertEqual([e['event_id'] for e in source['memory']['context']['events']], visual['retained_ids'])
            self.assertEqual(source['proposal'], visual['proposal'])
            self.assertEqual(source['gate'], visual['gate'])
            self.assertEqual('active', visual['expected'])
        self.assertIsNone(payload['records'][2]['budget_bytes'])

    def test_visual_does_not_invent_missing_history(self):
        report = self.report()
        report['rows'] = report['rows'][:2]
        self.assertEqual([], visual_payload(report)['records'])

    def test_json_source_cannot_close_script(self):
        value = {'text': '</script><svg onload="alert(1)">&'}
        encoded = safe_json(value)
        self.assertNotIn('<', encoded)
        self.assertEqual(value, json.loads(encoded))

    def test_chart_uses_actual_denominator(self):
        graph = outcome_figure({'metrics': {'raw_tail': {'eligible_cases': 5, 'final_resume': 3, 'eligible_not_resumed': 2}}})
        self.assertIn('3/5 eligible tasks resumed', graph)
        self.assertEqual(5, graph.count('<rect '))
        self.assertNotIn('/12', graph)

    def test_planted_control_is_separate_from_main_replay(self):
        page = explorer(self.report())
        self.assertIn('separate planted stale-request control', page)
        self.assertIn('3 history/strategy outcomes contain 0 unsafe proposals', page)

    def test_visual_marks_a_lost_eligible_task(self):
        data = visual_payload(self.report())['records']
        self.assertEqual(data[0]['verdict'], 'missed_eligible')
        self.assertEqual(data[1]['verdict'], 'correct_resume')

    def test_count_marks_have_visible_outlines_and_fixture_caption(self):
        graph = outcome_figure({'metrics': {'raw_tail': {'eligible_cases': 5, 'final_resume': 3, 'eligible_not_resumed': 2}}})
        self.assertIn('stroke="#526273"', graph)
        self.assertIn('authored note lengths', graph)


if __name__ == '__main__':
    unittest.main()
