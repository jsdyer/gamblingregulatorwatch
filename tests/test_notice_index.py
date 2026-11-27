import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import parse_qs, urlsplit

from collectors.notice_index import refresh, scan


CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/notice_indexes.json").read_text())
MGA, KGC, ON, MANUAL = [{k: v for k, v in x.items() if k != "review_links"} for x in CONFIG]


def post(i, title, source=KGC, modified="2026-02-10T00:00:00"):
    return {"id": i, "title": {"rendered": title},
            "link": source["index_url"].split("/category")[0].rstrip("/") + f"/notice-{i}/",
            "date": "2026-02-10T12:00:00", "modified_gmt": modified}


def feed(rows, total=None):
    def get(url):
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        n = len(rows) if total is None else total
        return json.dumps(rows[(page - 1) * 100:page * 100]).encode(), {
            "X-WP-TotalPages": str((n + 99) // 100), "X-WP-Total": str(n)}
    return get


def card(number, title):
    return (f'<div><span data-component-id="agco:badge">Lottery and Gaming</span>'
            f'<h5><a href="/en/news/story-{number}">{title}</a></h5>'
            '<time datetime="2026-03-15T12:00:00Z">March 15</time></div>')


def sector(cards, following=False, last=False):
    links = '<a href="?page=1" rel="next">Next</a>' if following else ''
    if last:
        links += '<li class="pager__item--last"><a href="?page=1">Last</a></li>'
    return f'<main class="view-id-search_news"><div class="view-content">{"".join(cards)}</div>{links}</main>'.encode(), {}


class NoticeIndex(unittest.TestCase):
    def test_mga_uses_printed_notice_date_and_retains_unique_publications(self):
        rows = [post(1, "13/11/2015 – Cancellation for A &amp; B", MGA),
                post(2, "13/11/2015 – Cancellation for A &amp; B", MGA),
                post(3, "Suspension for a holder", MGA)]
        selected, size = scan(MGA, feed(rows))
        self.assertEqual(size, 3)
        self.assertEqual([r["published_on"] for r in selected], ["2015-11-13", "2015-11-13", None])
        self.assertIn("A & B", selected[0]["title"])
        self.assertNotEqual(selected[0]["url"], selected[1]["url"])

    def test_kahnawake_filters_category_and_rejects_duplicate_or_partial_pages(self):
        rows = [post(i, "Suspension announced" if i == 100 else "Commission appoints member")
                for i in range(101)]
        def get(url):
            self.assertEqual(parse_qs(urlsplit(url).query)["categories"], ["4"])
            return feed(rows)(url)
        selected, size = scan(KGC, get)
        self.assertEqual((len(selected), size), (1, 101))
        for bad in (feed(rows[:100], total=101), feed(rows + [rows[0]]),
                    feed([{**rows[0], "link": "https://another.example/bad"}])):
            with self.assertRaises(ValueError):
                scan(KGC, bad)

    def test_ontario_follows_every_page_and_includes_settlement_articles(self):
        first = sector([card(1, "AGCO moves to suspend a lottery seller"),
                        card(2, "AGCO issues a penalty to Operator")], following=True, last=True)
        second = sector([card(3, "AGCO and Operator reach settlement")])
        get = lambda url: second if urlsplit(url).query else first
        selected, size = scan(ON, get)
        self.assertEqual(size, 3)
        self.assertEqual([r["url"].rsplit("/", 1)[1] for r in selected], ["story-2", "story-3"])
        for malformed in (sector([card(4, "Penalty")], last=True), (b"<article>No cards</article>", {})):
            with self.assertRaises(ValueError):
                scan(ON, lambda _: malformed)

    def test_baseline_new_changed_rolloff_and_reviewed_url_only(self):
        one, two = post(1, "A – SUSPENSION"), post(2, "A – SUSPENSION")
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "kahnawake.json").write_text(json.dumps({"actions": [{"id": "case-1", "url": one["link"]}]}))
            start = refresh([KGC, MANUAL], {}, folder, "2026-03-01", feed([one]))
            first, = start["notices"]
            self.assertFalse(first["is_new"])
            self.assertTrue(first["reviewed"])
            self.assertEqual(start["sources"][1]["availability"], "manual")
            week = refresh([KGC], start, folder, "2026-03-08", feed([one, two]))
            new = next(r for r in week["notices"] if r["url"] == two["link"])
            self.assertTrue(new["is_new"])
            self.assertFalse(new["reviewed"])
            self.assertNotIn("eligible", new)
            next_week = refresh([KGC], week, folder, "2026-03-15",
                                feed([{**one,"modified_gmt": "2026-03-14T00:00:00"}]))
            changed = next(r for r in next_week["notices"] if r["listed"])
            previous = next(r for r in next_week["notices"] if not r["listed"])
            self.assertTrue(changed["is_updated"])
            self.assertEqual(changed["first_seen"], "2026-03-01")
            self.assertEqual(previous["last_seen"], "2026-03-08")
            self.assertFalse(previous["is_new"])

    def test_failed_source_preserves_others_and_last_good_then_recovers(self):
        rows = [post(1, "Suspension of holder")]
        other = {**KGC, "regulator": "additional"}
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ("kahnawake", "additional"):
                (folder / f"{name}.json").write_text('{"actions":[]}')
            initial = refresh([KGC, other], {}, folder, "2026-03-01", feed(rows))
            def get(url):
                if "bad" in url:
                    raise OSError("offline")
                return feed([*rows, post(2, "Termination of holder")])(url)
            state = refresh([{**KGC, "endpoint": KGC["endpoint"] + "-bad"}, other], initial,
                            folder, "2026-03-08", get)
            failed, success = state["sources"]
            self.assertEqual((failed["availability"], failed["last_success_at"]), ("unavailable", "2026-03-01"))
            self.assertEqual(success["listed_count"], 2)
            self.assertEqual([r for r in state["notices"] if r["regulator"] == "kahnawake"],
                             [r for r in initial["notices"] if r["regulator"] == "kahnawake"])
            recovered = refresh([KGC], state, folder, "2026-03-15", get)
            self.assertEqual(recovered["sources"][0]["availability"], "available")
            self.assertEqual(sum(r["is_new"] for r in recovered["notices"]), 1)


if __name__ == "__main__":
    unittest.main()
