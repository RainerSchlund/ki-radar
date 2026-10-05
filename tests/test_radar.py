import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "radar"))
from archive import Archive, norm_url  # noqa: E402
from curate import curate, extract_json  # noqa: E402
from fetch_github import parse_trending  # noqa: E402
from fetch_reddit import parse_feed  # noqa: E402
import fetch_news  # noqa: E402

TRENDING = """<article class="Box-row"><h2 class="h3 lh-condensed">
<a data-view-component="true" href="/acme/mem-agent" class="Link">acme / mem-agent</a></h2>
<p class="col-9 color-fg-muted my-1 pr-4">Long-term memory for &amp; agents</p>
<span itemprop="programmingLanguage">Python</span>
<span class="d-inline-block float-sm-right">1,234 stars today</span></article>"""

FEED = """<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><author><name>/u/alice</name></author><category term="ClaudeAI" label="r/ClaudeAI"/>
<content type="html">&lt;div&gt;My take on agents&lt;/div&gt; submitted by &lt;a href="x"&gt;/u/alice&lt;/a&gt;
&lt;span&gt;&lt;a href="https://simonwillison.net/2026/Oct/3/agents/"&gt;[link]&lt;/a&gt;&lt;/span&gt;</content>
<id>t3_abc</id><link href="https://www.reddit.com/r/ClaudeAI/comments/abc/x/"/>
<published>2026-10-03T10:00:00+00:00</published><title>Agents essay</title></entry>
<entry><id>t5_sub</id><title>subreddit meta</title></entry></feed>"""


class ParseTest(unittest.TestCase):
    def test_trending(self):
        r = parse_trending(TRENDING)
        self.assertEqual(r[0]["full_name"], "acme/mem-agent")
        self.assertEqual(r[0]["stars_today"], 1234)
        self.assertEqual(r[0]["description"], "Long-term memory for & agents")
        self.assertEqual(r[0]["language"], "Python")

    def test_feed(self):
        p = parse_feed(FEED, "r/ClaudeAI")
        self.assertEqual(len(p), 1)  # t5_-Eintrag ist kein Beitrag
        self.assertEqual(p[0]["id"], "t3_abc")
        self.assertEqual(p[0]["author"], "alice")
        self.assertEqual(p[0]["subreddit"], "ClaudeAI")
        self.assertEqual(p[0]["external_url"], "https://simonwillison.net/2026/Oct/3/agents/")
        self.assertEqual(p[0]["text"], "My take on agents")
        self.assertEqual(p[0]["rank"], 1)


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "seen.json")

    def test_reported_never_again_rejected_after_cooldown(self):
        a = Archive(self.path)
        rep = {"key": "gh:a/b"}
        rej = {"key": "gh:c/d"}
        a.record([rep, rej], {"gh:a/b"}, date(2026, 10, 1))
        a.save()
        a = Archive(self.path)
        self.assertEqual(a.filter_new([rep, rej], date(2026, 10, 3), 7), [])
        self.assertEqual(a.filter_new([rep, rej], date(2026, 10, 9), 7), [rej])
        self.assertEqual(a.filter_new([rep], date(2027, 1, 1), 7), [])

    def test_same_article_via_other_post_blocked(self):
        a = Archive(self.path)
        a.record([{"key": "rd:t3_1", "external_url": "https://www.x.com/post/?utm=1"}],
                 {"rd:t3_1"}, date(2026, 10, 1))
        other = {"key": "rd:t3_2", "external_url": "http://x.com/post"}
        self.assertEqual(a.filter_new([other], date(2026, 10, 2), 7), [])
        self.assertEqual(norm_url("https://www.X.com/a/?q#f"), "x.com/a")

    def test_reported_status_not_downgraded(self):
        a = Archive(self.path)
        a.record([{"key": "k"}], {"k"}, date(2026, 10, 1))
        a.record([{"key": "k"}], set(), date(2026, 10, 2))
        self.assertEqual(a.data["items"]["k"]["status"], "reported")


def captured(cands):
    seen = []
    curate("github", cands, "m", ask=lambda p, m: seen.append(p) or {"items": []})
    return seen[0]


class CurateTest(unittest.TestCase):
    def test_extract_json_tolerates_fence_and_prose(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('Hier:\n{"a": {"b": 2}} Ende'), {"a": {"b": 2}})

    def test_unknown_and_duplicate_ids_dropped_links_from_data(self):
        cands = [{"key": "gh:x/y", "full_name": "x/y", "sources": ["trending/all"],
                  "url": "https://github.com/x/y"}]
        answer = {"headline": "h", "items": [
            {"id": "g0", "category": "MCP & Skills", "what": "w", "why": "y", "importance": 3},
            {"id": "g0", "category": "X", "what": "dup", "why": "", "importance": 1},
            {"id": "g99", "category": "X", "what": "erfunden", "why": "", "importance": 3}]}
        head, items = curate("github", cands, "m", ask=lambda p, m: answer)
        self.assertNotIn("{max_items}", captured(cands))
        self.assertEqual(head, "h")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://github.com/x/y")

    def test_cap_enforced(self):
        cands = [{"key": f"gh:{i}", "full_name": f"a/{i}", "sources": []} for i in range(5)]
        answer = {"items": [{"id": f"g{i}", "importance": 1} for i in range(5)]}
        self.assertEqual(len(curate("github", cands, "m", 3, ask=lambda p, m: answer)[1]), 3)

    def test_no_candidates_no_model_call(self):
        def boom(p, m):
            raise AssertionError("darf nicht aufgerufen werden")
        self.assertEqual(curate("reddit", [], "m", ask=boom)[1], [])


RSS2 = """<?xml version="1.0"?><rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>
<item><title>GPT-6 mini released</title><link>https://openai.com/index/gpt-6-mini/</link>
<description>&lt;p&gt;Cheaper model&lt;/p&gt;</description><dc:creator>OpenAI</dc:creator>
<pubDate>Sun, 04 Oct 2026 18:00:00 GMT</pubDate></item></channel></rss>"""

YT = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
<entry><title>Opus 5.5 tested</title><link rel="alternate" href="https://www.youtube.com/watch?v=x"/>
<author><name>Theo</name></author><published>2026-10-04T10:00:00+00:00</published>
<media:group><media:description>Long test video</media:description></media:group></entry></feed>"""


class NewsTest(unittest.TestCase):
    def test_rss2_and_youtube_atom(self):
        r = fetch_news.parse_feed(RSS2, "OpenAI")[0]
        self.assertEqual((r["title"], r["url"], r["text"], r["author"]),
                         ("GPT-6 mini released", "https://openai.com/index/gpt-6-mini/",
                          "Cheaper model", "OpenAI"))
        self.assertTrue(r["published"].startswith("2026-10-04T18:00"))
        y = fetch_news.parse_feed(YT, "YouTube: Theo")[0]
        self.assertEqual((y["url"], y["author"], y["text"]),
                         ("https://www.youtube.com/watch?v=x", "Theo", "Long test video"))

    def test_window_future_dates_cap_and_dedup(self):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        def item(url, d):
            return {"title": "t", "url": url, "source": "s",
                    "published": d.isoformat() if d else None}
        entries = [item("https://a.com/old", now - timedelta(days=5)),
                   item("https://a.com/future", now + timedelta(days=300)),
                   item("https://a.com/nodate", None),
                   item("https://a.com/1", now), item("http://www.a.com/1/", now),  # Dublette
                   item("https://a.com/2", now)]

        def run(cap):
            f = fetch_news.NewsFetcher({"window_hours": 48, "max_per_feed": cap,
                                        "feeds": [{"label": "A", "url": "u"}]}, log=lambda m: None)
            f._get = lambda url: ""
            f.hacker_news = lambda since: []
            orig = fetch_news.parse_feed
            fetch_news.parse_feed = lambda x, l: [dict(e) for e in entries]
            try:
                return [i["key"] for i in f.fetch()]
            finally:
                fetch_news.parse_feed = orig
        self.assertEqual(run(10), ["nw:a.com/1", "nw:a.com/2"])  # alt, Zukunft, ohne Datum, Dublette raus
        self.assertEqual(run(4), ["nw:a.com/1"])  # Grenze greift auf die Feed-Reihenfolge


class TitleMemoryTest(unittest.TestCase):
    def test_recent_titles_window_excludes_today(self):
        a = Archive(os.path.join(tempfile.mkdtemp(), "s.json"))
        a.remember_titles(["Alt"], date(2026, 9, 1))
        a.remember_titles(["Gestern"], date(2026, 10, 4))
        a.remember_titles(["Heute"], date(2026, 10, 5))
        self.assertEqual(a.recent_titles(date(2026, 10, 5), 7), ["2026-10-04: Gestern"])

    def test_recent_placeholder_filled(self):
        seen = []
        cands = [{"key": "nw:x", "title": "t", "source": "s", "url": "https://x.com/a"}]
        curate("news", cands, "m", ask=lambda p, m: seen.append(p) or {"items": []},
               recent=["2026-10-04: Gestern"])
        self.assertIn("2026-10-04: Gestern", seen[0])
        self.assertNotIn("{recent}", seen[0])


if __name__ == "__main__":
    unittest.main()
