"""Regression checks for the claims carried by reusable visual artifacts."""
import unittest
import xml.etree.ElementTree as ET
from observatory.report import cadence_svg, make_html, summary_svg, phone_figures, phone_cadence


def report_stub():
    return {'metrics': {'exact': {'tp': 44, 'fp': 36}, 'lexical': {'tp': 44, 'fp': 36},
                        'progress': {'tp': 60, 'fp': 0}},
            'traces': [{'replay': {'rows': [{}] * (6 if i < 20 else 8)}} for i in range(24)],
            'cadence': {'stall_window': 3, 'milestones': 6, 'gaps': 5,
                        'points': [{'status_messages': k, 'healthy_alerts': max(0, 5 * (k - 2)),
                                    'stalled_alerts': 4 + 5 * k} for k in range(7)]}}


class ReportTests(unittest.TestCase):
    def test_summary_denominator_follows_observed_records(self):
        result = report_stub()
        result['traces'] = [{'replay': {'rows': [{}] * 11}}]
        root = ET.fromstring(summary_svg(result))
        visible = ' '.join(node.text or '' for node in root.iter('{http://www.w3.org/2000/svg}text'))
        self.assertIn('1 development traces · 11 events', visible)
        self.assertNotIn('152 events', visible)

    def test_cadence_boundary_and_denominator_follow_recorded_policy(self):
        result = report_stub()
        result['cadence'].update(stall_window=4, milestones=8, gaps=7)
        root = ET.fromstring(cadence_svg(result))
        visible = ' '.join(node.text or '' for node in root.iter('{http://www.w3.org/2000/svg}text'))
        self.assertIn('4-event policy', visible)
        self.assertIn('Event 4: alert boundary', visible)
        self.assertIn('8 + 7k events', visible)
        boundary = next(node for node in root.iter() if node.get('data-policy-boundary') is not None)
        self.assertEqual(boundary.get('data-policy-boundary'), '4')
        self.assertEqual(float(boundary.get('x1')), 700)
        html = make_html(result)
        self.assertIn('monitor alerts at 4 agent events', html)
        self.assertNotIn('<!--POLICY_WINDOW-->', html)

    def test_phone_figures_match_records(self):
        result = report_stub()
        result['metrics']['exact'] = {'tp': 19, 'fp': 7}
        cards = ET.fromstring(phone_figures(result))
        articles = {node.get('data-monitor'): node for node in cards.findall('article')}
        self.assertEqual(set(articles), set(result['metrics']))
        for name, metric in result['metrics'].items():
            self.assertEqual([int(node.text) for node in articles[name].iter('strong')], [metric['tp'], metric['fp']])
        result['cadence']['points'][3]['healthy_alerts'] = 17
        cadence = ET.fromstring(phone_cadence(result))
        self.assertEqual(len(cadence.findall('article')), len(result['cadence']['points']))
        maximum = max(max(p['healthy_alerts'], p['stalled_alerts']) for p in result['cadence']['points'])
        for article, point in zip(cadence.findall('article'), result['cadence']['points']):
            self.assertEqual(int(article.get('data-gap')), point['status_messages'])
            for row in article.findall('div'):
                value = point[row.get('data-series')]
                self.assertEqual(int(row.get('data-value')), value)
                self.assertEqual(int(row.find('strong').text), value)
                bar = row.find("span[@class='phone-bar-track']/span")
                self.assertEqual(bar.get('style'), f'width:{value / maximum * 100:.3f}%')

    def test_summary_carries_policy_construction_caveat(self):
        figure = summary_svg(report_stub())
        sentence = ('Expected labels encode the verified-progress policy, so 60/0 is conformance by construction. '
                    'This monitor also sees artifacts and waits; the baselines see text only.')
        self.assertIn(sentence, figure)
        root = ET.fromstring(figure)
        # Visible SVG text must carry the caution, not just hidden description.
        visible = ' '.join(node.text or '' for node in root.iter('{http://www.w3.org/2000/svg}text'))
        self.assertIn('60/0 is conformance by construction.', visible)
        self.assertIn('baselines see text only.', visible)
        self.assertNotIn('Labels are external', figure)

    def test_cadence_uses_measured_counts(self):
        result = report_stub()
        result['cadence']['points'][3]['healthy_alerts'] = 17
        figure = cadence_svg(result)
        root = ET.fromstring(figure)
        labels = [node.text for node in root.iter('{http://www.w3.org/2000/svg}text')]
        self.assertIn('17', labels)
        self.assertIn('Event 3: alert boundary', labels)
        self.assertEqual(len(list(root.iter('{http://www.w3.org/2000/svg}polyline'))), 2)
        self.assertIn('matched length', figure)

    def test_reusable_cadence_figure_discloses_trace_denominator(self):
        figure = cadence_svg(report_stub())
        self.assertIn('alerts per trace', figure)
        self.assertIn('6 milestones', figure)
        self.assertIn('same number of events', figure)
        self.assertIn('6 + 5k events', figure)

    def test_report_attaches_selectable_limit_to_conformance_figure(self):
        html = make_html(report_stub())
        self.assertLess(html.index('id="summary-figure"'), html.index('id="sparse-limitation"'))
        self.assertLess(html.index('id="sparse-limitation"'), html.index('id="cadence-figure"'))
        self.assertIn('outside the matrix', html)
        self.assertIn('const optionOrder=[...mainOptions,...controlOptions]', html)
        self.assertIn('6 + 5k events', html)

    def test_timeline_has_fixed_labels_and_noncolor_status_encodings(self):
        html = make_html(report_stub())
        self.assertIn('class="lane-labels"', html)
        self.assertIn('class="chart-scroll" tabindex="0"', html)
        for name in ('evidence_error', 'complete', 'alert', 'waiting'):
            self.assertIn('data-state="' + name + '"', html)
        self.assertIn('data-wait-band="true"', html)
        self.assertIn("row.idle_agent_events===1?'event':'events'", html)


if __name__ == '__main__':
    unittest.main()
