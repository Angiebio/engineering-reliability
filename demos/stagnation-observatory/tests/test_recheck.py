"""Outside-review regressions: isolate the guard and assert its actual outcome."""
import copy
import json
import unittest
from unittest.mock import patch

from observatory.core import Event, canonical, replay, sha256, validate_trace
from observatory.fixtures import event, fixture_bank


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.trace = {'trace_id': 'review', 'task_id': 'packet', 'events': []}
        self.inputs = {'spec': {'task_id': 'packet', 'criteria': {'stage': ['x']}, 'waits': {}},
                       'pinned_digests': {}, 'store': {}}

    def call(self):
        return replay(self.trace, **self.inputs)

    def pin(self, content):
        self.inputs['store']['output'] = content
        self.inputs['pinned_digests']['output'] = sha256(content.encode('utf-8'))
        self.trace['events'] = [event('packet', 1, 'Result', kind='result', criterion='stage', artifact='output')]

    def wait(self, tick, until):
        # Policy is authored first; the trace is made from these test-author
        # parameters, never the source of its own authorization.
        self.inputs['spec']['waits'][f'event{tick}'] = {'tick': tick, 'wait_until': until, 'wake_condition': 'service response'}
        return event('packet', tick, 'Wait', kind='wait', until=until, wake='service response')

    def test_trusted_wait_horizon_is_exact(self):
        self.trace['events'] = [self.wait(1, 7)]
        self.assertEqual(self.call()['rows'][0]['reason'], 'controller_wait_declared')
        for until in (8, 999):
            self.trace['events'] = [self.wait(1, until)]
            with self.subTest(until=until), self.assertRaisesRegex(ValueError, '^invalid trusted wait declaration$'):
                self.call()

    def test_event_wait_horizon_is_exact(self):
        self.assertEqual(Event.parse(event('packet', 1, 'Wait', kind='wait', until=7, wake='service')).wait_until, 7)
        for until in (1, 8, 999):
            with self.subTest(until=until), self.assertRaisesRegex(ValueError, '^wait must have a bounded future expiry$'):
                Event.parse(event('packet', 1, 'Wait', kind='wait', until=until, wake='service'))

    def test_duplicate_items_reach_the_item_guard(self):
        self.pin(canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': ['x', 'x']}).decode())
        row = self.call()['rows'][0]
        self.assertEqual(row['status'], 'evidence_error')
        self.assertEqual(row['reason'], 'invalid_artifact_schema')
        self.assertFalse(row['new_progress'])
        self.assertEqual(row['evidence']['actual_sha256'], self.inputs['pinned_digests']['output'])
        self.assertEqual(self.call()['completed'], [])

    def test_empty_and_partial_item_sets_do_not_complete_a_criterion(self):
        self.inputs['spec']['criteria']['stage'] = ['x', 'y', 'z']
        for items in ([], ['x'], ['x', 'y'], ['x', 'y', 'z', 'extra']):
            self.pin(canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': items}).decode())
            row = self.call()['rows'][0]
            with self.subTest(items=items):
                self.assertEqual(row['evidence']['status'], 'criterion_not_met')
                self.assertEqual(row['evidence']['reason'], 'items_do_not_match')
                self.assertFalse(row['new_progress'])
                self.assertEqual(self.call()['completed'], [])
        self.pin(canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': ['z', 'x', 'y']}).decode())
        self.assertEqual(self.call()['completed'], ['stage'])

    def test_deep_json_is_an_evidence_error(self):
        self.pin('[' * 30000 + ']' * 30000)
        row = self.call()['rows'][0]
        self.assertEqual(row['status'], 'evidence_error')
        self.assertEqual(row['reason'], 'invalid_artifact_json')
        self.assertFalse(row['new_progress'])

    def test_agent_cannot_jump_to_a_future_authorized_wait(self):
        self.trace['events'] = [event('packet', tick, 'Loop') for tick in (1, 2, 3)] + [self.wait(50, 55)]
        with self.assertRaisesRegex(ValueError, '^tick must equal the next accepted event ordinal$'):
            self.call()
        self.trace['events'] = [event('packet', tick, 'Loop') for tick in range(1, 50)] + [self.wait(50, 55)]
        output = self.call()
        self.assertEqual(sum(row['status'] == 'alert' for row in output['rows']), 47)
        self.assertEqual(output['rows'][-1]['reason'], 'controller_wait_declared')

    def test_spec_task_binding_rejects_an_otherwise_valid_trace(self):
        self.trace['events'] = [event('packet', 1, 'Loop')]
        self.inputs['spec']['task_id'] = 'another'
        with self.assertRaisesRegex(ValueError, '^trace does not match trusted task$'):
            self.call()

    def test_pin_format_has_its_own_rejection(self):
        self.pin(canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': ['x']}).decode())
        for digest in ('A' * 64, 'g' * 64, '0' * 63, '0' * 65):
            self.inputs['pinned_digests']['output'] = digest
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, '^invalid pinned digest$'):
                self.call()

    def test_controller_role_cannot_label_a_message_or_result(self):
        self.pin(canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': ['x']}).decode())
        for record in (event('packet', 1, 'Loop'), self.trace['events'][0]):
            record['role'] = 'controller'
            self.trace['events'] = [record]
            with self.subTest(kind=record['kind']), self.assertRaisesRegex(ValueError, '^controller events are limited to wait declarations$'):
                self.call()

    def test_wait_resets_an_already_alerting_clock(self):
        self.trace['events'] = [event('packet', tick, 'Loop') for tick in range(1, 5)] + [self.wait(5, 8)]
        self.trace['events'] += [event('packet', tick, 'Loop') for tick in range(6, 11)]
        rows = self.call()['rows']
        self.assertEqual([row['idle_agent_events'] for row in rows], [1, 2, 3, 4, 0, 0, 0, 1, 2, 3])
        self.assertEqual([row['status'] for row in rows[4:]], ['waiting', 'waiting', 'waiting', 'observing', 'observing', 'alert'])

    def test_lexical_neighbours_below_the_policy_do_not_alert(self):
        for match_count in (86, 87, 88, 89):
            a = 'a' * match_count + 'b' * (100 - match_count)
            b = 'a' * match_count + 'c' * (100 - match_count)
            self.trace['events'] = [event('packet', 1, a), event('packet', 2, a), event('packet', 3, b)]
            row = self.call()['rows'][-1]
            with self.subTest(match_count=match_count):
                self.assertEqual(row['lexical_similarity'], match_count / 100)
                self.assertEqual(row['lexical_alert'], match_count >= 88)

    def test_alternating_messages_do_not_match_both_predecessors(self):
        self.trace['events'] = [event('packet', tick, text) for tick, text in enumerate(('Alpha status.', 'Entirely different.', 'Alpha status.'), 1)]
        row = self.call()['rows'][-1]
        self.assertFalse(row['exact_alert'])
        self.assertFalse(row['lexical_alert'])
        self.assertEqual(row['status'], 'alert')

    def test_identical_duplicate_json_keys_are_rejected(self):
        self.pin('{"task_id":"packet","task_id":"packet","criterion_id":"stage","items":["x"]}')
        self.assertEqual(self.call()['rows'][0]['reason'], 'invalid_artifact_json')

    def test_uncited_invalid_store_entry_is_a_batch_validation_error(self):
        self.trace['events'] = [event('packet', 1, 'Loop')]
        self.inputs['store']['unused'] = 123
        with self.assertRaisesRegex(ValueError, '^artifact store entries require valid IDs and UTF-8 text of at most 65536 bytes; not manifests$'):
            self.call()

    def test_unused_harness_inputs_are_explicit_diagnostics(self):
        self.trace['events'] = [event('packet', 1, 'Loop')]
        self.inputs['pinned_digests']['unused'] = '0' * 64
        self.inputs['store']['unused'] = '{}'
        self.wait(5, 8)
        self.assertEqual(self.call()['input_diagnostics'], {'unused_pins': ['unused'], 'unused_waits': ['event5'], 'unused_store_entries': ['unused']})

    def test_text_and_artifact_byte_limits(self):
        self.assertEqual(len(Event.parse(event('packet', 1, '\u00e9' * 4096)).text.encode('utf-8')), 8192)
        with self.assertRaisesRegex(ValueError, '^event text must contain 1..8192 bytes$'):
            Event.parse(event('packet', 1, '\u00e9' * 4096 + 'x'))
        content = canonical({'task_id': 'packet', 'criterion_id': 'stage', 'items': ['x']}).decode()
        self.pin(content + ' ' * (65536 - len(content)))
        self.assertEqual(self.call()['completed'], ['stage'])
        self.inputs['store']['output'] += ' '
        with self.assertRaisesRegex(ValueError, '^artifact store entries require valid IDs and UTF-8 text of at most 65536 bytes; not manifests$'):
            self.call()

    def test_event_count_limit(self):
        self.trace['events'] = [event('packet', tick, 'Loop') for tick in range(1, 10001)]
        self.assertEqual(len(validate_trace(self.trace, **self.inputs)), 10000)
        self.trace['events'].append(event('packet', 10001, 'Loop'))
        with self.assertRaisesRegex(ValueError, '^trace must contain 1..10000 events$'):
            self.call()

    def test_fixture_wait_policy_does_not_copy_agent_events(self):
        def changed_event(*args, **kwargs):
            result = event(*args, **kwargs)
            if result['kind'] == 'wait':
                result['wake_condition'] = 'agent changed this after authoring'
            return result
        with patch('observatory.fixtures.event', side_effect=changed_event):
            traces, labels, harness = fixture_bank()
        trace = next(row for row in traces if labels[row['trace_id']]['family'] == 'legitimate_wait')
        with self.assertRaisesRegex(ValueError, '^wait does not match a trusted controller declaration$'):
            replay(trace, **harness[trace['trace_id']])


if __name__ == '__main__':
    unittest.main()
