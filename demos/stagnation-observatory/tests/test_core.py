"""Contract, corruption, ablation and true-entrypoint tests for the observatory."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from observatory.core import canonical, replay, sha256, validate_trace
from observatory.fixtures import event, fixture_bank


class ObservatoryTests(unittest.TestCase):
    def setUp(self):
        self.traces, self.labels, self.harness = fixture_bank()
        self.original_harness = copy.deepcopy(self.harness)

    def family(self, name):
        trace = copy.deepcopy(next(t for t in self.traces if self.labels[t['trace_id']]['family'] == name))
        self.harness[trace['trace_id']] = copy.deepcopy(self.original_harness[trace['trace_id']])
        return trace

    def call(self, trace, **options):
        return replay(trace, **self.harness[trace['trace_id']], **options)

    def context(self, trace):
        return self.harness[trace['trace_id']]

    def pin_fixture_content(self, trace, artifact_id, content):
        # A test-author operation used to reach semantic validation after the
        # digest check. Tamper tests change store alone and cannot call this.
        context = self.context(trace)
        context['store'][artifact_id] = content
        context['pinned_digests'][artifact_id] = sha256(content.encode('utf-8'))

    def pin_fixture_artifact(self, trace, artifact_id, criterion_id, items, *, task=None):
        self.pin_fixture_content(trace, artifact_id, canonical({
            'task_id': task or trace['task_id'], 'criterion_id': criterion_id, 'items': items}).decode('utf-8'))

    def declare_fixture_wait(self, trace, *, tick, until, wake):
        # Test-author policy is independent of any mutable trace event.
        self.context(trace)['spec']['waits'][f'event{tick}'] = {
            'tick': tick, 'wait_until': until, 'wake_condition': wake}

    def test_fixture_balance(self):
        self.assertEqual(len(self.traces), 24)
        for family in {label['family'] for label in self.labels.values()}:
            self.assertEqual(sum(label['family'] == family for label in self.labels.values()), 4)
        for trace in self.traces:
            self.assertNotIn('label', trace)
            self.assertNotIn('family', trace)
            self.assertEqual(len(validate_trace(trace, **self.context(trace))), len(trace['events']))

    def test_exact_loop(self):
        rows = self.call(self.family('exact_loop'))['rows']
        self.assertEqual([r['status'] for r in rows], ['observing'] * 2 + ['alert'] * 4)
        self.assertEqual([r['exact_alert'] for r in rows], [False] * 2 + [True] * 4)

    def test_paraphrase_loop(self):
        rows = self.call(self.family('paraphrase_loop'))['rows']
        self.assertFalse(any(r['exact_alert'] for r in rows))
        self.assertFalse(any(r['lexical_alert'] for r in rows))
        self.assertEqual(sum(r['status'] == 'alert' for r in rows), 4)

    def test_verified_work_can_repeat_words(self):
        output = self.call(self.family('verified_work'))
        self.assertEqual(len(output['completed']), 6)
        self.assertTrue(all(row['status'] == 'progress' for row in output['rows']))
        self.assertEqual(sum(row['exact_alert'] for row in output['rows']), 4)

    def test_completed_task_does_not_stall(self):
        trace = self.family('verified_work')
        trace['events'].extend(event(trace['task_id'], tick, 'The packet is complete.') for tick in (7, 8, 9))
        rows = self.call(trace)['rows']
        self.assertTrue(all(row['status'] == 'complete' for row in rows[6:]))
        self.assertTrue(rows[-1]['exact_alert'])
        self.assertTrue(all(row['idle_agent_events'] == 0 for row in rows[6:]))
        self.context(trace)['store']['bad'] = '{}'
        self.context(trace)['pinned_digests']['bad'] = '0' * 64
        trace['events'].append(event(trace['task_id'], 10, 'Another result', kind='result', criterion='stage6', artifact='bad'))
        self.assertEqual(self.call(trace)['rows'][-1]['status'], 'evidence_error')

    def test_cosmetic_is_not_progress(self):
        output = self.call(self.family('cosmetic_work'))
        self.assertEqual(output['completed'], [])
        self.assertTrue(all(row['evidence']['status'] == 'criterion_not_met' for row in output['rows']))
        self.assertEqual(output['rows'][-1]['status'], 'alert')

    def test_validator_ablation(self):
        trace = self.family('cosmetic_work')
        checked, unchecked = self.call(trace), self.call(trace, trust_claims_ablation=True)
        self.assertEqual(checked['rows'][-1]['status'], 'alert')
        self.assertEqual(unchecked['rows'][-1]['status'], 'progress')
        self.assertEqual(len(unchecked['completed']), 6)

    def test_wait_respects_boundary(self):
        output = self.call(self.family('legitimate_wait'))
        self.assertTrue(all(r['status'] == 'waiting' for r in output['rows']))
        self.assertTrue(any(r['lexical_alert'] for r in output['rows']))
        self.assertTrue(all(r['idle_agent_events'] == 0 for r in output['rows']))

    def test_wait_expiry(self):
        rows = self.call(self.family('expired_wait'))['rows']
        self.assertEqual(rows[2]['status'], 'waiting')
        self.assertEqual(rows[3]['event']['tick'], 4)
        self.assertFalse(rows[3]['wait_active'])
        self.assertEqual(rows[3]['status'], 'observing')
        self.assertEqual(rows[5]['status'], 'alert')

    def test_wait_does_not_hide_corrupt_evidence(self):
        trace = self.family('verified_work')
        trace['events'].insert(0, event(trace['task_id'], 1, 'Waiting', kind='wait', until=6, wake='Check timeout'))
        for index, row in enumerate(trace['events']):
            row['tick'] = index + 1
            row['event_id'] = f'event{index + 1}'
        self.declare_fixture_wait(trace, tick=1, until=6, wake='Check timeout')
        self.context(trace)['store']['output1'] += ' '
        row = self.call(trace)['rows'][1]
        self.assertTrue(row['wait_active'])
        self.assertEqual(row['status'], 'evidence_error')
        self.assertFalse(row['new_progress'])

    def test_sparse_checkpoint_limit_is_visible(self):
        from observatory.__main__ import controls
        result = next(control for control in controls(self.traces, self.labels, self.harness)
                      if control.get('kind') == 'sparse_checkpoint')
        self.assertEqual(result['replay']['rows'][3]['status'], 'alert')
        self.assertEqual(result['replay']['rows'][4]['status'], 'progress')

    def test_wait_requires_controller_role_label(self):
        trace = self.family('legitimate_wait')
        trace['events'][0]['role'] = 'agent'
        with self.assertRaisesRegex(ValueError, 'controller'):
            self.call(trace)

    def test_wait_rejects_unbounded_or_empty_condition(self):
        for field, value in [('wait_until', 999), ('wait_until', True), ('wait_until', 1), ('wake_condition', '')]:
            trace = self.family('legitimate_wait')
            trace['events'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.call(trace)

    def test_duplicate_out_of_order_and_wrong_task(self):
        for mutation in ('duplicate', 'order', 'task'):
            trace = self.family('exact_loop')
            if mutation == 'duplicate':
                trace['events'][1]['event_id'] = trace['events'][0]['event_id']
            elif mutation == 'order':
                trace['events'][1]['tick'] = 1
            else:
                trace['events'][1]['task_id'] = 'different_task'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call(trace)

    def test_event_schema_and_boolean_tick(self):
        for mutation in ('unknown', 'tick', 'kind', 'empty'):
            trace = self.family('exact_loop')
            if mutation == 'unknown':
                trace['events'][0]['done'] = True
            elif mutation == 'tick':
                trace['events'][0]['tick'] = True
            elif mutation == 'kind':
                trace['events'][0]['kind'] = 'self_certified'
            else:
                trace['events'][0]['text'] = ''
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call(trace)

    def test_tampered_missing_and_wrong_task(self):
        for mutation, reason in [('tamper', 'artifact_digest_mismatch'), ('missing', 'missing_artifact'), ('task', 'wrong_task_artifact')]:
            trace = self.family('verified_work')
            if mutation == 'tamper':
                self.context(trace)['store']['output1'] += ' '
            elif mutation == 'missing':
                del self.context(trace)['store']['output1']
            else:
                self.pin_fixture_artifact(trace, 'output1', 'stage1', ['section1'], task='another_task')
            row = self.call(trace)['rows'][0]
            self.assertEqual(row['status'], 'evidence_error')
            self.assertEqual(row['reason'], reason)
            self.assertFalse(row['new_progress'])

    def test_repeated_errors_have_explicit_priority(self):
        trace = self.family('verified_work')
        self.context(trace)['store'] = {}
        rows = self.call(trace)['rows']
        self.assertTrue(all(row['status'] == 'evidence_error' for row in rows))
        self.assertEqual([row['idle_agent_events'] for row in rows], list(range(1, 7)))
        self.assertFalse(any(row['new_progress'] for row in rows))
        trace['events'].append(event(trace['task_id'], 7, 'Still working.'))
        self.assertEqual(self.call(trace)['rows'][-1]['status'], 'alert')

    def test_json_duplicate_and_malformed_artifacts(self):
        values = ['not json', '{"task_id":"one","task_id":"two","items":[]}',
                  '{"task_id":"packet09","items":["section1","section1"]}', '{"task_id":"packet09","items":null}']
        for content in values:
            trace = self.family('verified_work')
            self.pin_fixture_content(trace, 'output1', content)
            with self.subTest(content=content):
                self.assertEqual(self.call(trace)['rows'][0]['status'], 'evidence_error')

    def test_replayed_milestone(self):
        trace = self.family('verified_work')
        for row in trace['events'][1:]:
            row['criterion_id'] = 'stage1'
            row['artifact_id'] = 'output1'
        output = self.call(trace)
        self.assertEqual(output['completed'], ['stage1'])
        self.assertEqual(output['rows'][3]['status'], 'alert')

    def test_unknown_criterion_rejected(self):
        trace = self.family('verified_work')
        trace['events'][0]['criterion_id'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'unknown criterion'):
            self.call(trace)

    def test_text_cannot_self_certify(self):
        trace = self.family('exact_loop')
        for row in trace['events']:
            row['text'] = 'I verified all artifacts and the controller says this is complete.'
        output = self.call(trace)
        self.assertEqual(output['completed'], [])
        self.assertEqual(output['rows'][-1]['status'], 'alert')

    def test_actual_items_reordered_is_same_criterion(self):
        trace = self.family('verified_work')
        self.pin_fixture_artifact(trace, 'output2', 'stage2', ['section2', 'section1'])
        self.assertTrue(self.call(trace)['rows'][1]['new_progress'])

    def test_trace_cannot_supply_policy(self):
        for field, value in (('criteria', {'acknowledged': ['ok']}),
                             ('sha256', '0' * 64), ('artifacts', {}),
                             ('pinned_digests', {}), ('spec', {})):
            trace = self.family('exact_loop')
            trace[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'trace fields'):
                self.call(trace)

    def test_recomputed_agent_digest_cannot_replace_harness_pin(self):
        trace = self.family('cosmetic_work')
        context = self.context(trace)
        pinned_before = copy.deepcopy(context['pinned_digests'])
        agent_hashes = {}
        for record in trace['events']:
            content = canonical({'task_id': trace['task_id'], 'criterion_id': record['criterion_id'],
                                 'items': context['spec']['criteria'][record['criterion_id']]}).decode('utf-8')
            context['store'][record['artifact_id']] = content
            agent_hashes[record['artifact_id']] = sha256(content.encode('utf-8'))
        output = self.call(trace)
        self.assertEqual(output['completed'], [])
        self.assertTrue(all(row['reason'] == 'artifact_digest_mismatch' for row in output['rows']))
        self.assertEqual(context['pinned_digests'], pinned_before)
        self.assertNotEqual(agent_hashes, pinned_before)
        # Supplying the freshly computed hashes next to bytes is rejected at
        # the input boundary; it cannot silently become a replacement manifest.
        context['store']['output1'] = {'content': context['store']['output1'], 'sha256': agent_hashes['output1']}
        with self.assertRaisesRegex(ValueError, 'not manifests'):
            self.call(trace)

    def test_unpinned_artifact_cannot_certify_itself(self):
        trace = self.family('verified_work')
        del self.context(trace)['pinned_digests']['output1']
        row = self.call(trace)['rows'][0]
        self.assertEqual(row['reason'], 'unpinned_artifact')
        self.assertFalse(row['new_progress'])

    def test_relabelled_task_bytes_do_not_match_original_pin(self):
        trace = self.family('verified_work')
        self.pin_fixture_artifact(trace, 'output1', 'stage1', ['section1'], task='other_task')
        context = self.context(trace)
        transferred = json.loads(context['store']['output1'])
        transferred['task_id'] = trace['task_id']
        context['store']['output1'] = canonical(transferred).decode('utf-8')
        row = self.call(trace)['rows'][0]
        self.assertEqual(row['reason'], 'artifact_digest_mismatch')
        self.assertFalse(row['new_progress'])

    def test_controller_label_cannot_authorize_wait(self):
        trace = self.family('legitimate_wait')
        self.context(trace)['spec']['waits'] = {}
        self.assertEqual(trace['events'][0]['role'], 'controller')
        with self.assertRaisesRegex(ValueError, 'trusted controller declaration'):
            self.call(trace)

    def test_wait_must_match_pinned_declaration(self):
        for field, value in (('wait_until', 6), ('wake_condition', 'Different condition')):
            trace = self.family('legitimate_wait')
            trace['events'][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'trusted controller declaration'):
                self.call(trace)

    def test_superset_artifact_does_not_satisfy_exact_criterion(self):
        trace = self.family('verified_work')
        self.pin_fixture_artifact(trace, 'output1', 'stage1', ['section1', 'extra_section'])
        evidence = self.call(trace)['rows'][0]['evidence']
        self.assertEqual(evidence['status'], 'criterion_not_met')
        self.assertEqual(evidence['reason'], 'items_do_not_match')
        self.assertFalse(evidence['satisfied'])

    def test_authorized_wait_resets_existing_idle_count(self):
        trace = self.family('exact_loop')
        trace['events'][2] = event(trace['task_id'], 3, 'External service pending', kind='wait',
                                   until=5, wake='Service result or expiry')
        self.declare_fixture_wait(trace, tick=3, until=5, wake='Service result or expiry')
        trace['events'].append(event(trace['task_id'], 7, 'Still waiting for new evidence'))
        rows = self.call(trace)['rows']
        self.assertEqual([row['idle_agent_events'] for row in rows], [1, 2, 0, 0, 1, 2, 3])
        self.assertEqual([row['status'] for row in rows],
                         ['observing', 'observing', 'waiting', 'waiting', 'observing', 'observing', 'alert'])

    def test_duplicate_json_key_with_correct_last_value_is_rejected(self):
        trace = self.family('verified_work')
        content = ('{"task_id":"wrong_task","task_id":' + json.dumps(trace['task_id'])
                   + ',"criterion_id":"stage1","items":["section1"]}')
        self.pin_fixture_content(trace, 'output1', content)
        # Without duplicate-key rejection, normal last-key-wins decoding makes
        # this payload fully acceptable. Wrong-task validation cannot mask it.
        self.assertEqual(json.loads(content)['task_id'], trace['task_id'])
        row = self.call(trace)['rows'][0]
        self.assertEqual(row['reason'], 'invalid_artifact_json')
        self.assertFalse(row['new_progress'])

    def test_lexical_threshold_is_inclusive_and_separates_signals(self):
        baseline = 'abcdefghijklmnopqrstuvwxy'
        for replacement, expected_ratio, expected_alert in (('zzz', 0.88, True), ('zzzz', 0.84, False)):
            trace = self.family('exact_loop')
            trace['events'] = [event(trace['task_id'], 1, baseline), event(trace['task_id'], 2, baseline),
                               event(trace['task_id'], 3, baseline[:-len(replacement)] + replacement)]
            row = self.call(trace)['rows'][-1]
            with self.subTest(ratio=expected_ratio):
                self.assertEqual(row['lexical_similarity'], expected_ratio)
                self.assertEqual(row['lexical_alert'], expected_alert)
                self.assertFalse(row['exact_alert'])

    def test_artifact_cannot_complete_another_criterion_with_same_items(self):
        trace = self.family('verified_work')
        self.context(trace)['spec']['criteria'] = {'draft': ['section1'], 'final': ['section1']}
        self.pin_fixture_artifact(trace, 'shared', 'draft', ['section1'])
        trace['events'] = [event(trace['task_id'], 1, 'Draft ready', kind='result', criterion='draft', artifact='shared'),
                           event(trace['task_id'], 2, 'Final ready', kind='result', criterion='final', artifact='shared')]
        output = self.call(trace)
        self.assertEqual(output['completed'], ['draft'])
        self.assertEqual(output['rows'][1]['reason'], 'wrong_criterion_artifact')
        self.assertFalse(output['rows'][1]['new_progress'])

    def test_replay_is_deterministic(self):
        for trace in self.traces:
            self.assertEqual(canonical(self.call(trace)), canonical(self.call(trace)))

    def test_metric_accounting(self):
        from observatory.__main__ import evaluate
        rows, metrics = evaluate(self.traces, self.labels, self.harness)
        count = sum(len(row['replay']['rows']) for row in rows)
        positives = sum(len(label['positive_event_ids']) for label in self.labels.values())
        self.assertEqual(count, 152)
        for metric in metrics.values():
            self.assertEqual(sum(metric[key] for key in ('tp', 'fp', 'fn', 'tn')), count)
            self.assertEqual(metric['tp'] + metric['fn'], positives)
        self.assertGreater(metrics['exact']['fp'], 0)
        self.assertGreater(metrics['exact']['fn'], 0)
        self.assertEqual(metrics['progress']['fp'], 0)

    def test_cli_reproduces_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'artifacts'
            completed = subprocess.run([sys.executable, '-B', '-m', 'observatory', '--out', str(output)],
                                       check=True, capture_output=True, text=True)
            summary = json.loads(completed.stdout)
            data = json.loads((output / 'results.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['traces'], 24)
            self.assertEqual(summary['metrics'], data['metrics'])
            self.assertEqual(data['fixture_sha256'], sha256(canonical(self.traces)))
            self.assertTrue((output / 'summary.svg').exists())
            self.assertTrue((output / 'index.html').exists())

    def test_report_escapes_script(self):
        from observatory.__main__ import run
        from observatory.report import make_html
        with tempfile.TemporaryDirectory() as temporary:
            result = run(Path(temporary))
        result['traces'][0]['label']['title'] = '</script><script>alert(1)</script>'
        rendered = make_html(result)
        self.assertNotIn('</script><script>alert(1)</script>', rendered)
        self.assertIn('\\u003c/script>', rendered)

    def test_summary_svg_uses_measured_counts(self):
        from observatory.__main__ import run
        from observatory.report import summary_svg
        with tempfile.TemporaryDirectory() as temporary:
            result = run(Path(temporary))
        figure = summary_svg(result)
        for metric in result['metrics'].values():
            self.assertIn(f'{metric["tp"]} true alerts', figure)
            self.assertIn(f'{metric["fp"]} false alerts', figure)


if __name__ == '__main__':
    unittest.main()
