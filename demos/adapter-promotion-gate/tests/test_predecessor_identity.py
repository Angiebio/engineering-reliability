"""A fresh record with equal bytes cannot revive a revoked predecessor ID."""
from pathlib import Path
import tempfile
import unittest

from promotion_gate.core import GateError, Registry
from promotion_gate.demo import NOW, write_bundle


class PredecessorIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = Registry(self.root / 'registry.json', capacity=64, clock=lambda: NOW)
        self.registry.initialize(b'base')

    def admit(self, key, baseline, candidate):
        folder = self.root / key
        digest = write_bundle(folder, baseline=baseline, candidate=candidate)
        self.registry.admit(key, folder, digest)

    def act(self, key, action):
        self.registry.transition(key, action, 'release-manager')

    def prepare_old_pending(self, *, approved):
        self.admit('a', b'base', b'adapter-a')
        self.act('a', 'approve')
        self.act('a', 'serve')
        self.admit('pending', b'adapter-a', b'adapter-pending')
        if approved:
            self.act('pending', 'approve')
        self.act('a', 'rollback')
        self.admit('replacement', b'base', b'adapter-a')
        self.act('replacement', 'approve')
        self.act('replacement', 'serve')
        state = self.registry.read()
        self.assertEqual(state['records']['a']['state'], 'rolled_back')
        self.assertEqual(state['serving'], 'replacement')
        self.assertEqual(state['records']['pending']['predecessor'], 'a')
        # The byte guard has no reason to reject this fixture; only predecessor
        # identity distinguishes the current release from the revoked one.
        self.assertEqual(state['records']['replacement']['sha256'],
                         state['records']['pending']['baseline_sha256'])

    def deny_identity(self, action):
        before = self.registry.path.read_bytes()
        with self.assertRaises(GateError) as caught:
            self.act('pending', action)
        self.assertEqual(caught.exception.code, 'stale_baseline')
        self.assertEqual(str(caught.exception), 'stale_baseline: Serving predecessor identity changed since evaluation')
        self.assertEqual(self.registry.path.read_bytes(), before)

    def test_approve_rejects_same_bytes_replacement(self):
        self.prepare_old_pending(approved=False)
        self.deny_identity('approve')
        self.assertEqual(self.registry.read()['records']['pending']['state'], 'shadow')

    def test_serve_rejects_same_bytes_replacement(self):
        self.prepare_old_pending(approved=True)
        self.deny_identity('serve')
        self.assertEqual(self.registry.read()['records']['pending']['state'], 'approved')

    def test_revoked_predecessor_stays_revoked_while_fresh_nested_rollback_works(self):
        self.prepare_old_pending(approved=True)
        self.deny_identity('serve')
        for key in ('pending', 'a'):
            before = self.registry.path.read_bytes()
            with self.subTest(key=key), self.assertRaises(GateError) as caught:
                self.act(key, 'rollback')
            self.assertEqual(caught.exception.code, 'invalid_transition')
            self.assertEqual(self.registry.path.read_bytes(), before)
        # Re-admission under a fresh identity binds the actual predecessor. The
        # denial above must not disable legitimate nested restoration.
        self.admit('fresh', b'adapter-a', b'fresh-adapter')
        self.act('fresh', 'approve')
        self.act('fresh', 'serve')
        self.act('fresh', 'rollback')
        self.assertEqual(self.registry.read()['serving'], 'replacement')
        self.act('replacement', 'rollback')
        state = self.registry.read()
        self.assertEqual(state['serving'], 'baseline')
        self.assertEqual(state['records']['a']['state'], 'rolled_back')
        self.assertEqual(sum(row['action'] == 'rollback' and row['candidate'] == 'a'
                             for row in state['audit']), 1)


if __name__ == '__main__':
    unittest.main()
