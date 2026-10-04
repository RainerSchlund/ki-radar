"""Tageslauf: abrufen → Bekanntes filtern → kuratieren → Dashboard → veröffentlichen.

  python3 radar/run.py              # Tageslauf inkl. git push
  python3 radar/run.py --no-publish # alles außer push
  python3 radar/run.py --force      # auch wenn heute schon gelaufen
  python3 radar/run.py --render     # nur Seiten neu erzeugen

Schlägt Abruf oder Kuratierung fehl, wird NICHTS ins Archiv geschrieben
(Exit 1) — der nächste Versuch holt alles nach.
"""
import argparse
import fcntl
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from archive import Archive  # noqa: E402
from curate import curate  # noqa: E402
from fetch_github import GitHubFetcher  # noqa: E402
from fetch_reddit import RedditFetcher  # noqa: E402
import render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(ROOT, "archive", "status.json")


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", "run.log"), "a") as f:
        f.write(line + "\n")


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)


def publish(today, has_news):
    git("add", "docs", "archive")
    if not git("diff", "--cached", "--quiet", check=False).returncode:
        log("publish: nichts zu committen")
        return
    msg = f"Radar {today}: " + ("neue Ausgabe" if has_news else "keine Neuigkeiten")
    git("commit", "-m", msg)
    git("pull", "--rebase", "--autostash")
    git("push")
    log("publish: gepusht")


def no_mentions(text):
    """Verhindert, dass '@name' aus Fremdtext im Issue echte GitHub-Nutzer anpingt."""
    return (text or "").replace("@", "@\u200b")


def latest_json(cfg, day):
    def top(items, n=5):
        return [{"title": no_mentions(i.get("full_name") or i.get("title")),
                 "what": no_mentions(i["what"]), "importance": i["importance"]}
                for i in items[:n]]
    return {
        "date": day["date"],
        "url": f"{cfg['site_url']}/days/{day['date']}.html",
        "archive_url": f"{cfg['site_url']}/",
        "notify": cfg.get("notify_github_user"),
        "github": {"count": len(day["github"]["items"]), "headline": no_mentions(day["github"]["headline"]),
                   "top": top(day["github"]["items"])},
        "reddit": {"count": len(day["reddit"]["items"]), "headline": no_mentions(day["reddit"]["headline"]),
                   "top": top(day["reddit"]["items"])},
    }


def run(args):
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    today = date.today()
    day_file = os.path.join(ROOT, "archive", "items", f"{today}.json")
    status = {}
    if os.path.exists(STATUS):
        with open(STATUS) as f:
            status = json.load(f)

    if args.render:
        render.render_all(status)
        return 0
    if status.get("last_date") == today.isoformat() and not args.force:
        log(f"heute ({today}) schon gelaufen — nichts zu tun")
        return 0

    gh_f = GitHubFetcher(cfg["github"], log=log)
    rd_f = RedditFetcher(cfg["reddit"], log=log)
    with ThreadPoolExecutor(2) as ex:
        gh_job, rd_job = ex.submit(gh_f.fetch), ex.submit(rd_f.fetch)
        gh_all, rd_all = gh_job.result(), rd_job.result()
    if not gh_all and not rd_all:
        log("Abruf leer — offline? Abbruch ohne Archiv-Eintrag")
        return 1

    arc = Archive(os.path.join(ROOT, "archive", "seen.json"))
    cooldown = cfg["reject_cooldown_days"]
    gh_new = arc.filter_new(gh_all, today, cooldown)
    rd_new = arc.filter_new(rd_all, today, cooldown)
    log(f"neu: GitHub {len(gh_new)}/{len(gh_all)}, Reddit {len(rd_new)}/{len(rd_all)}")

    gh_head, gh_items = curate("github", gh_new, cfg["model"], cfg["max_items_per_source"])
    log(f"kuratiert GitHub: {len(gh_items)}")
    rd_head, rd_items = curate("reddit", rd_new, cfg["model"], cfg["max_items_per_source"])
    log(f"kuratiert Reddit: {len(rd_items)}")

    day = {
        "date": today.isoformat(),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "github": {"headline": gh_head, "items": gh_items, "candidates": len(gh_new),
                   "fetched": len(gh_all), "failures": gh_f.failures},
        "reddit": {"headline": rd_head, "items": rd_items, "candidates": len(rd_new),
                   "fetched": len(rd_all), "failures": rd_f.failures},
    }
    has_news = bool(gh_items or rd_items)
    with open(day_file, "w") as f:
        json.dump(day, f, indent=1, ensure_ascii=False)
    arc.record(gh_new + rd_new, {i["key"] for i in gh_items + rd_items}, today)
    arc.save()

    status = {"last_date": today.isoformat(),
              "last_check": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "last_result": (f"{len(gh_items)} Repos, {len(rd_items)} Beiträge"
                              if has_news else "keine Neuigkeiten")}
    with open(STATUS, "w") as f:
        json.dump(status, f, indent=1, ensure_ascii=False)
    if has_news:
        with open(os.path.join(ROOT, "docs", "latest.json"), "w") as f:
            json.dump(latest_json(cfg, day), f, indent=1, ensure_ascii=False)
    render.render_all(status)
    log(f"fertig: {status['last_result']}")
    if args.publish:
        publish(today, has_news)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-publish", dest="publish", action="store_false")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--render", action="store_true")
    args = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "logs", ".lock"), "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("läuft bereits — Abbruch")
            return 0
        try:
            return run(args)
        except Exception as e:
            log(f"FEHLER: {type(e).__name__}: {e}")
            return 1


if __name__ == "__main__":
    sys.exit(main())
