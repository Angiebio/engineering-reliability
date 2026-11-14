"""Optional Playwright verification of the data-driven visual explorer."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
output = root / 'qa'
output.mkdir(exist_ok=True)
report = json.loads((root / 'artifacts/results.json').read_text(encoding='utf-8'))
records = report['rows'] + report['natural_rows']
observations = []
with sync_playwright() as runtime:
    browser = runtime.chromium.launch(headless=True)
    for width, height in ((1440, 1000), (390, 844)):
        page = browser.new_page(viewport={'width': width, 'height': height})
        errors, network = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda req: network.append(req.url) if req.url.startswith(('https:', 'http:')) else None)
        page.goto((root / 'artifacts/index.html').as_uri())
        checked = 0
        for row in records:
            page.select_option('#cv-case', row['case_id'])
            page.select_option('#cv-arm', row['strategy'])
            assert page.locator('#cv-proposal').inner_text() == row['proposal']['action']
            assert page.locator('#cv-decision').inner_text() == row['gate']['action']
            assert page.locator('#cv-current').inner_text().endswith(row['gate']['current_evidence_id'])
            assert str(row['memory']['used_bytes']) in page.locator('#cv-budget').inner_text()
            expected = ('correct_resume' if row['expected'] == 'active' else 'unsafe_allowed') if row['gate']['action'] == 'resume' else ('missed_eligible' if row['expected'] == 'active' else 'unsafe_caught' if row['proposal']['action'] == 'resume' else 'correct_hold')
            assert page.locator('#cv-verdict').get_attribute('data-verdict') == expected
            assert row['expected'] in page.locator('#cv-expected').inner_text()
            checked += 1
        for index, point in enumerate(report['sweep']['points']):
            page.locator('#budget-dial').evaluate('(node,value)=>{node.value=value;node.dispatchEvent(new Event("input"));}', index)
            assert str(point['budget_bytes']) in page.locator('#budget-value').inner_text()
            for strategy, values in point['strategies'].items():
                shown = page.locator(f'#budget-readout [data-strategy="{strategy}"]').inner_text()
                assert f"{values['eligible_resumed']}/{values['eligible_count']} eligible tasks resumed" in shown
                assert f"{values['unsafe_proposals']}/{values['ineligible_count']} before gate" in shown
        page.select_option('#cv-case', 'case03')
        page.select_option('#cv-arm', 'raw_tail')
        assert page.locator('#cv-proposal').inner_text() == 'abstain'
        assert page.locator('#cv-verdict').get_attribute('data-verdict') == 'missed_eligible'
        page.locator('#cv-arm').focus()
        page.keyboard.press('ArrowDown')
        assert page.locator('#cv-proposal').inner_text() == 'resume'
        page.locator('.cv-source summary').click()
        assert page.locator('#cv-sources li').count() > 0
        page.select_option('#cv-case', 'natural-case14')
        page.select_option('#cv-arm', 'raw_tail')
        assert page.locator('#cv-verdict').get_attribute('data-verdict') == 'unsafe_caught'
        text_size = page.locator('#cv-timeline text').nth(1).evaluate('(node)=>parseFloat(getComputedStyle(node).fontSize)*node.ownerSVGElement.getBoundingClientRect().width/node.ownerSVGElement.viewBox.baseVal.width')
        assert text_size >= 14
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors and not network
        page.locator('.cv-source summary').click()
        page.locator('#continuity-visual').screenshot(path=str(output / f'review-explorer-{width}.png'))
        page.locator('#budget-dial').evaluate('(node,value)=>{node.value=value;node.dispatchEvent(new Event("input"));}', next(i for i,p in enumerate(report['sweep']['points']) if p['budget_bytes'] == 640))
        if width == 390:
            assert not page.locator('.budget-chart').is_visible()
            assert page.locator('.budget-mobile-steps').is_visible()
            expected_brackets = [(a['budget_bytes'], b['budget_bytes'],
                                  a['strategies']['raw_tail']['eligible_resumed'], b['strategies']['raw_tail']['eligible_resumed'])
                                 for a, b in zip(report['sweep']['points'], report['sweep']['points'][1:])
                                 if a['strategies']['raw_tail']['eligible_resumed'] != b['strategies']['raw_tail']['eligible_resumed']]
            assert page.locator('.budget-mobile-steps li').count() == len(expected_brackets)
            for left, right, before, after in expected_brackets:
                card = page.locator(f'.budget-mobile-steps [data-left="{left}"][data-right="{right}"]')
                assert f'{before} → {after} eligible resumptions' in card.inner_text()
                assert card.evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)') >= 14
            assert page.locator('.budget-scope').evaluate('(n)=>parseFloat(getComputedStyle(n).fontSize)') >= 14
        page.locator('#budget-explorer').screenshot(path=str(output / f'review-budget-{width}.png'))
        observations.append({'width': width, 'recorded_outcomes_checked': checked,
                             'budget_points_checked': len(report['sweep']['points']), 'minimum_timeline_label_px': text_size,
                             'keyboard_strategy_change': True, 'source_text_expands': True,
                             'phone_budget_cards_and_readable_scope': width == 390,
                             'page_errors': errors, 'external_requests': network, 'page_overflow': False})
        page.close()
    browser.close()
(output / 'review-browser-results.json').write_text(json.dumps(observations, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(observations, indent=2))
