"""Inspect actual mobile geometry and history restoration, not just DOM counts."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent

if __name__ == '__main__':
    (ROOT / 'qa').mkdir(exist_ok=True)
    records = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        for width, height in ((1440, 1000), (390, 844)):
            page = browser.new_page(viewport={'width': width, 'height': height})
            errors, network = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('request', lambda request: network.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
            page.goto((ROOT / 'artifacts/index.html').as_uri())
            assert page.locator('.hero-result').bounding_box()['y'] < height
            picker = page.locator('#scenario-picker')
            options = picker.locator('option').evaluate_all('(nodes)=>nodes.map(n=>n.value)')
            assert len(options) == 11
            for value in options:
                picker.select_option(value)
                assert page.locator('.scenario:visible').count() == 1
                panel = page.locator('.scenario:visible')
                assert panel.get_attribute('id') == value
                panel.locator('summary').click()
                assert panel.locator('details').evaluate('(node)=>node.open')
                assert panel.locator('.quantitative:visible').count() == 2
            picker.select_option('join-inflation')
            comparison = page.locator('#join-inflation [data-figure=comparison]:visible')
            comparison.scroll_into_view_if_needed()
            bounds = comparison.bounding_box()
            bars = comparison.locator('.enrollment-bar').all()
            boxes = [bar.bounding_box() for bar in bars]
            assert boxes[0]['width'] > boxes[1]['width']
            assert abs(boxes[0]['width']/boxes[1]['width'] - 1.2) < .001
            quantitative_nodes = comparison.locator('.enrollment-bar,.bar-value,.rate-observation').all()
            for node in quantitative_nodes:
                box = node.bounding_box()
                assert box['x'] >= bounds['x'] - 1
                assert box['x'] + box['width'] <= bounds['x'] + bounds['width'] + 1
                assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1
            assert comparison.locator('.rate-observation').count() == 5
            comparison.screenshot(path=str(ROOT / 'qa' / f'audit-comparison-{width}.png'))
            # A history-restored select must be reconciled with the rendered panel.
            picker.select_option('multinational')
            page.locator('a[href="results.json"]').click()
            page.go_back()
            picker = page.locator('#scenario-picker')
            assert page.locator('.scenario:visible').get_attribute('id') == picker.input_value()
            picker.select_option('review-map')
            page.locator('#review-map [data-figure=geography]:visible').screenshot(path=str(ROOT / 'qa' / f'audit-map-{width}.png'))
            for extra in range(11):
                page.locator('#site-dial').fill(str(extra))
                assert format(600 + 100*extra, ',') in page.locator('#site-readout').inner_text()
                assert 'identity 500' in page.locator('#site-readout').inner_text()
                assert 'CA joined 100 vs identity 100' in page.locator('#map-readout').inner_text()
                assert f'US joined {format(600 + 100*extra, ",")} vs identity 500' in page.locator('#map-readout').inner_text()
            page.locator('#sweep').screenshot(path=str(ROOT / 'qa' / f'audit-sweep-{width}.png'))
            picker.select_option('join-inflation')
            picker.focus()
            page.keyboard.press('ArrowDown')
            assert page.locator('.scenario:visible').get_attribute('id') == picker.input_value()
            picker.select_option('join-inflation')
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(ROOT / 'qa' / f'audit-first-view-{width}.png'))
            ids = page.locator('[id]').evaluate_all('(nodes)=>nodes.map(n=>n.id)')
            assert len(ids) == len(set(ids))
            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth + 1')
            records.append({'width': width, 'scenarios_verified': len(options), 'errors': errors,
                            'external_requests': network, 'page_overflow': overflow,
                            'bars_and_labels_within_view': True, 'bar_width_ratio': boxes[0]['width']/boxes[1]['width'],
                            'visible_rate_dots': 5, 'back_navigation_synced': True, 'site_dial_positions': list(range(11))})
            assert not errors and not network and not overflow
            page.close()
        browser.close()
    (ROOT / 'qa/audit-browser-results.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(records, indent=2))
