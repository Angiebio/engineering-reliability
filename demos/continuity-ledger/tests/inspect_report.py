"""Optional local browser QA; requires Playwright outside runtime dependencies."""

import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
qa = root / "qa"
qa.mkdir(exist_ok=True)
results = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    for width, height in ((1440, 1100), (390, 844)):
        page = browser.new_page(viewport={"width": width, "height": height})
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto((root / "artifacts" / "index.html").as_uri())
        page.select_option("#strategy", "timeline")
        assert page.locator("article.case:visible").count() == 24
        page.locator("article.case:visible summary").first.click()
        assert page.locator("article.case:visible details").first.get_attribute("open") is not None
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not failures, failures
        page.screenshot(path=str(qa / f"report-{width}.png"), full_page=False)
        results.append({"width": width, "height": height, "visible_filtered_cases": 24,
                        "details_expands": True, "horizontal_overflow": False, "page_errors": failures})
        page.close()
    browser.close()
(qa / "browser-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
