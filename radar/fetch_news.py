"""News-Abruf: RSS/Atom-Feeds (Blogs, Hersteller, Fachmedien, YouTube),
Google-News-Suchen und Hacker News. Reines I/O, Bewertung macht curate.py.
"""
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (X11; Linux x86_64) ki-radar/0.1 (personal daily digest)"
ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"


def _clean(text, limit=500):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def _date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def parse_feed(xml_text, label):
    """RSS 2.0, RDF/RSS 1.0 und Atom (inkl. YouTube) → Einträge."""
    root = ET.fromstring(xml_text)
    out = []
    entries = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    for e in entries:
        fields = {}
        link = None
        for c in e:
            name = _local(c.tag)
            if name == "link":
                href = c.get("href")
                if href and c.get("rel", "alternate") == "alternate":
                    link = link or href
                elif c.text and c.text.strip():
                    link = link or c.text.strip()
            elif name not in fields:
                fields[name] = c.text or ""
        group = e.find(f"{MEDIA}group")
        desc = fields.get("description") or fields.get("summary") or fields.get("content") or ""
        if group is not None and not desc:
            desc = group.findtext(f"{MEDIA}description", "")
        author = fields.get("creator") or ""
        a = e.find(f"{ATOM}author")
        if a is not None:
            author = a.findtext(f"{ATOM}name", "") or author
        published = _date(fields.get("published") or fields.get("pubDate")
                          or fields.get("date") or fields.get("updated"))
        title = _clean(fields.get("title"), 300)
        if not link or not title:
            continue
        out.append({"title": title, "url": link.strip(), "text": _clean(desc),
                    "author": _clean(author, 80) or None,
                    "published": published.isoformat() if published else None,
                    "source": label})
    return out


class NewsFetcher:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.failures = []

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")

    def _feed(self, label_url):
        label, url = label_url
        cap = (self.cfg.get("google_news_max_per_query", 20) if label.startswith("googlenews:")
               else self.cfg.get("max_per_feed", 30))
        try:
            return parse_feed(self._get(url), label)[:cap]  # Feeds sind neueste/relevanteste zuerst
        except Exception as e:
            self.failures.append(f"{label}: {e}")
            return []

    def _google_news(self):
        jobs = []
        for q in self.cfg.get("google_news_queries", []):
            lang = q.get("lang", "en")
            url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q["q"] + " when:2d")
                   + ("&hl=de&gl=DE&ceid=DE:de" if lang == "de" else "&hl=en-US&gl=US&ceid=US:en"))
            jobs.append((f"googlenews:{q['q']}", url))
        return jobs

    def hacker_news(self, since):
        """Populäre HN-Stories seit `since` zu den Suchbegriffen (Punkte client-seitig)."""
        hn = self.cfg.get("hacker_news", {})
        found = {}
        for q in hn.get("queries", []):
            url = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=50&query="
                   + urllib.parse.quote(q) + f"&numericFilters=created_at_i>{int(since.timestamp())}")
            try:
                hits = json.loads(self._get(url)).get("hits", [])
            except Exception as e:
                self.failures.append(f"hn '{q}': {e}")
                continue
            for h in hits:
                if (h.get("points") or 0) < hn.get("min_points", 80) or h["objectID"] in found:
                    continue
                found[h["objectID"]] = {
                    "title": _clean(h.get("title"), 300),
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
                    "discussion_url": f"https://news.ycombinator.com/item?id={h['objectID']}",
                    "text": _clean(h.get("story_text") or ""), "author": h.get("author"),
                    "published": h.get("created_at"), "source": "hackernews",
                    "points": h.get("points"), "comments": h.get("num_comments"),
                }
        return list(found.values())

    def fetch(self):
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=self.cfg["window_hours"])
        jobs = [(f["label"], f["url"]) for f in self.cfg["feeds"]] + self._google_news()
        with ThreadPoolExecutor(8) as ex:
            batches = list(ex.map(self._feed, jobs))
        items = [i for b in batches for i in b] + self.hacker_news(since)
        fresh, seen = [], set()
        for i in items:
            d = _date(i["published"]) if i.get("published") else None
            if d is None or d < since or d > now + timedelta(days=1):
                continue  # ohne plausibles Datum kein Nachweis, dass es neu ist
            key = re.sub(r"^https?://(www\.)?", "", i["url"].lower()).split("#")[0].rstrip("/")
            if key in seen:
                continue
            seen.add(key)
            i["key"] = "nw:" + key
            fresh.append(i)
        empty = [lbl for (lbl, _), b in zip(jobs, batches) if not b
                 and not any(f.startswith(lbl + ":") for f in self.failures)]
        self.log(f"news: {len(fresh)} Kandidaten aus {len(jobs)} Feeds + HN, "
                 f"{len(self.failures)} Fehler, {len(empty)} leere Feeds")
        return fresh


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "config.json"))["news"]
    f = NewsFetcher(cfg, log=lambda m: print(m, file=sys.stderr))
    t = time.time()
    out = f.fetch()
    json.dump({"items": out, "failures": f.failures, "secs": round(time.time() - t)},
              sys.stdout, indent=1, ensure_ascii=False)
