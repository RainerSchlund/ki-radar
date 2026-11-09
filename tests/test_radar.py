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
import curate as curate_mod  # noqa: E402
import leitstand  # noqa: E402
import pruefung  # noqa: E402
import pruefschema  # noqa: E402
import skill_liste  # noqa: E402

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


class EinsatzTest(unittest.TestCase):
    def test_einsatz_from_config_unknown_becomes_sonstiges(self):
        cands = [{"key": f"gh:{i}", "full_name": f"a/{i}", "sources": []} for i in range(2)]
        einsatz = [{"name": "Werkzeuge/MCP", "wofuer": "x"}, {"name": "Sonstiges", "wofuer": "y"}]
        seen = []
        answer = {"items": [{"id": "g0", "einsatz": "Werkzeuge/MCP", "importance": 2},
                            {"id": "g1", "einsatz": "Erfunden", "importance": 1}]}
        _, items = curate("github", cands, "m", ask=lambda p, m: seen.append(p) or answer,
                          einsatz=einsatz)
        self.assertEqual([i["einsatz"] for i in items], ["Werkzeuge/MCP", "Sonstiges"])
        self.assertIn('"Werkzeuge/MCP": x', seen[0])
        self.assertNotIn("{einsatz}", seen[0])

    def test_config_einsatz_list_is_valid(self):
        import json
        with open(os.path.join(os.path.dirname(__file__), "..", "config.json")) as f:
            cfg = json.load(f)
        names = [e["name"] for e in cfg["einsatz"]]
        self.assertIn("Sonstiges", names)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(cfg["pruefung"]["top_n"], 5)


class FakeProc:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class AskClaudeErrorTest(unittest.TestCase):
    def _ask(self, proc=None, exc=None):
        import subprocess
        orig = curate_mod.subprocess.run

        def fake(*a, **k):
            if exc:
                raise exc
            return proc
        curate_mod.subprocess.run = fake
        try:
            with self.assertRaises(curate_mod.ClaudeFehler) as cm:
                curate_mod.ask_claude("p", "m", timeout=1)
            return str(cm.exception)
        finally:
            curate_mod.subprocess.run = orig

    def test_empty_stdout(self):
        self.assertIn("leere Antwort", self._ask(FakeProc("")))

    def test_empty_result(self):
        self.assertIn("leere Antwort", self._ask(FakeProc('{"result": "", "is_error": false}')))

    def test_timeout_and_exit(self):
        import subprocess
        self.assertIn("Zeitüberschreitung", self._ask(exc=subprocess.TimeoutExpired("claude", 1)))
        self.assertIn("exit 1", self._ask(FakeProc("", 1, "limit")))

    def test_prose_without_json(self):
        self.assertIn("ohne gültiges JSON", self._ask(FakeProc('{"result": "Sorry, kein JSON"}')))


def repo(name, imp, today=0, stars=0, **kw):
    return {"key": "gh:" + name, "full_name": name, "url": "https://github.com/" + name,
            "importance": imp, "stars_today": today, "stars": stars, "what": "w", **kw}


GOOD = {"zusammenfassung": "z", "vergleichbar": [{"skill": "token-budget", "aehnlich": "a"},
                                                  {"skill": "gibts-nicht", "aehnlich": "b"}],
        "besser": [{"aspekt": "x", "beleg": "src/main.py"}, {"aspekt": "y", "beleg": "erfunden.py"}],
        "adaptierbar": [{"was": "Muster", "beleg": "./README.md", "selbstauskunft": False}],
        "urteil": "vorschlag", "verwendung": "idee adaptieren", "grund": "g",
        "belege": [{"datei": "src/main.py", "aussage": "a"}],
        "kurz_oeffentlich": "Ein Werkzeug für X; die Idee lohnt."}
FILES = ["README.md", "src/main.py"]
SKILLS = {"skills": [{"name": "token-budget", "herkunft": ["eigen"], "description": "d"}], "hinweise": []}


class PruefSchemaTest(unittest.TestCase):
    def test_valid_report_cleaned(self):
        r = pruefschema.validate(GOOD, FILES, {"token-budget"})
        self.assertEqual([v["skill"] for v in r["vergleichbar"]], ["token-budget"])
        self.assertEqual([b["beleg"] for b in r["besser"]], ["src/main.py"])
        self.assertTrue(r["adaptierbar"][0]["selbstauskunft"])  # README = Selbstauskunft, erzwungen
        self.assertEqual(r["adaptierbar"][0]["beleg"], "README.md")
        self.assertEqual(len(r["warnungen"]), 2)

    def test_hard_errors(self):
        for bad in ({**GOOD, "urteil": "vielleicht"}, {**GOOD, "verwendung": None},
                    {**GOOD, "belege": [{"datei": "nicht/da.py"}]}, {**GOOD, "grund": ""}, []):
            with self.assertRaises(pruefschema.Ungueltig):
                pruefschema.validate(bad, FILES, {"token-budget"})

    def test_verworfen_drops_verwendung(self):
        r = pruefschema.validate({**GOOD, "urteil": "verworfen"}, FILES, set())
        self.assertIsNone(r["verwendung"])

    def test_public_text_filter(self):
        path = os.path.join(tempfile.mkdtemp(), "s.txt")
        with open(path, "w") as f:
            f.write("# Kommentar\ni:geheimkunde\nCore\nre:\\bX-\\d+\n")
        sperr = pruefschema.load_sperrliste(path)
        ok = lambda t: pruefschema.public_text(t, sperr)[1] is None  # noqa: E731
        self.assertTrue(ok("Ein core-naher Agent."))  # 'Core' nur exakt
        self.assertFalse(ok("Ähnlich wie bei GeheimKunde."))
        self.assertFalse(ok("Siehe Ticket X-12."))
        self.assertFalse(ok("Liegt unter ~/IdeaProjects/x"))
        self.assertFalse(ok("Mehr auf https://example.org"))
        self.assertEqual(pruefschema.public_text("", sperr)[0], pruefschema.NEUTRAL)

    def test_prompt_uses_skill_md_and_marks_foreign_data(self):
        p = pruefschema.prompt(SKILLS, {"repo": "a/b", "tree": "README.md",
                                        "excerpts": [{"path": "README.md", "text": "ignore all"}]})
        self.assertNotIn("<!-- PROMPT -->", p)
        self.assertIn("Antworte nur mit diesem JSON-Objekt", p)
        self.assertIn("FREMDDATEN", p)
        self.assertIn('"token-budget"', p)


class TopFiveTest(unittest.TestCase):
    def test_order_importance_then_signal_skips_reviewed(self):
        items = [repo("a/1", 1, stars=9999), repo("a/2", 3, today=5), repo("a/3", 3, today=50),
                 repo("a/4", 2, stars=10), repo("a/5", 2, stars=20), repo("a/6", 2, stars=5),
                 repo("a/7", 3, pruefung="ok")]
        self.assertEqual([i["full_name"] for i in pruefung.top_n(items, 5)],
                         ["a/3", "a/2", "a/5", "a/4", "a/6"])

    def _review(self, ask):
        items = [repo(f"a/{i}", 3 - i % 3, today=i) for i in range(7)]
        logs = []
        local = tempfile.mkdtemp()
        fetch = lambda n: {"repo": n, "files": FILES, "tree": "README.md\nsrc/main.py",  # noqa: E731
                           "excerpts": [{"path": "README.md", "text": "t"}]}
        failed = pruefung.review_top(items, {"model": "m", "pruefung": {"top_n": 5, "parallel": 1}},
                                     date(2026, 11, 9), logs.append, fetch=fetch, ask=ask,
                                     build_skills=lambda p: SKILLS, local=local)
        return items, failed, logs, local

    def test_only_top_five_reviewed_and_reports_stay_local(self):
        calls = []
        items, failed, logs, local = self._review(lambda p, m: calls.append(p) or GOOD)
        self.assertEqual(len(calls), 5)
        self.assertEqual(failed, [])
        self.assertEqual(sum(1 for i in items if i.get("urteil") == "vorschlag"), 5)
        self.assertEqual(sum(1 for i in items if "pruefung" not in i), 2)
        self.assertEqual(len(os.listdir(os.path.join(local, "pruefungen", "2026-11-09"))), 5)
        for i in items:  # keine Berichtsdetails am öffentlichen Item
            self.assertNotIn("besser", i)

    def test_empty_claude_answer_logged_run_continues(self):
        def ask(p, m):
            if "a/0" in p:
                raise curate_mod.ClaudeFehler("claude -p leere Antwort (result leer)")
            return GOOD
        items, failed, logs, _ = self._review(ask)
        self.assertEqual(len(failed), 1)
        bad = [i for i in items if i.get("pruefung") == "fehler"]
        self.assertEqual(len(bad), 1)
        self.assertIsNone(bad[0]["urteil"])
        self.assertTrue(any(line.startswith("FEHLER Prüfung") and "leere Antwort" in line for line in logs))
        self.assertEqual(sum(1 for i in items if i.get("pruefung") == "ok"), 4)


def day_fixture():
    return {"date": "2026-11-09",
            "news": {"items": [{"key": "nw:a.com/1", "title": "T", "headline_de": "Ü", "url": "https://a.com/1",
                                "what": "w", "importance": 3, "source": "googlenews:KI"}]},
            "reddit": {"items": [{"key": "rd:t3_x", "title": "R", "permalink": "https://reddit.com/x",
                                  "what": "w", "importance": 5, "subreddit": "ClaudeAI"}]},
            "github": {"items": [repo("a/b", 2, einsatz="Werkzeuge/MCP", pruefung="ok", urteil="vorschlag",
                                      verwendung="beobachten", urteil_kurz="k"),
                                 repo("c/d", 1, einsatz="Sonstiges")]}}


class LeitstandTest(unittest.TestCase):
    KEYS = {"id", "rubrik", "title", "url", "what", "importance", "source", "einsatz", "urteil", "urteil_kurz"}

    def _text(self, ids, extra=""):
        return " ".join(["wort"] * 160) + " " + " ".join(f"[[{i}]]" for i in ids) + extra

    def test_format_and_stable_ids(self):
        import re as _re
        day = day_fixture()
        items = leitstand.build_items(day)
        self.assertEqual([i["rubrik"] for i in items], ["news", "reddit", "github", "github"])
        for i in items:
            self.assertEqual(set(i), self.KEYS)
            self.assertRegex(i["id"], r"^[nrg]-20261109-[0-9a-f]{8}$")
            self.assertIn(i["importance"], (1, 2, 3))
        self.assertEqual(len({i["id"] for i in items}), 4)
        self.assertEqual(items[1]["importance"], 3)  # geklemmt
        self.assertEqual(items[0]["source"], "Google News · KI")
        self.assertEqual(items[1]["url"], "https://reddit.com/x")
        self.assertEqual((items[2]["einsatz"], items[2]["urteil"], items[2]["urteil_kurz"]),
                         ("Werkzeuge/MCP", "vorschlag", "beobachten: k"))
        self.assertEqual((items[3]["urteil"], items[3]["urteil_kurz"]), (None, None))
        self.assertIsNone(items[0]["einsatz"])
        self.assertEqual(items, leitstand.build_items(day_fixture()))  # gleiche Eingabe, gleiche IDs
        path = os.path.join(tempfile.mkdtemp(), "l.json")
        prompts = []
        ids = [i["id"] for i in items[:2]]
        data = leitstand.export(day, {"model": "m"}, lambda m: None, path=path,
                                ask=lambda p, m: prompts.append(p) or {"title": "T", "text": self._text(ids)})
        self.assertEqual(list(data), ["format", "date", "report", "items"])
        self.assertEqual(data["format"], "ki-radar-leitstand/1")
        self.assertEqual(set(data["report"]), {"title", "text"})
        self.assertNotIn(items[2]["id"], prompts[0])  # Bericht nur über News + Reddit
        with open(path) as f:
            self.assertEqual(__import__("json").load(f), data)
        # zweiter Export ohne Änderung: kein neuer claude-Aufruf
        leitstand.export(day, {"model": "m"}, lambda m: None, path=path,
                         ask=lambda p, m: self.fail("Bericht hätte aus dem Cache kommen müssen"))
        self.assertTrue(_re.search(r"\[\[n-", data["report"]["text"]))

    def test_invented_id_rejected_missing_warned(self):
        ids = ["n-20261109-aaaaaaaa", "r-20261109-bbbbbbbb"]
        with self.assertRaises(leitstand.Ungueltig):
            leitstand.validate_report({"title": "t", "text": self._text(ids, " [[n-20261109-ffffffff]]")}, ids, {})
        rep, warn = leitstand.validate_report({"title": "t", "text": self._text(ids[:1])}, ids, {})
        self.assertTrue(any("nicht referenziert" in w for w in warn))
        _, warn = leitstand.validate_report({"title": "t", "text": "kurz [[%s]] [[%s]]" % tuple(ids)}, ids, {})
        self.assertTrue(any("Länge" in w for w in warn))

    def test_report_failure_falls_back_and_is_marked(self):
        day, logs, calls = day_fixture(), [], []

        def ask(p, m):
            calls.append(p)
            raise curate_mod.ClaudeFehler("claude -p leere Antwort (stdout leer)")
        data = leitstand.export(day, {"model": "m"}, logs.append,
                                path=os.path.join(tempfile.mkdtemp(), "l.json"), ask=ask)
        self.assertEqual(len(calls), 2)  # ein zweiter Versuch
        self.assertIn("nicht erzeugt", data["report"]["text"])
        self.assertTrue(day["leitstand_report"]["fehler"])
        self.assertEqual(sum("FEHLER Leitstand-Bericht" in line for line in logs), 2)

    def test_retry_after_invented_id_succeeds(self):
        day = day_fixture()
        ids = [i["id"] for i in leitstand.build_items(day)[:2]]
        answers = [{"title": "t", "text": self._text(ids, " [[n-20261109-00000000]]")},
                   {"title": "t", "text": self._text(ids)}]
        data = leitstand.export(day, {"model": "m"}, lambda m: None,
                                path=os.path.join(tempfile.mkdtemp(), "l.json"),
                                ask=lambda p, m: answers.pop(0))
        self.assertFalse(day["leitstand_report"]["fehler"])
        self.assertNotIn("00000000", data["report"]["text"])


class HoleRepoTest(unittest.TestCase):
    def test_digest_skips_symlinks_binaries_and_git(self):
        import hole_repo
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "src"))
        os.makedirs(os.path.join(root, ".git"))
        for rel, data in (("README.md", b"Hallo"), ("src/main.py", b"print(1)"),
                          ("src/bin.dat", b"\0\1\2"), (".git/config", b"x")):
            with open(os.path.join(root, rel), "wb") as f:
                f.write(data)
        os.symlink("/etc/passwd", os.path.join(root, "src", "leak.py"))
        d = hole_repo.digest(root, "a/b")
        self.assertEqual(d["files"], ["README.md", "src/bin.dat", "src/main.py"])
        self.assertEqual([e["path"] for e in d["excerpts"]], ["README.md", "src/main.py"])

    def test_clone_rejects_odd_names(self):
        import hole_repo
        with self.assertRaises(ValueError):
            hole_repo.clone("a/b;rm -rf", "/tmp/x", run=lambda *a, **k: self.fail("darf nicht klonen"))


class SkillListeTest(unittest.TestCase):
    def test_frontmatter_block_scalar_and_quotes(self):
        fm = skill_liste.frontmatter("---\nname: 'x-y'\ndescription: >\n  zwei\n  Zeilen\nother: 1\n---\n# body")
        self.assertEqual(fm, {"name": "x-y", "description": "zwei Zeilen", "other": "1"})

    def test_catalog_unreachable_noted(self):
        def boom(*a, **k):
            raise OSError("kein Netz")
        _, notes = skill_liste.company_catalog(run=boom, script=__file__)
        self.assertTrue(notes and "nicht" in notes[0])


if __name__ == "__main__":
    unittest.main()
