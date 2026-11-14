"""Lifecycle graphics must reconstruct the recorded audit, not imply new checks."""
import copy
import unittest

from promotion_gate.demo import run_gallery
from promotion_gate.visuals import explorer, ladder_svg, replay_frames, visual_payload


class VisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_gallery()

    def test_graph_tracks_rollback_and_serving_separately(self):
        case = next(c for c in self.result['cases'] if c['observed'] == 'rollback_restored')
        frames = replay_frames(case)
        self.assertEqual(['not admitted', 'shadow', 'approved', 'serving', 'rolled_back'],
                         [frame['candidate_state'] for frame in frames])
        self.assertEqual(['baseline', 'baseline', 'baseline', 'candidate', 'baseline'],
                         [frame['serving'] for frame in frames])

    def test_denial_adds_no_successful_audit_transition(self):
        case = next(c for c in self.result['cases'] if c['observed'] == 'canary_failed')
        frames = replay_frames(case)
        self.assertEqual(2, len(frames))
        self.assertEqual([0, 0], [frame['revision'] for frame in frames])
        self.assertEqual(['not admitted', 'not admitted'], [frame['candidate_state'] for frame in frames])
        self.assertEqual([], case['audit'])

    def test_unknown_or_inconsistent_audit_fails(self):
        case = copy.deepcopy(self.result['cases'][0])
        case['audit'][0]['action'] = 'magically_serve'
        with self.assertRaises(ValueError):
            replay_frames(case)
        case = copy.deepcopy(self.result['cases'][0])
        case['serving'] = 'invented'
        with self.assertRaises(ValueError):
            replay_frames(case)

    def test_visual_json_is_inert_and_names_scope(self):
        result = copy.deepcopy(self.result)
        result['cases'][0]['name'] = '</script><img src=x onerror=alert(1)>'
        page = explorer(result)
        self.assertNotIn('</script><img', page)
        self.assertIn('\\u003c/script\\u003e', page)
        self.assertIn('not plotted as passes', page)
        self.assertIn('Canary outcomes are authored true/false statements in a synthetic report; no canary test was executed.', page)
        self.assertEqual(len(result['cases']), len(visual_payload(result)['cases']))

    def test_ladder_uses_only_recorded_checks(self):
        import xml.etree.ElementTree as ET
        tree = ET.fromstring(ladder_svg(self.result))
        words = ' '.join(node.text or '' for node in tree.iter('{http://www.w3.org/2000/svg}text'))
        self.assertIn('hatched = not evaluated', words)
        self.assertIn('Canaries are authored boolean claims.', words)
        for case in self.result['cases']:
            for operation in case['operations']:
                positions = [self.result['check_stages'].index(c['stage']) for c in operation['checks']]
                self.assertEqual(positions, sorted(positions))
                self.assertTrue(all(c['status'] == 'passed' for c in operation['checks'][:-1]))
                if operation['denial']:
                    self.assertEqual(operation['checks'][-1]['status'], 'stopped')
                    self.assertEqual(operation['checks'][-1]['reason'], operation['denial'])
        changed = copy.deepcopy(self.result)
        changed['cases'][1]['operations'][0]['denial'] = 'distinct_recorded_reason'
        self.assertIn('distinct_recorded_reason', ladder_svg(changed))


if __name__ == '__main__':
    unittest.main()
