"""Boundary tests use the same evidence and registry entrypoints as the gallery."""

import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from promotion_gate.core import GateError, Registry, canonical, evaluate, number, parse_json, sha256
from promotion_gate.demo import BASELINE, NOW, report_fixture, render_html, run_gallery, write_bundle


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bundle = self.root / "bundle"
        self.registry = Registry(self.root / "registry.json", clock=lambda: NOW)
        self.registry.initialize(BASELINE)

    def deny(self, code, operation):
        before = self.registry.path.read_bytes()
        with self.assertRaises(GateError) as raised:
            operation()
        self.assertEqual(code, raised.exception.code)
        self.assertEqual(before, self.registry.path.read_bytes())

    def admit(self, fixture=None, **options):
        anchor = write_bundle(self.bundle, fixture, **options)
        return self.registry.admit("candidate", self.bundle, anchor)

    def test_admission_is_only_shadow(self):
        self.assertEqual("shadow", self.admit()["state"])
        self.assertEqual("baseline", self.registry.read()["serving"])

    def test_metrics_reject_nan_inf_bool_and_ranges(self):
        for value in [float("nan"), float("inf"), -float("inf"), True, "0.1", None, -2, 2, 10**500]:
            with self.subTest(value=value):
                with self.assertRaises(GateError):
                    number(value, "gain", -1, 1)

    def test_nonfinite_json_literal(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            fixture = report_fixture()
            fixture["gain"] = value
            self.deny("nonfinite_json", lambda: self.admit(fixture))

    def test_duplicate_json_key(self):
        with self.assertRaises(GateError) as raised:
            parse_json(b'{"gain":0.1,"gain":0.9}')
        self.assertEqual("duplicate_key", raised.exception.code)

    def test_empty_missing_duplicate_canaries(self):
        for expected, mutate in [
            ("canary_schema", lambda r: r.update(canaries=[])),
            ("missing_canary", lambda r: r["canaries"].pop()),
            ("duplicate_canary", lambda r: r["canaries"].append(copy.deepcopy(r["canaries"][0])))]:
            with self.subTest(expected=expected):
                fixture = report_fixture()
                mutate(fixture)
                self.deny(expected, lambda: self.admit(fixture))

    def test_failed_canary_beats_high_gain(self):
        fixture = report_fixture()
        fixture["gain"] = 1.0
        fixture["canaries"][0]["passed"] = False
        self.deny("canary_failed", lambda: self.admit(fixture))

    def test_canary_bool_is_strict(self):
        fixture = report_fixture()
        fixture["canaries"][0]["passed"] = "true"
        self.deny("canary_schema", lambda: self.admit(fixture))

    def test_threshold_equality_passes(self):
        fixture = report_fixture()
        fixture.update(gain=0.02, regression=0.01)
        self.assertEqual("shadow", self.admit(fixture)["state"])

    def test_threshold_failures(self):
        for expected, changes in [("insufficient_gain", {"gain":0.019}), ("excess_regression", {"regression":0.011})]:
            fixture = report_fixture()
            fixture.update(changes)
            self.deny(expected, lambda: self.admit(fixture))

    def test_manifest_and_artifact_tampering(self):
        for name, expected in [("manifest.json", "manifest_mismatch"), ("candidate.bin", "artifact_mismatch"),
                                ("evaluation.json", "artifact_mismatch"), ("baseline.bin", "artifact_mismatch")]:
            anchor = write_bundle(self.bundle)
            (self.bundle / name).write_bytes(b"tampered")
            self.deny(expected, lambda: self.registry.admit("candidate", self.bundle, anchor))

    def test_stale_and_future_evidence(self):
        for delta in [timedelta(days=-8), timedelta(seconds=1)]:
            self.deny("stale_evidence", lambda: self.admit(evaluated_at=NOW + delta))

    def test_stale_baseline(self):
        self.deny("stale_baseline", lambda: self.admit(baseline=b"other baseline"))

    def test_capacity_preserves_bytes(self):
        self.registry.capacity = 1
        self.deny("capacity", lambda: self.admit())
        self.assertEqual(1, len(self.registry.read()["records"]))

    def test_interrupted_replace_preserves_bytes(self):
        def fail():
            raise OSError("injected interruption before atomic replacement")
        self.registry.before_replace = fail
        before = self.registry.path.read_bytes()
        with self.assertRaises(OSError):
            self.admit()
        self.assertEqual(before, self.registry.path.read_bytes())
        self.assertEqual([], list(self.root.glob(".registry-*.tmp")))
        self.assertFalse(self.registry.path.with_suffix(".json.lock").exists())
        self.registry.before_replace = None
        self.assertEqual("shadow", self.admit()["state"])

    def test_lock_refuses_concurrent_writer(self):
        lock = self.registry.path.with_suffix(".json.lock")
        lock.write_bytes(b"other writer")
        self.deny("registry_locked", lambda: self.admit())
        self.assertTrue(lock.exists())

    def test_shadow_cannot_serve(self):
        self.admit()
        self.deny("invalid_transition", lambda: self.registry.transition("candidate", "serve", "release-manager"))

    def test_authorization(self):
        self.admit()
        self.deny("unauthorized", lambda: self.registry.transition("candidate", "approve", "model-agent"))

    def test_stale_evidence_cannot_be_approved(self):
        self.admit()
        self.registry.clock = lambda: NOW + timedelta(days=8)
        self.deny("stale_evidence", lambda: self.registry.transition("candidate", "approve", "release-manager"))

    def test_stale_approved_candidate_cannot_serve(self):
        self.admit()
        self.registry.transition("candidate", "approve", "release-manager")
        anchor = write_bundle(self.root / "other", candidate=b"other candidate")
        self.registry.admit("other", self.root / "other", anchor)
        self.registry.transition("other", "approve", "release-manager")
        self.registry.transition("other", "serve", "release-manager")
        self.deny("stale_baseline", lambda: self.registry.transition("candidate", "serve", "release-manager"))

    def test_lifecycle_and_exact_rollback(self):
        self.admit()
        self.registry.transition("candidate", "approve", "release-manager")
        self.registry.transition("candidate", "serve", "release-manager")
        self.assertEqual("candidate", self.registry.read()["serving"])
        self.registry.transition("candidate", "rollback", "release-manager")
        state = self.registry.read()
        self.assertEqual("baseline", state["serving"])
        self.assertEqual(sha256(BASELINE), state["records"]["baseline"]["sha256"])
        self.assertEqual(["admit_shadow", "approve", "serve", "rollback"], [x["action"] for x in state["audit"]])

    def test_rollback_integrity(self):
        self.admit()
        self.registry.transition("candidate", "approve", "release-manager")
        self.registry.transition("candidate", "serve", "release-manager")
        state = self.registry.read()
        state["records"]["baseline"]["bytes_b64"] = "dGFtcGVyZWQ="
        self.registry.path.write_bytes(canonical(state))
        self.deny("registry_integrity", lambda: self.registry.transition("candidate", "rollback", "release-manager"))

    def test_missing_rollback_artifact(self):
        self.admit()
        self.registry.transition("candidate", "approve", "release-manager")
        self.registry.transition("candidate", "serve", "release-manager")
        state = self.registry.read()
        del state["records"]["baseline"]
        self.registry.path.write_bytes(canonical(state))
        self.deny("rollback_missing", lambda: self.registry.transition("candidate", "rollback", "release-manager"))

    def test_paths_cannot_escape_bundle(self):
        write_bundle(self.bundle)
        manifest = parse_json((self.bundle / "manifest.json").read_bytes())
        manifest["artifacts"]["candidate"]["file"] = "../secret.bin"
        data = canonical(manifest)
        (self.bundle / "manifest.json").write_bytes(data)
        self.deny("artifact_path", lambda: self.registry.admit("candidate", self.bundle, sha256(data)))

    def test_duplicate_candidate(self):
        self.admit()
        self.deny("duplicate_candidate", lambda: self.admit())

    def test_registry_schema_validation(self):
        pristine = self.registry.read()
        for field, value in [("schema_version", True), ("revision", True), ("revision", -1),
                             ("serving", []), ("records", []), ("audit", {})]:
            with self.subTest(field=field, value=value):
                state = copy.deepcopy(pristine)
                state[field] = value
                self.registry.path.write_bytes(canonical(state))
                self.deny("registry_schema", self.registry.read)

    def test_registry_evidence_fields(self):
        self.admit()
        pristine = self.registry.read()
        for field in ("baseline_sha256", "predecessor", "evaluated_at", "manifest_sha256"):
            with self.subTest(field=field):
                state = copy.deepcopy(pristine)
                del state["records"]["candidate"][field]
                self.registry.path.write_bytes(canonical(state))
                self.deny("registry_schema", lambda: self.registry.transition("candidate", "approve", "release-manager"))
        for field, value, expected in [("baseline_sha256", "x", "registry_schema"),
                                       ("predecessor", [], "registry_schema"),
                                       ("evaluated_at", "yesterday", "invalid_timestamp"),
                                       ("baseline_sha256", "0" * 64, "rollback_mismatch")]:
            with self.subTest(field=field, value=value):
                state = copy.deepcopy(pristine)
                state["records"]["candidate"][field] = value
                self.registry.path.write_bytes(canonical(state))
                self.deny(expected, self.registry.read)

    def test_public_gallery(self):
        result = run_gallery()
        self.assertEqual(22, result["scenario_count"])
        self.assertEqual(22, result["passed"])
        self.assertEqual(19, result["denials_preserving_state"])

    def test_html_escapes_fixture_text(self):
        result = run_gallery()
        result["cases"][0]["name"] = '<script>alert("x")</script>'
        page = render_html(result)
        self.assertNotIn('<script>alert', page)
        self.assertIn('&lt;script&gt;', page)


if __name__ == "__main__":
    unittest.main()
