"""Optional Playwright verification of every recorded lifecycle visual."""
import json
from pathlib import Path
import sys
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from promotion_gate.visuals import visual_payload

output = root / 'qa'
output.mkdir(exist_ok=True)
records = json.loads((root / 'artifacts/results.json').read_text(encoding='utf-8'))
cases = visual_payload(records)['cases']
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
        for index, case in enumerate(cases):
            page.select_option('#pv-case', str(index))
            for step, frame in enumerate(case['frames']):
                page.locator('#pv-step').fill(str(step))
                assert page.locator('#pv-serving').inner_text() == frame['serving']
                assert page.locator('#pv-revision').inner_text() == str(frame['revision'])
                assert frame['candidate_state'] in page.locator('#pv-diagram title').text_content()
                checked += 1
        lifecycle = next(i for i, item in enumerate(cases) if item['reason'] == 'rollback_restored')
        page.select_option('#pv-case', str(lifecycle))
        assert page.locator('#pv-step').input_value() == '0'
        page.locator('#pv-step').fill('3')
        assert page.locator('#pv-serving').inner_text() == 'candidate'
        assert page.locator('#pv-reason').inner_text() == 'rollback_restored'
        assert page.locator('#pv-reason').locator('..').locator('dt').inner_text() == 'Scenario final outcome'
        assert page.locator('#pv-category').locator('..').locator('dt').inner_text() == 'Final outcome category'
        page.locator('#pv-step').focus()
        page.keyboard.press('ArrowRight')
        assert page.locator('#pv-serving').inner_text() == 'baseline'
        assert 'rolled_back' in page.locator('#pv-diagram title').text_content()
        page.locator('#pv-next').focus()
        page.keyboard.press('Enter')
        assert page.locator('#pv-next').evaluate('(node) => node === document.activeElement')
        assert page.locator('#pv-next').get_attribute('aria-disabled') == 'true'
        page.locator('#pv-step').fill('0')
        page.locator('#pv-prev').focus()
        page.keyboard.press('Enter')
        assert page.locator('#pv-prev').evaluate('(node) => node === document.activeElement')
        rejected = next(i for i, item in enumerate(cases) if item['reason'] == 'canary_failed')
        page.select_option('#pv-case', str(rejected))
        page.locator('#pv-step').fill('1')
        assert page.locator('#pv-checks .stopped').inner_text().endswith('canary_failed')
        assert page.locator('#pv-serving').inner_text() == 'baseline'
        assert page.locator('#promotion-visual').inner_text().find('no canary test was executed') >= 0
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors and not network
        page.locator('#promotion-visual').screenshot(path=str(output / f'audit-explorer-{width}.png'))
        observations.append({'width': width, 'recorded_frames_checked': checked,
                             'keyboard_step_change': True, 'rollback_replay': True,
                             'final_scenario_outcome_labels_explicit': True, 'boundary_button_focus_retained': True, 'starts_at_initial_frame': True, 'recorded_denial_checks': True,
                             'page_errors': errors, 'external_requests': network, 'page_overflow': False})
        page.close()
    browser.close()
(output / 'audit-browser-results.json').write_text(json.dumps(observations, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(observations, indent=2))
