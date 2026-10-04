"""GitHub-Abruf: Trending-Seiten + Suche nach neuen Repos zu den Radar-Themen.

Reines I/O. Was davon relevant ist, entscheidet die Kuratierung (curate.py).
"""
import html
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

UA = "ki-radar/0.1 (personal daily digest; github.com/RainerSchlund/ki-radar)"


def _get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _token():
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


def _clean(text, limit=400):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()[:limit]


def parse_trending(page):
    """Zerlegt github.com/trending in Repo-Einträge."""
    repos = []
    for art in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="/([^"/]+/[^"/]+)"', art, re.S)
        if not m:
            continue
        desc = re.search(r'<p class="col-9[^"]*">(.*?)</p>', art, re.S)
        today = re.search(r'([\d,]+)\s+stars\s+(today|this week)', art)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', art)
        repos.append({
            "full_name": m.group(1).strip(),
            "description": _clean(desc.group(1)) if desc else "",
            "stars_today": int(today.group(1).replace(",", "")) if today else None,
            "language": lang.group(1).strip() if lang else None,
        })
    return repos


class GitHubFetcher:
    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.token = _token()
        self.failures = []

    def _api(self, path):
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return json.loads(_get("https://api.github.com" + path, headers))

    def trending(self):
        found = {}
        for lang in self.cfg["trending_paths"]:
            url = "https://github.com/trending" + (f"/{lang}" if lang else "") + "?since=daily"
            try:
                for r in parse_trending(_get(url)):
                    r["sources"] = [f"trending/{urllib.parse.unquote(lang) or 'all'}"]
                    if r["full_name"] in found:
                        found[r["full_name"]]["sources"] += r["sources"]
                    else:
                        found[r["full_name"]] = r
            except Exception as e:
                self.failures.append(f"trending/{lang or 'all'}: {e}")
            time.sleep(1)
        return found

    def search(self):
        since = (datetime.now(timezone.utc) - timedelta(days=self.cfg["search_window_days"])).date()
        found = {}
        for q in self.cfg["search_queries"]:
            full = f"{q} created:>={since} stars:>={self.cfg['search_min_stars']}"
            path = ("/search/repositories?sort=stars&order=desc&per_page="
                    f"{self.cfg['search_per_query']}&q=" + urllib.parse.quote(full))
            try:
                for item in self._api(path).get("items", []):
                    name = item["full_name"]
                    if name in found:
                        found[name]["sources"].append(f"search:{q}")
                        continue
                    found[name] = self._from_api(item)
                    found[name]["sources"] = [f"search:{q}"]
            except Exception as e:
                self.failures.append(f"search '{q}': {e}")
            time.sleep(2.5)  # Such-API: 30 Anfragen/Minute
        return found

    @staticmethod
    def _from_api(item):
        return {
            "full_name": item["full_name"],
            "description": _clean(item.get("description") or ""),
            "stars": item.get("stargazers_count"),
            "language": item.get("language"),
            "topics": item.get("topics") or [],
            "created_at": item.get("created_at"),
            "pushed_at": item.get("pushed_at"),
            "homepage": item.get("homepage") or None,
        }

    def enrich(self, repo):
        """Trending-Einträge haben keine Sterne/Topics — per API nachladen."""
        try:
            data = self._from_api(self._api(f"/repos/{repo['full_name']}"))
            for k, v in data.items():
                if repo.get(k) in (None, "", []):
                    repo[k] = v
        except Exception as e:
            self.failures.append(f"enrich {repo['full_name']}: {e}")

    def fetch(self):
        repos = self.search()
        for name, r in self.trending().items():
            if name in repos:
                repos[name]["sources"] += r["sources"]
                repos[name]["stars_today"] = r["stars_today"]
            else:
                repos[name] = r
                self.enrich(r)
        for r in repos.values():
            r["url"] = f"https://github.com/{r['full_name']}"
            r["key"] = "gh:" + r["full_name"].lower()
        self.log(f"github: {len(repos)} Kandidaten, {len(self.failures)} Fehler")
        return list(repos.values())


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "config.json"))["github"]
    f = GitHubFetcher(cfg, log=lambda m: print(m, file=sys.stderr))
    out = f.fetch()
    json.dump({"items": out, "failures": f.failures}, sys.stdout, indent=1, ensure_ascii=False)
