"""Reviewer-chosen boundary, lifecycle and projection regressions."""
import copy
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import promotion_gate.core as core
from promotion_gate.core import GateError, Registry, canonical
from promotion_gate.demo import BASELINE, CANDIDATE, NOW, render_html, run_gallery, write_bundle
from promotion_gate.visuals import ladder_cards, ladder_svg


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = Registry(self.root / 'registry.json', capacity=64, clock=lambda: NOW)
        self.registry.initialize(BASELINE)

    def admit(self, key='candidate', *, baseline=BASELINE, candidate=CANDIDATE):
        folder = self.root / key
        anchor = write_bundle(folder, baseline=baseline, candidate=candidate)
        self.registry.admit(key, folder, anchor)

    def act(self, key, action):
        self.registry.transition(key, action, 'release-manager')

    def deny(self, code, call, detail=None):
        before = self.registry.path.read_bytes()
        with self.assertRaises(GateError) as error:
            call()
        self.assertEqual(error.exception.code, code)
        if detail:
            self.assertIn(detail, str(error.exception))
        self.assertEqual(self.registry.path.read_bytes(), before)

    def serve_pair(self):
        self.admit('first')
        self.act('first', 'approve')
        self.act('first', 'serve')
        # B uses the original baseline bytes. This is the reviewer's cycle:
        # serving B would satisfy A's baseline digest if stale approval survived.
        self.admit('second', baseline=CANDIDATE, candidate=BASELINE)
        self.act('second', 'approve')
        self.act('second', 'serve')

    def test_displacement_cannot_recycle_approval(self):
        self.serve_pair()
        self.assertEqual(self.registry.read()['records']['first']['state'], 'superseded')
        self.deny('invalid_transition', lambda: self.act('first', 'serve'))
        self.deny('invalid_transition', lambda: self.act('first', 'approve'))
        self.assertEqual(self.registry.read()['revision'], 6)

    def test_nested_rollback_restores_exact_predecessor(self):
        self.serve_pair()
        self.act('second', 'rollback')
        state = self.registry.read()
        self.assertEqual(state['serving'], 'first')
        self.assertEqual(state['records']['first']['sha256'], core.sha256(CANDIDATE))
        self.assertEqual(state['records']['second']['state'], 'rolled_back')
        self.act('first', 'rollback')
        self.assertEqual(self.registry.read()['serving'], 'baseline')
        self.assertEqual(self.registry.read()['revision'], 8)

    def test_exact_freshness_boundaries(self):
        # Both ends and every public entrypoint use actual timestamps. A slightly
        # wider window or changing <= to < must alter at least one expected result.
        for action in ('admit', 'approve', 'serve'):
            for offset in (timedelta(microseconds=-1), timedelta(), timedelta(days=7),
                           timedelta(days=7, microseconds=1)):
                with self.subTest(action=action, offset=offset):
                    folder = self.root / f'{action}-{offset.total_seconds()}'
                    registry = Registry(folder / 'state.json', clock=lambda: NOW)
                    registry.initialize(BASELINE)
                    anchor = write_bundle(folder / 'bundle')
                    if action != 'admit':
                        registry.admit('candidate', folder / 'bundle', anchor)
                    if action == 'serve':
                        registry.transition('candidate', 'approve', 'release-manager')
                    registry.clock = lambda: NOW + offset
                    call = (lambda: registry.admit('candidate', folder / 'bundle', anchor)) if action == 'admit' else (
                        lambda: registry.transition('candidate', action, 'release-manager'))
                    before = registry.path.read_bytes()
                    if timedelta() <= offset <= timedelta(days=7):
                        call()
                    else:
                        with self.assertRaises(GateError) as error:
                            call()
                        self.assertEqual(error.exception.code, 'stale_evidence')
                        self.assertEqual(registry.path.read_bytes(), before)

    def test_headroom_covers_all_pending_approvals(self):
        # Measure real future writes at the maximum record/ID count. The cap is
        # smaller than completing only these approvals, before any serve/rollback.
        # Reserving for one record or 2048 bytes/record admits an unsafe boundary.
        keys = [f'c{index:047d}' for index in range(63)]
        for index, key in enumerate(keys[:-1]):
            self.admit(key, candidate=f'artifact-{index}'.encode())
        before = self.registry.path.read_bytes()
        self.admit(keys[-1], candidate=b'last-artifact')
        for key in keys:
            self.act(key, 'approve')
        measured_required = self.registry.path.stat().st_size
        self.registry.path.write_bytes(before)
        with patch.object(core, 'MAX_REGISTRY_BYTES', measured_required - 1):
            self.deny('oversize', lambda: self.admit(keys[-1], candidate=b'last-artifact'),
                      'reserve lifecycle audit headroom')

    def test_per_event_snapshot_has_its_own_guard(self):
        self.admit()
        self.act('candidate', 'approve')
        state = self.registry.read()
        state['audit'][0]['state_snapshot']['record_states']['candidate'] = 'approved'
        self.registry.path.write_bytes(canonical(state))
        self.deny('registry_schema', self.registry.read, 'Audit snapshot disagrees with history')

    def test_actor_binding_has_its_own_guard(self):
        self.admit()
        state = self.registry.read()
        state['audit'][0]['actor'] = 'release-manager'
        self.registry.path.write_bytes(canonical(state))
        self.deny('registry_schema', self.registry.read, 'Audit actor label disagrees with action')

    def test_approval_replay_requires_shadow_predecessor(self):
        self.admit()
        self.act('candidate', 'approve')
        state = self.registry.read()
        duplicate = copy.deepcopy(state['audit'][-1])
        state['revision'] += 1
        duplicate['revision'] = state['revision']
        state['audit'].append(duplicate)
        self.registry.path.write_bytes(canonical(state))
        self.deny('registry_schema', self.registry.read, 'Approval has no shadow predecessor')

    def test_trusted_disk_metadata_is_not_authenticated(self):
        self.admit()
        self.act('candidate', 'approve')
        self.registry.clock = lambda: NOW + timedelta(days=8)
        self.deny('stale_evidence', lambda: self.act('candidate', 'serve'))
        state = self.registry.read()
        state['records']['candidate']['evaluated_at'] = self.registry.clock().isoformat()
        state['records']['candidate']['manifest_sha256'] = '0' * 64
        state['audit'][0]['at'] = (NOW - timedelta(days=20)).isoformat()
        self.registry.path.write_bytes(canonical(state))
        self.act('candidate', 'serve')
        self.assertEqual(self.registry.read()['serving'], 'candidate')

    def test_gallery_consumes_reviewed_anchor_file(self):
        original = Path.read_text
        reads = []
        def changed(path, *args, **kwargs):
            if path.name == 'reviewed-anchor.txt':
                reads.append(path.name)
                return '0' * 64
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', changed):
            with self.assertRaisesRegex(AssertionError, 'expected shadow, observed manifest_mismatch'):
                run_gallery()
        self.assertEqual(reads, ['reviewed-anchor.txt'])


class FigureRecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_gallery()

    def test_ladder_rejects_unknown_stages_before_publication(self):
        result = copy.deepcopy(self.result)
        result['cases'][1]['operations'][0]['checks'][-1]['stage'] = 'new_unlisted_guard'
        for renderer in (ladder_svg, ladder_cards, render_html):
            with self.subTest(renderer=renderer.__name__), self.assertRaisesRegex(ValueError, 'Unknown recorded ladder stage'):
                renderer(result)

    def test_ladder_preserves_full_authority_label(self):
        tree = ET.fromstring(ladder_svg(self.result))
        words = ' '.join(element.text or '' for element in tree.iter('{http://www.w3.org/2000/svg}text'))
        name = next(case['name'] for case in self.result['cases'] if case['observed'] == 'unauthorized')
        self.assertIn(name, words)
        self.assertIn('no authentication', words)

    def test_ladder_cards_preserve_all_rows(self):
        class Rows(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows = []
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == 'details' and values.get('class') == 'gate-row':
                    self.rows.append((int(values['data-case']), values['data-operation']))
        rendered = ladder_cards(self.result)
        parser = Rows()
        parser.feed(rendered)
        self.assertEqual(parser.rows, [(index + 1, operation['operation'])
                                      for index, case in enumerate(self.result['cases']) for operation in case['operations']])
        for case in self.result['cases']:
            if case['rejection_preserved_registry']:
                self.assertIn('Stopped: ' + case['observed'], rendered)

    def test_outcome_cell_comes_from_recorded_result(self):
        result = copy.deepcopy(self.result)
        result['cases'][0]['passed'] = False
        rendered = render_html(result)
        self.assertEqual(rendered.count('Matches expected: no'), 1)
        self.assertEqual(rendered.count('Matches expected: yes'), len(result['cases']) - 1)


if __name__ == '__main__':
    unittest.main()
