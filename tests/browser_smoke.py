"""Exercise the published operator directory and filtered records at a project subpath."""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import tempfile
import threading
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SLUG = "gamblingregulatorwatch"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    dist = ROOT / "dist"
    edition = json.loads((dist / "data/edition.json").read_text(encoding="utf-8"))
    operators = edition["operators"]
    regulators = edition["regulators"]
    assert operators and regulators
    person = next((item for item in operators if item["actions"] and item["licences"]), operators[0])
    with tempfile.TemporaryDirectory() as temp:
        (Path(temp) / SLUG).symlink_to(dist, target_is_directory=True)
        handler = partial(QuietHandler, directory=temp)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/{SLUG}/"
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"))
                for width, height, name in [(1280, 900, "desktop"), (390, 844, "mobile")]:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(url)
                    expect(page.locator("#operator-workspace")).to_be_visible()
                    feature = page.locator(".featured-record")
                    expect(feature).to_contain_text(re.compile(r"(?<!\d)20\d{2}(?!\d)"))
                    assert feature.locator("a").count() > 0
                    first_link = feature.locator("a").first.bounding_box()
                    assert first_link["y"] + first_link["height"] <= height
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    screenshots = ROOT / "browser-checks"
                    screenshots.mkdir(exist_ok=True)
                    page.screenshot(path=str(screenshots / f"{name}.png"), full_page=True)

                    query = page.get_by_role("searchbox", name="Operator or regulator")
                    query.fill(person["name"])
                    row = page.locator("#operator-list article").filter(has=page.get_by_role("link", name=person["name"], exact=True)).first
                    expect(row).to_be_visible()
                    row.get_by_role("button").click()
                    expect(page.locator("#operator-preview h3")).to_have_text(person["name"])
                    expect(page).to_have_url(re.compile(r"[?&]operator="))
                    permalink = page.url
                    expect(page.locator("#operator-preview a.profile")).to_have_attribute("href", f"./records/{person['slug']}/")
                    page.reload()
                    expect(page.locator("#operator-preview h3")).to_have_text(person["name"])
                    expect(page).to_have_url(permalink)
                    assert (dist / "records" / person["slug"] / "index.html").is_file()
                    page.locator("#operator-preview button").click()

                    alias_case = next(((op, licence["name"]) for op in operators for licence in op["licences"]
                                       if licence.get("name") and licence["name"].casefold() != op["name"].casefold()), None)
                    if alias_case:
                        legal, alias = alias_case
                        query.fill(alias)
                        named = page.locator("#operator-list article").filter(has=page.get_by_role("link", name=legal["name"], exact=True))
                        expect(named.first).to_contain_text(alias)
                    query.fill("unmatched search -- 987654321")
                    expect(page.locator("#operator-list")).to_contain_text("No operator")
                    expect(page.locator("#export")).to_be_disabled()
                    page.locator("#reset").click()
                    expect(page.locator("#export")).to_be_enabled()
                    with page.expect_download() as downloading:
                        page.locator("#export").click()
                    assert downloading.value.suggested_filename.endswith(".csv")
                    query.fill(regulators[0]["name"])
                    expect(page.locator("#regulator-matches")).to_contain_text(regulators[0]["name"])
                    assert page.locator("#regulator-matches a").count() > 0
                    page.locator("#compare-a").select_option(regulators[-1]["id"])
                    expect(page.locator("#comparison thead th").nth(1)).to_have_text(regulators[-1]["name"])
                    if len(regulators) > 1:
                        assert page.locator("#compare-a").input_value() != page.locator("#compare-b").input_value()
                    expect(page.locator("#comparison")).to_contain_text("Distinct eligible cases")
                    assert not errors, errors
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print("Verified first use, exact entity, source links, deep link, filters, export and regulator comparison at desktop and phone widths.")


if __name__ == "__main__":
    main()
