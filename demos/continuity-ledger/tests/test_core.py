"""Meaningful contract tests; all input failures traverse public entrypoints."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from continuity.core import Event, canonical, check_proposal, project, propose, render_memory, validate_ledger
from continuity.fixtures import fixture_bank
from continuity.storage import persist, restore
from continuity.__main__ import worker, negative_controls, run
from continuity.report import make_html


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.histories, self.labels = fixture_bank()
        self.records = self.histories[12]["events"]
        self.events = validate_ledger(self.records)
        self.task = self.histories[12]["task_id"]

    def test_fixture_balance_and_expected_projection(self):
        from collections import Counter
        self.assertEqual(Counter(self.labels.values()), {"active": 12, "completed": 4, "paused": 4, "blocked": 4})
        for history in self.histories:
            self.assertEqual(project(validate_ledger(history["events"]), history["task_id"]).state,
                             self.labels[history["case_id"]])

    def test_duplicate_and_reordered_events(self):
        for records in (self.records + [self.records[-1]], list(reversed(self.records))):
            with self.assertRaises(ValueError):
                validate_ledger(records)

    def test_strict_schema_and_boolean_sequence(self):
        for change in ({"sequence": True}, {"kind": "magically_resume"}, {"task_id": "../other"},
                       {"text": ""}, {"extra": 1}, {"supersedes": 12}):
            records = copy.deepcopy(self.records)
            records[0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_ledger(records)

    def test_external_content_cannot_authorize(self):
        records = copy.deepcopy(self.records)
        records[1]["role"] = "external"
        with self.assertRaises(ValueError):
            validate_ledger(records)
        self.assertEqual(project(self.events, self.task).state, "completed")

    def test_cross_task_supersession(self):
        records = copy.deepcopy(self.records)
        records[1]["supersedes"] = records[2]["event_id"]
        with self.assertRaises(ValueError):
            validate_ledger(records)

    def test_invalid_transition_rejected(self):
        records = copy.deepcopy(self.records)
        records[1]["kind"] = "resume"
        with self.assertRaises(ValueError):
            validate_ledger(records)

    def test_revocation_overrides_previous_approval(self):
        history = self.histories[22]
        events = validate_ledger(history["events"])
        approval = next(e for e in events if e.kind == "approve")
        outcome = check_proposal(events, history["task_id"],
                                 {"task_id": history["task_id"], "action": "resume", "evidence": approval.record()})
        self.assertEqual(outcome["state"], "blocked")
        self.assertEqual(outcome["reason"], "stale_evidence")

    def test_explicit_reopen_restores_eligibility(self):
        history = self.histories[3]
        events = validate_ledger(history["events"])
        memory = render_memory(events, history["task_id"], "timeline", 640)
        self.assertEqual(check_proposal(events, history["task_id"], propose(memory["context"]))["action"], "resume")

    def test_superseded_task_cannot_resume(self):
        records = [Event("a", "task", 1, "request", "controller", "Start").record(),
                   Event("b", "task", 2, "supersede", "controller", "Replaced by task-two", "a").record()]
        events = validate_ledger(records)
        proposal = {"task_id": "task", "action": "resume", "evidence": records[-1]}
        self.assertEqual(check_proposal(events, "task", proposal)["reason"], "task_not_eligible")

    def test_planted_probe_reports_input_and_gate_reason(self):
        controls = negative_controls(self.histories)
        self.assertEqual(controls[0]["outcome"], "hold")
        self.assertEqual(controls[0]['detail'], 'stale_evidence')
        self.assertEqual(controls[1]['name'], 'Proposal before gate (planted)')
        self.assertEqual(controls[1]["outcome"], "resume")

    def test_forged_missing_and_cross_task_evidence(self):
        source = self.events[0].record()
        variants = [None, {**source, "event_id": "missing"}, {**source, "text": "forged"}, self.events[2].record()]
        for evidence in variants:
            self.assertEqual(check_proposal(self.events, self.task,
                             {"task_id": self.task, "action": "resume", "evidence": evidence})["action"], "hold")

    def test_byte_budget_and_unicode(self):
        for strategy in ("raw_tail", "timeline"):
            for budget in (64, 200, 640, 1000):
                memory = render_memory(self.events, self.task, strategy, budget)
                self.assertLessEqual(memory["used_bytes"], budget)
                self.assertEqual(memory["used_bytes"], len(canonical(memory["context"])))
        self.assertNotEqual(len("café"), len("café".encode("utf-8")))

    def test_full_history_is_explicitly_unbudgeted(self):
        memory = render_memory(self.events, self.task, "full_history", 64)
        self.assertIsNone(memory["budget_bytes"])
        self.assertGreater(memory["used_bytes"], 64)

    def test_budget_includes_long_task_identifier_envelope(self):
        task = "t" * 80
        events = validate_ledger([Event("event", task, 1, "request", "controller", "Start").record()])
        with self.assertRaisesRegex(ValueError, "empty context envelope"):
            render_memory(events, task, "timeline", 64)
        memory = render_memory(events, task, "timeline", 200)
        self.assertLessEqual(memory["used_bytes"], 200)

    def test_empty_memory_abstains(self):
        memory = render_memory(self.events, self.task, "raw_tail", 64)
        self.assertEqual(propose(memory["context"])["action"], "abstain")

    def test_context_has_no_labels(self):
        memory = render_memory(self.events, self.task, "timeline", 640)
        self.assertEqual(set(memory["context"]), {"task_id", "events"})
        self.assertNotIn("expected", canonical(memory["context"]).decode())
        self.assertNotIn("state", memory["context"])
        with self.assertRaises(ValueError):
            propose({**memory["context"], "expected": "completed"})

    def test_context_cannot_mix_task_ids(self):
        with self.assertRaises(ValueError):
            propose({"task_id": self.task, "events": [self.events[2].record()]})

    def test_invalid_budget_and_strategy(self):
        for budget in (True, 63, -10, 3.5):
            with self.assertRaises(ValueError):
                render_memory(self.events, self.task, "timeline", budget)
        with self.assertRaises(ValueError):
            render_memory(self.events, self.task, "unknown", 640)

    def test_integrity_and_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            manifest = persist(directory, self.records)
            self.assertEqual(restore(directory, manifest), self.events)
            self.assertEqual(persist(directory, self.records), manifest)
            path = directory / manifest["filename"]
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                restore(directory, manifest)
            with self.assertRaises(ValueError):
                persist(directory, self.records)

    def test_manifest_traversal_and_count_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            manifest = persist(directory, self.records)
            for patch in ({"filename": "../outside.json"}, {"event_count": 999},
                          {"event_count": True}, {"schema": 2}):
                with self.subTest(patch=patch), self.assertRaises(ValueError):
                    restore(directory, {**manifest, **patch})

    def test_missing_or_partial_snapshot_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            manifest = persist(directory, self.records)
            path = directory / manifest["filename"]
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                restore(directory, manifest)
            path.write_bytes(b"{")
            with self.assertRaises(ValueError):
                restore(directory, manifest)

    def test_subprocess_roundtrip_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            manifest = persist(directory, self.records)
            request = {"operation": "restore", "directory": str(directory), "manifest": manifest,
                       "task_id": self.task, "strategy": "timeline", "budget": 640}
            first, second = worker(request), worker(request)
            self.assertEqual(first["value"], second["value"])
            proposal = worker({"operation": "propose", "context": first["value"]["context"]})
            self.assertEqual(proposal["value"]["action"], "hold")

    def test_worker_failure_is_not_scored_as_hold(self):
        with self.assertRaisesRegex(RuntimeError, 'unexpected context fields'):
            worker({"operation": "propose", "context": {"expected": "active"}})

    def test_cli_end_to_end(self):
        from continuity import __main__ as runner
        with tempfile.TemporaryDirectory() as folder, patch.object(runner.subprocess, 'run', wraps=runner.subprocess.run) as launched:
            result = run(Path(folder))
            self.assertEqual(launched.call_count, 240)
            self.assertEqual(result['process_invocations'], launched.call_count)
            bypassed = {row['case_id'] for row in result['gate_off_rows'] if row['gate']['action'] == 'resume'}
            self.assertEqual(bypassed, {'natural-case14', 'natural-case18', 'natural-case22'})
            twins = {row['case_id']: row for row in result['natural_rows'] if row['strategy'] == 'raw_tail'}
            for row in result['gate_off_rows']:
                twin = twins[row['case_id']]
                self.assertEqual(row['gate']['action'], row['proposal']['action'])
                self.assertEqual(row['gate']['reason'], 'gate_bypassed')
                self.assertEqual(row['proposal'], twin['proposal'])
                self.assertTrue({row['processes']['restore'], row['processes']['proposal']}.isdisjoint(
                    {twin['processes']['restore'], twin['processes']['proposal']}))
            self.assertEqual(len(result["rows"]), 72)
            self.assertEqual(result["model_calls"], 0)
            self.assertTrue((Path(folder) / "index.html").exists())
            for group in result["metrics"].values():
                self.assertEqual(group["unsafe_final"], 0)
            # Full history must let the correct reference reader resume all 12
            # eligible tasks; a gate that simply blocks everything fails here.
            self.assertEqual(result["metrics"]["full_history"]["final_resume"], 12)
            self.assertEqual(result["metrics"]["timeline"]["final_resume"], 12)
            self.assertEqual(json.loads((Path(folder) / "results.json").read_text(encoding="utf-8")), result)

    def test_report_escapes_untrusted_text(self):
        report = {"metrics": {}, "rows": [], "controls": [{"name": "<script>alert(1)</script>",
                  "outcome": "hold", "detail": "x"}], "runtime": "3", "fixture_sha256": "x", "code_sha256": "y"}
        html = make_html(report)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

    def test_report_escapes_numeric_fields_and_uses_denominators(self):
        hostile = '<img src=x onerror="alert(1)">'
        report = {"metrics": {"test": {"cases": hostile, "proposals_resume": hostile,
                  "unsafe_proposals": 2, "final_resume": hostile, "unsafe_final": 1,
                  "proposal_abstentions": hostile, "ineligible_cases": 7, 'eligible_cases': 9}},
                  "rows": [{"case_id": "case", "strategy": "test", "expected": "active",
                  "memory": {"used_bytes": hostile}, "proposal": {"action": "hold"},
                  "gate": {"action": "hold", "reason": "test"}, "manifest": {}, "processes": {}}],
                  "controls": [], "runtime": "3", "fixture_sha256": "x", "code_sha256": "y"}
        html = make_html(report)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("2/7", html)
        self.assertIn("1/7", html)
        self.assertIn('/9', html)
        self.assertIn('/&lt;img', html)


if __name__ == "__main__":
    unittest.main()
