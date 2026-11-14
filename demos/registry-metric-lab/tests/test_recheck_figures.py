"""Property-level checks for figures added during the first repair.

Read actual SVG geometry and HTML table cells. Expected values come from saved
SQL results or independently specified numerical examples, never source text.
"""
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from registry_metrics.core import analyze
from registry_metrics.fixtures import scenarios, review_map_fixture
from registry_metrics.__main__ import generate, site_sweep
from registry_metrics.report import geography_svg, sweep_svg, make_html

NS = '{http://www.w3.org/2000/svg}'


class CountryTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.cell = False
        self.rows = []
        self.row = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table' and dict(attrs).get('class') == 'country-table':
            self.active = True
        if self.active and tag == 'tr':
            self.row = []
        if self.active and tag == 'td':
            self.cell = True
            self.row.append('')

    def handle_endtag(self, tag):
        if self.active and tag == 'td':
            self.cell = False
        if self.active and tag == 'tr' and self.row:
            self.rows.append(self.row)
        if tag == 'table':
            self.active = False

    def handle_data(self, data):
        if self.cell:
            self.row[-1] += data


def analyzed_examples():
    for value in scenarios():
        value['result'] = analyze(value['data'], value['country'], value['kind'])
        yield value


class RecheckFigureTests(unittest.TestCase):
    def test_geography_bars_bind_every_group_method_and_value(self):
        examples = list(analyzed_examples())
        zero = deepcopy(examples[0])
        for trial in zero['data']['trials']:
            trial['enrollment'] = 0
        zero['result'] = analyze(zero['data'])
        examples.append(zero)
        for example in examples:
            correct = example['result']['geography']
            joined = {g['country']: g for g in example['result']['incorrect']['geography']}
            peak = max([g['trial_enrollment_sum'] for g in [*correct, *joined.values()] if g['trial_enrollment_sum'] is not None] + [1])
            for compact, span in ((False, 600), (True, 260)):
                with self.subTest(scenario=example['id'], compact=compact):
                    svg = ET.fromstring(geography_svg(example, compact))
                    bars = [n for n in svg.iter(NS+'rect') if n.attrib.get('class') == 'geography-bar']
                    expected = [(g['country'], method, record['trial_enrollment_sum']) for g in correct
                                for method, record in (('Joined', joined[g['country']]), ('Identity', g))]
                    self.assertEqual([(n.attrib['data-country'], n.attrib['data-method']) for n in bars], [(c, m) for c, m, _ in expected])
                    labels = [n.text for n in svg.iter(NS+'text') if (n.text or '').startswith(('Joined:', 'Identity:'))]
                    self.assertEqual(labels, [m + ': ' + ('unknown' if v is None else format(v, ',')) for _, m, v in expected])
                    for bar, (_, method, value) in zip(bars, expected):
                        self.assertEqual(float(bar.attrib['x']), 20)
                        self.assertAlmostEqual(float(bar.attrib['width']), span * (value or 0) / peak)
                        self.assertEqual(bar.attrib['fill'], '#b45e3c' if method == 'Joined' else '#2a7559')

    def test_country_table_preserves_complete_groups_and_denominators(self):
        for example in analyzed_examples():
            parser = CountryTables()
            parser.feed(make_html({'scenarios': [example]}))
            expected = [[g['country'], str(g['trial_count']), str(g['known_enrollment_n']),
                         'unknown' if g['trial_enrollment_sum'] is None else format(g['trial_enrollment_sum'], ',')]
                        for g in example['result']['geography']] or [['No known-country group.']]
            self.assertEqual(parser.rows, expected, example['id'])

    def test_sweep_coordinates_and_ticks_match_every_record(self):
        for points in (site_sweep(), self.changed_sweep()):
            maximum = max(p['stats'][key]['enrollment_sum'] for p in points for key in ('incorrect', 'corrected'))
            for compact, left, span in ((False, 80, 840), (True, 40, 270)):
                svg = ET.fromstring(sweep_svg(points, compact))
                lines = {n.attrib['data-method']: n for n in svg.iter(NS+'polyline')}
                self.assertEqual(set(lines), {'incorrect', 'corrected'})
                for key, line in lines.items():
                    actual = [[float(v) for v in pair.split(',')] for pair in line.attrib['points'].split()]
                    expected = [[left + i*span/(len(points)-1), 310 - 190*p['stats'][key]['enrollment_sum']/maximum]
                                for i, p in enumerate(points)]
                    self.assertEqual(len(actual), len(expected))
                    for a, b in zip(actual, expected):
                        for av, bv in zip(a, b):
                            self.assertAlmostEqual(av, bv)
                ticks = [n for n in svg.iter(NS+'text') if n.attrib.get('class') == 'sweep-y-tick']
                self.assertEqual([n.text for n in ticks], ['0', format(maximum/2, ',g'), format(maximum, ',')])
                self.assertEqual([float(n.attrib['y']) for n in ticks], [314, 219, 124])
                dots = list(svg.iter(NS+'circle'))
                self.assertEqual(len(dots), 2*len(points))
                for index, key in enumerate(('incorrect', 'corrected')):
                    for i, dot in enumerate(dots[index*len(points):(index+1)*len(points)]):
                        self.assertAlmostEqual(float(dot.attrib['cy']), 310 - 190*points[i]['stats'][key]['enrollment_sum']/maximum)

    @staticmethod
    def changed_sweep():
        points = site_sweep()
        for i, point in enumerate(points):
            point['stats']['incorrect']['enrollment_sum'] = 0 if i == 0 else 800 + 160*i
            point['stats']['corrected']['enrollment_sum'] = 731
            point['stats']['corrected']['trial_count'] = 4
        return points

    def test_sweep_legend_changes_with_values(self):
        for compact in (False, True):
            svg = ET.fromstring(sweep_svg(self.changed_sweep(), compact))
            text = ' '.join(svg.itertext())
            self.assertIn('4 trials', text)
            self.assertIn('identity sum (731)', text)
            self.assertIn('Joined sum 0 to 2,400', text)
            self.assertNotIn('500', text)
            self.assertNotIn('600 to 1600', text)

    def test_flawed_geography_names_its_joined_row_denominator(self):
        result = analyze(review_map_fixture(), None, 'DRUG')
        joined = next(g for g in result['incorrect']['geography'] if g['country'] == 'US')
        identity = next(g for g in result['geography'] if g['country'] == 'US')
        self.assertEqual(joined['known_enrollment_row_n'], 7)
        self.assertNotIn('known_enrollment_n', joined)
        self.assertEqual(identity['known_enrollment_n'], 4)

    def test_filtered_map_scope_is_disclosed(self):
        for example in analyzed_examples():
            html = make_html({'scenarios': [example]})
            self.assertIn('unfiltered calls match the inspected TrialCat bug', html)
            self.assertIn('the historical map ignored that filter', html)

    def test_generated_failure_tags_include_map_disagreements(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = generate(Path(temporary))
        tags = {s['id']: s['category'] for s in report['scenarios']}
        self.assertEqual({key for key, value in tags.items() if value == 'Control example'},
                         {'missing-values', 'country-filter', 'empty-cohort', 'all-missing'})
        self.assertEqual(tags['multinational'], 'Failure example')
        self.assertEqual(tags['review-map'], 'Failure example')
        self.assertEqual(len(tags), 11)
        # Unique rates remove the separate DISTINCT-rate defect, so the map is
        # the only reason this case can be tagged Failure. Otherwise the first
        # discrepancy would mask a disconnected map comparison.
        isolated = next(s for s in scenarios() if s['id'] == 'multinational')
        isolated['data']['trials'][1]['rate'] = 20
        with tempfile.TemporaryDirectory() as temporary:
            with patch('registry_metrics.__main__.scenarios', return_value=[isolated]):
                report = generate(Path(temporary))
        row = report['scenarios'][0]
        for key in ('enrollment_sum', 'rate_n', 'rate_median'):
            self.assertEqual(row['result']['incorrect'][key], row['result']['corrected'][key])
        self.assertEqual(row['category'], 'Failure example')
        isolated['data']['sites'] = [s for s in isolated['data']['sites'] if s['id'] != 'S2']
        with tempfile.TemporaryDirectory() as temporary:
            with patch('registry_metrics.__main__.scenarios', return_value=[isolated]):
                report = generate(Path(temporary))
        self.assertEqual(report['scenarios'][0]['category'], 'Control example')


if __name__ == '__main__':
    unittest.main()
