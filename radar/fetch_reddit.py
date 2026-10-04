"""Reddit-Abruf über die Atom-Feeds (die .json-Endpunkte antworten mit 403).

Drei Feed-Arten: Top-Beiträge des Tages je Subreddit, Beiträge die auf
beobachtete Blog-Domains verlinken (reddit.com/domain/<d>), und Beiträge
beobachteter Nutzer. Reines I/O, Bewertung macht curate.py.
"""
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

UA = "linux:ki-radar:v0.1 (personal daily digest)"
NS = {"a": "http://www.w3.org/2005/Atom"}


def _clean(text, limit=600):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def parse_feed(xml_text, feed_label):
    root = ET.fromstring(xml_text)
    posts = []
    for rank, e in enumerate(root.findall("a:entry", NS), 1):
        pid = (e.findtext("a:id", "", NS) or "").strip()
        if not pid.startswith("t3_"):
            continue
        content = e.findtext("a:content", "", NS) or ""
        link_el = e.find("a:link", NS)
        permalink = link_el.get("href") if link_el is not None else ""
        ext = re.search(r'<a href="([^"]+)">\[link\]</a>', content)
        external = html.unescape(ext.group(1)) if ext else None
        if external and "reddit.com" in external:
            external = None
        cat = e.find("a:category", NS)
        sub = cat.get("term") if cat is not None else None
        # Selbsttext steht im Content-Block vor "submitted by"
        body = re.split(r"submitted by", content, maxsplit=1)[0]
        posts.append({
            "id": pid,
            "title": _clean(e.findtext("a:title", "", NS), 300),
            "author": (e.findtext("a:author/a:name", "", NS) or "").replace("/u/", ""),
            "subreddit": sub,
            "published": e.findtext("a:published", None, NS) or e.findtext("a:updated", None, NS),
            "permalink": permalink,
            "external_url": external,
            "text": _clean(body),
            "sources": [feed_label],
            "rank": rank,
        })
    return posts


class RedditFetcher:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.failures = []

    def _get(self, url):
        for attempt, wait in enumerate((0, 30, 90)):
            if wait:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 2:
                    raise
        raise RuntimeError("unreachable")

    @staticmethod
    def _search_url(query):
        return ("https://www.reddit.com/search.rss?sort=new&t=week&limit=100&q="
                + urllib.parse.quote(query))

    def feeds(self):
        """Gebündelte Feeds: Reddit erlaubt ohne Anmeldung ~1 Abruf pro Minute."""
        out = [("r/" + "+".join(g), "https://www.reddit.com/r/" + "+".join(g)
                + "/top/.rss?t=day&limit=100") for g in self.cfg["subreddit_groups"]]
        # Blog-Domains und Nutzer lassen sich nur über die Suche bündeln
        # (reddit.com/domain/a+b liefert 404).
        doms, n = self.cfg["domains"], self.cfg.get("domain_groups_size", 10)
        for i in range(0, len(doms), n):
            q = " OR ".join(f"site:{d}" for d in doms[i:i + n])
            out.append((f"site/{'+'.join(doms[i:i + n])}", self._search_url(q)))
        users = self.cfg.get("users", [])
        if users:
            q = " OR ".join(f"author:{u}" for u in users)
            out.append(("u/" + "+".join(users), self._search_url(q)))
        return out

    def fetch(self):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.cfg["window_hours"])
        posts = {}
        feeds = self.feeds()
        for i, (label, url) in enumerate(feeds):
            if i:
                time.sleep(self.cfg["request_pause_seconds"])
            try:
                items = parse_feed(self._get(url), label)
            except Exception as e:
                self.failures.append(f"{label}: {e}")
                continue
            for p in items:
                try:
                    if datetime.fromisoformat(p["published"]) < cutoff:
                        continue
                except (TypeError, ValueError):
                    pass
                if p["id"] in posts:
                    posts[p["id"]]["sources"] += p["sources"]
                else:
                    posts[p["id"]] = p
        for p in posts.values():
            p["key"] = "rd:" + p["id"]
            p["url"] = p["permalink"]
        self.log(f"reddit: {len(posts)} Kandidaten aus {len(feeds)} Feeds, "
                 f"{len(self.failures)} Fehler")
        return list(posts.values())


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "config.json"))["reddit"]
    f = RedditFetcher(cfg, log=lambda m: print(m, file=sys.stderr))
    out = f.fetch()
    json.dump({"items": out, "failures": f.failures}, sys.stdout, indent=1, ensure_ascii=False)
