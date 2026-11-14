"""Exercise published controls and the audit's visual failure reproductions.

Playwright is optional review tooling, not a dependency of the demonstration.
Checks use the saved result rows as the oracle, then inspect geometry and export.
"""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main():
    report = json.loads((ROOT / 'artifacts/results.json').read_text(encoding='utf-8'))
    selectable = [(trace['trace_id'], trace['replay']) for trace in report['traces']]
    selectable.extend((control['trace']['trace_id'], control['replay']) for control in report['controls'] if 'replay' in control and 'trace' in control)
    observations = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        for width, height in ((1440, 1000), (390, 844)):
            page = browser.new_page(viewport={'width': width, 'height': height})
            errors, external = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
            page.on('request', lambda request: external.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
            page.goto((ROOT / 'artifacts/index.html').as_uri(), wait_until='load')
            assert page.locator('#scenario option').count() == len(selectable) == 26
            assert page.locator('#all-traces tr').count() == 24
            assert page.locator('#metrics tr').count() == 3
            initial_timeline = page.locator('#timeline').bounding_box()
            if width == 1440:
                assert initial_timeline['y'] + 100 < height, 'No recorded marks in the first viewport'
            page.screenshot(path=str(ROOT / 'qa' / f'audit-first-view-{width}.png'))
            tested = 0
            for name, replay in selectable:
                page.locator('#scenario').select_option(name)
                for index, row in enumerate(replay['rows']):
                    page.locator('#step').fill(str(index))
                    assert page.locator('#event-id').inner_text() == row['event']['event_id']
                    assert page.locator('#status').inner_text() == row['status'].replace('_', ' ')
                    assert page.locator('#timeline [data-state]').count() == len(replay['rows'])
                    if row['idle_agent_events'] == 1:
                        assert '1 agent event since' in page.locator('#progress-count').inner_text()
                    tested += 1
            # The formerly buried limitation is now adjacent and selectable.
            figure = page.locator('#summary-phone' if width == 390 else '#summary-figure').bounding_box()
            limitation = page.locator('#sparse-limitation').bounding_box()
            # Phone cards retain one paragraph margin; no intervening content
            # separates their final caveat from the selectable limitation.
            assert 0 <= limitation['y'] - (figure['y'] + figure['height']) <= (20 if width == 390 else 2)
            assert page.locator('#summary-phone').evaluate("node => node.nextElementSibling.id") == 'sparse-limitation'
            if width == 390:
                assert page.locator('#summary-phone').is_visible()
                assert not page.locator('#summary-figure').is_visible()
                assert not page.locator('#cadence-figure').is_visible()
                for name, metric in report['metrics'].items():
                    card = page.locator(f'#summary-phone [data-monitor="{name}"]')
                    assert [int(value) for value in card.locator('strong').all_text_contents()] == [metric['tp'], metric['fp']]
                    box = card.bounding_box()
                    assert 0 <= box['x'] and box['x'] + box['width'] <= width
                assert 'conformance by construction' in page.locator('#summary-phone .notice').inner_text()
                assert page.locator('#cadence-phone article').count() == len(report['cadence']['points'])
                for point in report['cadence']['points']:
                    card = page.locator(f'#cadence-phone [data-gap="{point["status_messages"]}"]')
                    for key in ('healthy_alerts', 'stalled_alerts'):
                        row = card.locator(f'[data-series="{key}"]')
                        assert row.get_attribute('data-value') == str(point[key])
                        assert row.locator('strong').inner_text() == str(point[key])
                        box = row.bounding_box()
                        assert 0 <= box['x'] and box['x'] + box['width'] <= width
                page.locator('#summary-phone').screenshot(path=str(ROOT / 'qa' / 'recheck-summary-phone.png'))
                page.locator('#cadence-phone').screenshot(path=str(ROOT / 'qa' / 'recheck-cadence-phone.png'))
            page.locator('#show-limitation').click()
            assert page.locator('#scenario').input_value() == 'sparse-checkpoint'
            assert page.locator('#status').inner_text() == 'alert'
            assert 'outside the matrix' in page.locator('#scenario option:checked').inner_text()
            page.locator('#next').click()
            assert page.locator('#status').inner_text() == 'progress'
            # The independently authored control actually separates text signals.
            page.locator('#scenario').select_option('near-match-text')
            assert page.locator('#exact').inner_text() == 'No repetition alert'
            assert page.locator('#lexical').inner_text().startswith('Repetition alert')
            # Horizontal movement never moves the lane labels with the plot.
            page.locator('#scenario').select_option('trace21')
            labels_before = page.locator('.lane-labels').bounding_box()
            page.locator('#step').fill('7')
            labels_after = page.locator('.lane-labels').bounding_box()
            assert labels_before['x'] == labels_after['x']
            assert labels_after['x'] >= 0 and labels_after['x'] + labels_after['width'] <= width
            assert page.locator('#timeline [data-wait-band]').count() > 0
            assert page.locator('#timeline [data-state="alert"]').count() > 0
            # Native keyboard controls and evidence disclosure remain operable.
            page.locator('#step').focus()
            page.keyboard.press('Home')
            page.keyboard.press('ArrowRight')
            assert page.locator('#step').input_value() == '1'
            page.locator('#next').focus()
            page.keyboard.press('Enter')
            assert page.locator('#step').input_value() == '2'
            page.locator('.details-grid summary').focus()
            page.keyboard.press('Enter')
            assert page.locator('.details-grid details').evaluate('node => node.open')
            with page.expect_download() as pending:
                page.locator('#download-svg').click()
            target = ROOT / 'qa' / f'audit-timeline-{width}.svg'
            pending.value.save_as(target)
            exported = ET.fromstring(target.read_text(encoding='utf-8'))
            exported_text = ' '.join(exported.itertext())
            assert 'Exact text baseline' in exported_text and 'Wait / alert / state' in exported_text
            assert page.locator('#cadence-table tr').count() == 7
            assert '5' == page.locator('#cadence-table tr').nth(3).locator('td').first.inner_text()
            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
            page.locator('#step').fill('5')
            page.locator('.workbench').screenshot(path=str(ROOT / 'qa' / f'audit-replay-{width}.png'))
            page.locator('#conformance').screenshot(path=str(ROOT / 'qa' / f'audit-conformance-{width}.png'))
            observations.append({'width': width, 'page_errors': errors, 'external_requests': external,
                                 'page_overflow': overflow, 'scenarios': len(selectable), 'frames_checked': tested,
                                 'first_timeline_y': initial_timeline['y'], 'fixed_lane_labels': True,
                                 'limitation_gap_px': limitation['y'] - (figure['y'] + figure['height']),
                                 'compact_figures_all_counts_visible': width == 390,
                                 'keyboard_and_svg_export': 'passed'})
            page.close()
        browser.close()
    (ROOT / 'qa/audit-browser-results.json').write_text(json.dumps(observations, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(observations, indent=2))
    assert all(not row['page_errors'] and not row['external_requests'] and not row['page_overflow'] for row in observations)


if __name__ == '__main__':
    main()
