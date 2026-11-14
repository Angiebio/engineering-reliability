"""Independent numerical and graphical contracts added after the Claude audit."""
from copy import deepcopy
import json
import random
import re
import unittest
import xml.etree.ElementTree as ET

from registry_metrics.core import analyze, MAX_RECORDS, MAX_VALUE
from registry_metrics.fixtures import base, scenarios, review_map_fixture
from registry_metrics.report import comparisons_svg, provenance_svg, geography_svg, display, make_html
from registry_metrics.__main__ import site_sweep

NS = '{http://www.w3.org/2000/svg}'


def scenario():
    value = scenarios()[0]
    value['result'] = analyze(value['data'])
    return value


def geography_oracle(data, country, kind, flawed=False):
    """Construct full expected groups from list membership, never SQL/helpers."""
    groups = {}
    for trial in data['trials']:
        sites = [s for s in data['sites'] if s['trial_id'] == trial['id'] and s['country'] is not None
                 and (country is None or s['country'] == country)]
        kinds = [i for i in data['interventions'] if i['trial_id'] == trial['id'] and i['kind'] == kind] if kind else [None]
        if not kinds:
            continue
        if flawed:
            contributions = [s['country'] for s in sites for _ in kinds]
        else:
            contributions = sorted({s['country'] for s in sites})
        for key in contributions:
            groups.setdefault(key, []).append(trial)
    result = []
    for key, trials in sorted(groups.items()):
        values = [t['enrollment'] for t in trials if t['enrollment'] is not None]
        result.append({'country': key, 'trial_count': len({t['id'] for t in trials}),
                       ('known_enrollment_row_n' if flawed else 'known_enrollment_n'): len(values), 'trial_enrollment_sum': sum(values) if values else None})
    return result


class ReviewTests(unittest.TestCase):
    def test_always_joined_geography(self):
        data = next(s['data'] for s in scenarios() if s['id'] == 'multinational')
        result = analyze(data, None)
        self.assertEqual(result['incorrect']['enrollment_sum'], 500)
        self.assertEqual(result['incorrect']['geography'], geography_oracle(data, None, None, True))
        self.assertEqual(result['incorrect']['geography'][1]['trial_enrollment_sum'], 600)
        self.assertEqual(result['geography'][1]['trial_enrollment_sum'], 500)

    def test_review_map_fixture(self):
        for kind, expected_us, expected_ca in [(None, 670, 100), ('DRUG', 870, 200)]:
            value = analyze(review_map_fixture(), None, kind)
            wrong = {g['country']: g['trial_enrollment_sum'] for g in value['incorrect']['geography']}
            right = {g['country']: g['trial_enrollment_sum'] for g in value['geography']}
            self.assertEqual(wrong['US'], expected_us)
            self.assertEqual(wrong['CA'], expected_ca)
            self.assertEqual(right, {'CA': 100, 'DE': 100, 'US': 570})

    def test_full_geography_lists_match_seeded_independent_oracle(self):
        rng = random.Random(73129)
        for batch in range(100):
            data = {'trials': [], 'sites': [], 'interventions': []}
            for i in range(rng.randrange(1, 8)):
                key = f'T{i}'
                data['trials'].append({'id': key, 'enrollment': rng.choice([None, 0, 10, 10, 30]), 'rate': rng.choice([None, 0, 10, 30])})
                for j in range(rng.randrange(4)):
                    data['sites'].append({'id': f'S{i}_{j}', 'trial_id': key, 'country': rng.choice([None, 'US', 'CA'])})
                for j in range(rng.randrange(4)):
                    data['interventions'].append({'id': f'I{i}_{j}', 'trial_id': key, 'kind': rng.choice(['DRUG', 'DEVICE'])})
            for country in (None, 'US', 'CA'):
                for kind in (None, 'DRUG', 'DEVICE'):
                    result = analyze(data, country, kind)
                    self.assertEqual(result['geography'], geography_oracle(data, country, kind))
                    self.assertEqual(result['incorrect']['geography'], geography_oracle(data, country, kind, True))

    def test_geography_known_count_and_null_zero(self):
        missing = next(s['data'] for s in scenarios() if s['id'] == 'missing-values')
        self.assertEqual(analyze(missing)['geography'], [{'country': 'US', 'trial_count': 3, 'known_enrollment_n': 2, 'trial_enrollment_sum': 400}])
        data = base()
        for trial in data['trials']:
            trial['enrollment'] = None
        data['trials'][0]['enrollment'] = 0
        group = analyze(data)['geography'][0]
        self.assertEqual(group['trial_enrollment_sum'], 0)
        self.assertEqual(group['known_enrollment_n'], 1)

    def test_record_and_value_bounds(self):
        data = base()
        data['trials'][0]['enrollment'] = MAX_VALUE + 1
        with self.assertRaises(ValueError):
            analyze(data)
        data = base()
        data['sites'] = [{'id': f'S{i}', 'trial_id': 'T1', 'country': 'US'} for i in range(MAX_RECORDS + 1)]
        with self.assertRaises(ValueError):
            analyze(data)

    def test_site_sweep_reexecutes_sql_and_records_geography(self):
        points = site_sweep()
        self.assertEqual(len(points), 11)
        for extra, point in enumerate(points):
            self.assertEqual(point['stats'], analyze(point['data'], 'US'))
            self.assertEqual(point['world'], analyze(point['data'], None))
            self.assertEqual(point['stats']['incorrect']['enrollment_sum'], 600 + extra * 100)
            self.assertEqual(point['stats']['corrected']['enrollment_sum'], 500)
            geography = {g['country']: g['trial_enrollment_sum'] for g in point['world']['incorrect']['geography']}
            self.assertEqual(geography, {'CA': 100, 'US': 600 + extra * 100})

    def test_exact_integer_display(self):
        for value in (0, 1, 9, 11, 12_345_641, 12_345_642, 12_345_649):
            self.assertEqual(display(value), format(value, ','))
        self.assertEqual(display(12_345_640), '12,345,640')
        self.assertEqual(display(12_345_600), '12,345,600')
        self.assertEqual(display(2_000_000_000), '2,000,000,000')
        self.assertEqual(display(1.23456789012345), '1.23456789012345')
        value = scenario()
        value['result']['incorrect']['enrollment_sum'] = 12_345_640
        value['result']['corrected']['enrollment_sum'] = 12_345_600
        html = make_html({'scenarios': [value]})
        self.assertIn('12,345,640', html)
        self.assertIn('12,345,600', html)

    def test_headline_uses_first_record(self):
        value = scenario()
        value['result']['incorrect']['enrollment_sum'] = 700
        value['result']['corrected']['enrollment_sum'] = 550
        html = make_html({'scenarios': [value]})
        headline = re.search(r'<p class="hero-result">([^<]+)</p>', html).group(1)
        self.assertIn('joined total 700', headline)
        self.assertIn('identity-correct total 550', headline)

    def test_bar_geometry_and_labels(self):
        for compact, origin, span in ((False, 210, 550), (True, 20, 270)):
            with self.subTest(compact=compact):
                root = ET.fromstring(comparisons_svg(scenario(), compact))
                bars = {n.attrib['data-method']: n for n in root.iter(NS+'rect') if n.attrib.get('class') == 'enrollment-bar'}
                labels = {n.attrib['data-method']: n.text for n in root.iter(NS+'text') if n.attrib.get('class') == 'bar-label'}
                self.assertEqual(labels, {'incorrect': 'Joined-row sum', 'corrected': 'Trial-identity sum'})
                self.assertEqual({float(n.attrib['x']) for n in bars.values()}, {float(origin)})
                self.assertAlmostEqual(float(bars['incorrect'].attrib['width']) / float(bars['corrected'].attrib['width']), 600/500)
                self.assertEqual(float(bars['incorrect'].attrib['width']), span)

    def test_provenance_edges_and_duplicate_marker(self):
        value = scenario()
        root = ET.fromstring(provenance_svg(value))
        starts = {g.attrib['data-trial']: float(g.find(NS+'rect').attrib['y']) + 24
                  for g in root.iter(NS+'g') if g.attrib.get('class') == 'trial-node'}
        paths = [p for p in root.iter(NS+'path') if p.attrib.get('class') == 'source-edge']
        self.assertEqual(len(paths), 4)
        for path in paths:
            start = re.match(r'M260 ([\d.]+)', path.attrib['d'])
            self.assertEqual(float(start.group(1)), starts[path.attrib['data-trial']])
        joined = [g for g in root.iter(NS+'g') if g.attrib.get('class') == 'joined-node']
        self.assertEqual(sum('duplicate trial' in ''.join(g.itertext()) for g in joined), 1)
        self.assertTrue(all('US' in ''.join(g.itertext()) for g in joined))
        ends = {g.attrib['data-trial']: float(g.find(NS+'rect').attrib['y']) + 24
                for g in root.iter(NS+'g') if g.attrib.get('class') == 'cohort-node'}
        right = [p for p in root.iter(NS+'path') if p.attrib.get('d', '').startswith('M620 ')]
        self.assertEqual(len(right), len(value['result']['joined_rows']))
        seen = set()
        for index, row in enumerate(value['result']['joined_rows']):
            with self.subTest(row=index):
                numbers = [float(n) for n in re.findall(r'[\d.]+', right[index].attrib['d'])]
                self.assertEqual(numbers, [620, 155 + 76*index, 680, 155 + 76*index, 700, ends[row['id']], 760, ends[row['id']]])
                self.assertEqual(paths[index].attrib['stroke'], '#a74b32' if row['id'] in seen else '#688477')
                self.assertEqual(joined[index].find(NS+'rect').attrib['fill'], '#f8e9df' if row['id'] in seen else '#edf1eb')
                seen.add(row['id'])

    def test_compact_comparison_keeps_all_marks_in_view(self):
        root = ET.fromstring(comparisons_svg(scenario(), compact=True))
        viewport = float(root.attrib['viewBox'].split()[2])
        bars = [n for n in root.iter(NS+'rect') if n.attrib.get('class') == 'enrollment-bar']
        self.assertGreater(float(bars[0].attrib['width']), float(bars[1].attrib['width']))
        for bar in bars:
            self.assertLessEqual(float(bar.attrib['x']) + float(bar.attrib['width']), viewport)
        labels = [n for n in root.iter(NS+'text') if n.attrib.get('class') == 'bar-value']
        self.assertEqual([n.text for n in labels], ['600', '500'])
        for label in labels:
            self.assertGreaterEqual(float(label.attrib['x']), 0)
            self.assertLess(float(label.attrib['x']), viewport)
        dots = list(root.iter(NS+'circle'))
        self.assertEqual(len(dots), 5)
        for dot in dots:
            self.assertLessEqual(float(dot.attrib['cx']) + float(dot.attrib['r']), viewport)
            self.assertGreaterEqual(float(dot.attrib['cx']) - float(dot.attrib['r']), 0)

    def test_dot_lane_boundaries(self):
        value = scenario()
        for count in (2, 30, 1000):
            value['result']['corrected']['rate_values'] = [10] * count
            for compact in (False, True):
                root = ET.fromstring(comparisons_svg(value, compact))
                for lane in [g for g in root.iter(NS+'g') if g.attrib.get('class') == 'rate-lane']:
                    top, bottom = float(lane.attrib['data-top']), float(lane.attrib['data-bottom'])
                    for dot in lane.iter(NS+'circle'):
                        y, r = float(dot.attrib['cy']), float(dot.attrib['r'])
                        self.assertGreaterEqual(y-r, top)
                        self.assertLessEqual(y+r, bottom)

    def test_median_markers_use_actual_medians(self):
        value = scenario()
        for trial, rate in zip(value['data']['trials'], (5, 11, 25)):
            trial['rate'] = rate
        value['result'] = analyze(value['data'])
        for compact, origin, span in ((False, 220, 550), (True, 30, 270)):
            root = ET.fromstring(comparisons_svg(value, compact))
            for lane in [g for g in root.iter(NS+'g') if g.attrib.get('class') == 'rate-lane']:
                marker = next(p for p in lane.iter(NS+'path') if p.attrib.get('class') == 'median-marker')
                actual = float(re.match(r'M([\d.]+)', marker.attrib['d']).group(1))
                self.assertAlmostEqual(actual, origin + span * 11 / 30)

    def test_downloaded_figures_carry_scenario_filters_and_grain(self):
        value = next(s for s in scenarios() if s['id'] == 'country-filter')
        value['result'] = analyze(value['data'], value['country'])
        for render in (provenance_svg, comparisons_svg, geography_svg):
            root = ET.fromstring(render(value))
            visible = ' '.join(n.text or '' for n in root.iter(NS+'text'))
            self.assertIn('country=CA', visible)
            self.assertIn('1 trial;', visible)
            self.assertIn('invented, trial-wide', visible)

    def test_geographic_header_uses_country_group_denominator(self):
        value = next(s for s in scenarios() if s['id'] == 'review-map')
        value['result'] = analyze(value['data'], None)
        root = ET.fromstring(geography_svg(value))
        visible = ' '.join(n.text or '' for n in root.iter(NS+'text'))
        self.assertIn('3 country groups; map always joins sites', visible)
        self.assertNotIn('6 query rows', visible)

    def test_empty_is_distinct_from_all_missing(self):
        values = []
        for name in ('empty-cohort', 'all-missing'):
            value = next(s for s in scenarios() if s['id'] == name)
            value['result'] = analyze(value['data'], value['country'])
            values.append(value)
        self.assertIn('no trials (n=0)', comparisons_svg(values[0]))
        self.assertNotIn('no trials (n=0)', comparisons_svg(values[1]))
        self.assertIn('unknown', comparisons_svg(values[1]))


if __name__ == '__main__':
    unittest.main()
