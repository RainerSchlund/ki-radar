"""Archiv gegen Wiederholungen.

archive/seen.json merkt sich jeden Kandidaten mit Status:
  reported  – stand schon im Dashboard, wird nie wieder gezeigt
  rejected  – als irrelevant aussortiert; nach reject_cooldown_days neu prüfbar
Zusätzlich sperrt eine gemeldete externe URL (Blogartikel) dieselbe URL in
anderen Reddit-Beiträgen, damit ein Artikel nicht zweimal auftaucht.
"""
import json
import os
import re
from datetime import date, timedelta


def norm_url(url):
    if not url:
        return None
    u = re.sub(r"^https?://(www\.)?", "", url.strip().lower())
    u = re.sub(r"[?#].*$", "", u)
    return u.rstrip("/")


class Archive:
    def __init__(self, path):
        self.path = path
        self.data = {"items": {}, "urls": {}}
        if os.path.exists(path):
            with open(path) as f:
                self.data = json.load(f)

    def is_blocked(self, item, today, cooldown_days):
        entry = self.data["items"].get(item["key"])
        if entry:
            if entry["status"] == "reported":
                return True
            last = date.fromisoformat(entry["date"])
            if today - last < timedelta(days=cooldown_days):
                return True
        ext = norm_url(item.get("external_url"))
        return bool(ext and ext in self.data["urls"])

    def filter_new(self, items, today, cooldown_days):
        return [i for i in items if not self.is_blocked(i, today, cooldown_days)]

    def record(self, items, reported_keys, today):
        for i in items:
            status = "reported" if i["key"] in reported_keys else "rejected"
            prev = self.data["items"].get(i["key"])
            if prev and prev["status"] == "reported":
                continue
            self.data["items"][i["key"]] = {"status": status, "date": today.isoformat(),
                                            "first_seen": (prev or {}).get("first_seen",
                                                                           today.isoformat())}
            ext = norm_url(i.get("external_url"))
            if status == "reported" and ext:
                self.data["urls"][ext] = today.isoformat()

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=0, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, self.path)
