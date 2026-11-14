"""Ensure the mutation verifier cannot claim success from a vacuous test/error."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name('verify_comment_mutations.py')
spec = importlib.util.spec_from_file_location('comment_verifier', MODULE)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class RunnerTests(unittest.TestCase):
    def run_case(self, replacement, *, test_body='self.assertTrue(guard.allow())', evidence='test_accepts'):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / 'demos/toy'
            (package / 'tests').mkdir(parents=True)
            source = '# Mutation: TOY-GUARD\n# Evidence: ' + evidence + '\ndef allow():\n    return True\n'
            (package / 'guard.py').write_text(source, encoding='utf-8')
            (package / 'tests/test_guard.py').write_text('import unittest\nimport guard\nclass Guards(unittest.TestCase):\n    def test_accepts(self):\n        ' + test_body + '\n', encoding='utf-8')
            manifest = [{'id': 'TOY-GUARD', 'source': 'guard.py', 'old': 'return True', 'new': replacement,
                         'tests': ['test_guard.Guards.test_accepts'], 'claim': 'Named test notices guard change', 'finding': 'runner'}]
            (package / 'tests/comment_mutations.json').write_text(json.dumps(manifest), encoding='utf-8')
            with patch.object(verifier, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                try:
                    return verifier.verify('toy')
                finally:
                    self.assertEqual((package / 'guard.py').read_text(encoding='utf-8'), source)

    def test_real_assertion_failure_is_attributed_and_original_is_preserved(self):
        record = self.run_case('return False')
        self.assertTrue(record['contracts'][0]['caught_by_cited_tests'])
        self.assertEqual(record['contracts'][0]['mutant']['failed_tests'], ['test_guard.Guards.test_accepts'])

    def test_test_that_does_not_exercise_guard_cannot_count_as_detection(self):
        with self.assertRaisesRegex(RuntimeError, 'survived'):
            self.run_case('return False', test_body='self.assertTrue(True)')

    def test_import_failure_is_not_a_guard_detection(self):
        with self.assertRaisesRegex(RuntimeError, 'survived'):
            self.run_case("return __import__('missing_comment_runner_probe_93817')")

    def test_pristine_failure_cannot_be_attributed_to_mutation(self):
        with self.assertRaisesRegex(RuntimeError, 'pristine'):
            self.run_case('return False', test_body='self.assertFalse(guard.allow())')

    def test_comment_must_cite_the_executed_test(self):
        with self.assertRaisesRegex(ValueError, 'does not cite'):
            self.run_case('return False', evidence='test_something_else')


if __name__ == '__main__':
    unittest.main()
