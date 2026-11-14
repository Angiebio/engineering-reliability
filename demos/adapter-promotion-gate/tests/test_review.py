"""Independent named regressions for the cross-model review findings."""
import copy
import json
from datetime import timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from promotion_gate.core import GateError, MAX_FILE_BYTES, Registry, canonical, parse_json, sha256
from promotion_gate.demo import BASELINE, NOW, observed_success, report_fixture, run_gallery, write_bundle
from promotion_gate.visuals import replay_frames


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.registry = Registry(self.root / 'registry.json', clock=lambda: NOW)
        self.registry.initialize(BASELINE)

    def deny(self, code, call):
        before = self.registry.path.read_bytes()
        with self.assertRaises(GateError) as raised:
            call()
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(self.registry.path.read_bytes(), before)

    def admit(self, **options):
        anchor = write_bundle(self.bundle, **options)
        return self.registry.admit('candidate', self.bundle, anchor)

    def repin_fixture(self, name, content):
        (self.bundle / name).write_bytes(content)
        manifest = parse_json((self.bundle / 'manifest.json').read_bytes())
        for entry in manifest['artifacts'].values():
            if entry['file'] == name:
                entry['sha256'] = sha256(content)
        encoded = canonical(manifest)
        (self.bundle / 'manifest.json').write_bytes(encoded)
        return sha256(encoded)

    def lifecycle(self):
        self.admit()
        for action in ('approve', 'serve', 'rollback'):
            self.registry.transition('candidate', action, 'release-manager')

    def test_rollback_revokes_approval(self):
        self.lifecycle()
        self.assertEqual(self.registry.read()['records']['candidate']['state'], 'rolled_back')
        self.deny('invalid_transition', lambda: self.registry.transition('candidate', 'serve', 'release-manager'))
        self.deny('invalid_transition', lambda: self.registry.transition('candidate', 'approve', 'release-manager'))

    def test_non_utc_clock_writes_utc(self):
        self.registry.clock = lambda: NOW.astimezone(timezone(timedelta(hours=1)))
        self.admit()
        self.assertEqual(self.registry.read()['audit'][0]['at'], NOW.isoformat())

    def test_naive_clock_cannot_break_rollback_storage(self):
        self.admit()
        self.registry.transition('candidate', 'approve', 'release-manager')
        self.registry.transition('candidate', 'serve', 'release-manager')
        self.registry.clock = lambda: NOW.replace(tzinfo=None)
        self.deny('invalid_clock', lambda: self.registry.transition('candidate', 'rollback', 'release-manager'))
        self.assertEqual(self.registry.read()['serving'], 'candidate')

    def test_invalid_private_state_never_replaces_registry(self):
        state = self.registry.read()
        state['revision'] = 99
        self.deny('registry_schema', lambda: self.registry._write(state))
        self.assertEqual(list(self.root.glob('.registry-*.tmp')), [])

    def test_largest_artifact_completes_rollback(self):
        self.admit(candidate=b'a' * MAX_FILE_BYTES)
        for action in ('approve', 'serve', 'rollback'):
            self.registry.transition('candidate', action, 'release-manager')
        self.assertEqual(self.registry.read()['serving'], 'baseline')
        anchor = write_bundle(self.root / 'oversize', candidate=b'b' * (MAX_FILE_BYTES + 1))
        self.deny('oversize', lambda: self.registry.admit('oversize', self.root / 'oversize', anchor))

    def test_near_full_registry_reserves_complete_lifecycle(self):
        # Search a fixture's actual admission boundary, then exercise every
        # remaining public transition; simply checking a size constant misses
        # the original failure where rollback was the first write over the cap.
        for index in range(5):
            anchor = write_bundle(self.bundle, candidate=bytes([65 + index]) * MAX_FILE_BYTES)
            self.registry.admit(f'prior{index}', self.bundle, anchor)
        starting = self.registry.path.read_bytes()
        low, high = 1, MAX_FILE_BYTES
        while low < high:
            size = (low + high + 1) // 2
            self.registry.path.write_bytes(starting)
            anchor = write_bundle(self.bundle, candidate=b'z' * size)
            try:
                self.registry.admit('candidate', self.bundle, anchor)
            except GateError as exc:
                self.assertEqual(exc.code, 'oversize')
                high = size - 1
            else:
                low = size
        self.assertLess(low, MAX_FILE_BYTES)
        self.registry.path.write_bytes(starting)
        anchor = write_bundle(self.bundle, candidate=b'z' * low)
        self.registry.admit('candidate', self.bundle, anchor)
        for action in ('approve', 'serve', 'rollback'):
            self.registry.transition('candidate', action, 'release-manager')
        self.assertEqual(self.registry.read()['serving'], 'baseline')

    def test_capacity_bound_is_explicit(self):
        Registry(self.root / 'capacity64.json', capacity=64)
        for value in (0, 65, True):
            with self.subTest(capacity=value), self.assertRaises(GateError) as raised:
                Registry(self.root / 'invalid.json', capacity=value)
            self.assertEqual(raised.exception.code, 'capacity')

    def test_evidence_expires_after_approval(self):
        self.admit()
        self.registry.transition('candidate', 'approve', 'release-manager')
        self.registry.clock = lambda: NOW + timedelta(days=8)
        self.deny('stale_evidence', lambda: self.registry.transition('candidate', 'serve', 'release-manager'))

    def test_invalid_metrics_rejected_on_admit_path(self):
        for field, literal in [('gain', '1e999'), ('gain', '"0.05"'), ('gain', 'true'), ('regression', '-0.01')]:
            with self.subTest(field=field, literal=literal):
                write_bundle(self.bundle)
                fixture = report_fixture()
                fixture[field] = 'REPLACE'
                raw = json.dumps(fixture).replace('"REPLACE"', literal).encode()
                anchor = self.repin_fixture('evaluation.json', raw)
                self.deny('invalid_metric', lambda: self.registry.admit('candidate', self.bundle, anchor))

    def test_unknown_canary_rejected_on_admit(self):
        fixture = report_fixture()
        fixture['canaries'].append({'id': 'unknown', 'passed': True})
        anchor = write_bundle(self.bundle, fixture)
        self.deny('canary_schema', lambda: self.registry.admit('candidate', self.bundle, anchor))

    def test_unchanged_candidate_rejected(self):
        self.deny('unchanged_candidate', lambda: self.admit(candidate=BASELINE))

    def test_audit_must_bind_lifecycle_state(self):
        self.admit()
        state = self.registry.read()
        state['records']['candidate']['state'] = 'approved'
        self.registry.path.write_bytes(canonical(state))
        self.deny('registry_schema', self.registry.read)

    def test_recorded_check_stops_at_failure(self):
        fixture = report_fixture()
        fixture['gain'] = True
        anchor = write_bundle(self.bundle, fixture)
        self.deny('invalid_metric', lambda: self.registry.admit('candidate', self.bundle, anchor))
        checks = self.registry.last_checks
        self.assertEqual(checks[-1], {'stage': 'metrics', 'status': 'stopped', 'reason': 'invalid_metric'})
        self.assertFalse(any(c['stage'] == 'canaries' for c in checks))
        self.assertTrue(all(c['status'] == 'passed' for c in checks[:-1]))

    def test_every_frame_uses_recorded_state(self):
        result = run_gallery()
        for case in result['cases']:
            for operation, frame in zip(case['operations'], replay_frames(case)[1:]):
                self.assertEqual(frame['candidate_state'], operation['after_state']['record_states'].get('candidate', 'not admitted'))
                self.assertEqual(frame['serving'], operation['after_state']['serving'])
                self.assertEqual(frame['serving_sha256'], operation['after_state']['serving_sha256'])

    def test_gallery_detects_disconnected_rollback(self):
        original = Registry.transition
        def disconnected(registry, key, action, actor):
            if action != 'rollback':
                return original(registry, key, action, actor)
        with patch.object(Registry, 'transition', disconnected):
            with self.assertRaisesRegex(AssertionError, 'unexpected_persistent_state'):
                run_gallery()

    def test_observed_outcome_requires_restored_bytes(self):
        self.lifecycle()
        state = self.registry.read()
        self.assertEqual(observed_success(state), 'rollback_restored')
        state['records']['baseline']['sha256'] = '0' * 64
        self.assertEqual(observed_success(state), 'unexpected_persistent_state')

    def test_invalid_render_does_not_leave_success_artifacts(self):
        from promotion_gate.demo import main
        output = self.root / 'render-failed'
        with patch('sys.argv', ['demo', '--output', str(output)]), patch('promotion_gate.demo.render_html', side_effect=ValueError('bad projection')):
            with self.assertRaises(ValueError):
                main()
        self.assertFalse((output / 'results.json').exists())

    def test_additional_admission_reason_codes(self):
        for raw, expected in [(b'{', 'invalid_json'), (b'[]', 'invalid_object'),
                               (b'{"schema_version":true}', 'manifest_schema')]:
            write_bundle(self.bundle)
            (self.bundle / 'manifest.json').write_bytes(raw)
            self.deny(expected, lambda: self.registry.admit('candidate', self.bundle, sha256(raw)))
        for change, expected in [(lambda r: r.update(extra=1), 'report_schema'),
                                  (lambda r: r.update(kind='measured'), 'report_kind')]:
            fixture = report_fixture()
            change(fixture)
            anchor = write_bundle(self.bundle, fixture)
            self.deny(expected, lambda: self.registry.admit('candidate', self.bundle, anchor))
        anchor = write_bundle(self.bundle)
        self.deny('invalid_digest', lambda: self.registry.admit('candidate', self.bundle, 'INVALID'))
        manifest = parse_json((self.bundle / 'manifest.json').read_bytes())
        manifest['artifacts'] = []
        raw = canonical(manifest)
        (self.bundle / 'manifest.json').write_bytes(raw)
        self.deny('artifact_schema', lambda: self.registry.admit('candidate', self.bundle, sha256(raw)))
        self.deny('empty_artifact', lambda: self.admit(candidate=b''))

    def test_additional_registry_reason_codes(self):
        self.deny('already_initialized', lambda: self.registry.initialize(BASELINE))
        self.deny('invalid_id', lambda: self.registry.admit('../bad', self.bundle, '0'*64))
        self.deny('unknown_action', lambda: self.registry.transition('unknown', 'launch', 'release-manager'))
        self.deny('unknown_candidate', lambda: self.registry.transition('unknown', 'approve', 'release-manager'))


if __name__ == '__main__':
    unittest.main()
