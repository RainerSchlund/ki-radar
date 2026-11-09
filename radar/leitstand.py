"""Export für den Leitstand: docs/leitstand.json (Format ki-radar-leitstand/1).

items  = alle Einträge des Tages (News, Reddit, GitHub) mit über Tage stabiler ID
report = zusammenhängender deutscher Bericht über News + Reddit (eigener `claude -p`-Aufruf),
         der jede erwähnte Meldung mit [[<id>]] referenziert. Code prüft die IDs: erfundene
         IDs → ungültig (ein zweiter Versuch, dann Ersatztext); fehlende/Länge → Warnung.
review = Stand des Reviews von Hand zum Prüf-Urteil (GitHub): "ungeprueft" bis bestätigt;
         Quelle archive/reviews.json (nur IDs + Status, schreibt `leitstand radar reviews`).

Zweite, NICHT öffentliche Datei local/leitstand-voll.json (Format ki-radar-leitstand-voll/1):
die vollen Prüfberichte je Item-ID für das private Leitstand-Dashboard (bis 30 Tage).

  python3 radar/leitstand.py [--date JJJJ-MM-TT]   # Tag aus dem Archiv neu exportieren, ohne Modell
"""
import argparse
import hashlib
import json
import os
import re
import sys

from curate import ask_claude

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL = os.path.join(ROOT, "local")
REVIEWS = os.path.join(ROOT, "archive", "reviews.json")
FORMAT = "ki-radar-leitstand/1"
VOLL_FORMAT = "ki-radar-leitstand-voll/1"
REVIEW_STATUS = ("stimmt", "teilweise", "falsch")  # sonst "ungeprueft"
KEEP_DAYS = 30
PREFIX = {"news": "n", "reddit": "r", "github": "g"}
REF = re.compile(r"\[\[([^\[\]]+)\]\]")


class Ungueltig(ValueError):
    pass


def item_id(rubrik, day_date, key):
    """Stabil: hängt nur an Rubrik, Tag der Meldung und Archiv-Schlüssel (der nie wieder gezeigt wird)."""
    return f"{PREFIX[rubrik]}-{day_date.replace('-', '')}-{hashlib.sha1(key.encode()).hexdigest()[:8]}"


def _source(rubrik, it):
    if rubrik == "news":
        return it["source"].replace("googlenews:", "Google News · ")
    if rubrik == "reddit":
        return f"r/{it['subreddit']}" if it.get("subreddit") else "Reddit"
    return "GitHub"


def _urteil_kurz(it):
    if not it.get("urteil_kurz"):
        return None
    return f"{it['verwendung']}: {it['urteil_kurz']}" if it.get("verwendung") else it["urteil_kurz"]


def load_reviews(path=REVIEWS):
    """archive/reviews.json → {item_id: status}. Fehlt die Datei: {} (alles ungeprüft)."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    return {iid: r["status"] for iid, r in (data.get("reviews") or {}).items()
            if isinstance(r, dict) and r.get("status") in REVIEW_STATUS}


def review_status(urteil, iid, reviews):
    """Ohne Urteil kein Review; mit Urteil 'ungeprueft', bis es von Hand bewertet ist."""
    return (reviews or {}).get(iid, "ungeprueft") if urteil else None


def build_items(day, reviews=None):
    out = []
    for rubrik in ("news", "reddit", "github"):
        for it in (day.get(rubrik) or {}).get("items", []):
            gh = rubrik == "github"
            iid = item_id(rubrik, day["date"], it["key"])
            out.append({
                "id": iid,
                "rubrik": rubrik,
                "title": (it.get("headline_de") or it.get("title")) if not gh else it["full_name"],
                "url": it.get("permalink") if rubrik == "reddit" else it["url"],
                "what": it.get("what", ""),
                "importance": min(3, max(1, int(it.get("importance") or 1))),
                "source": _source(rubrik, it),
                "einsatz": it.get("einsatz") if gh else None,
                "urteil": it.get("urteil") if gh else None,
                "urteil_kurz": _urteil_kurz(it) if gh else None,
                "review": review_status(it.get("urteil"), iid, reviews) if gh else None,
            })
    return out


def build_voll(day, local=LOCAL):
    """Volle Prüfberichte des Tages je Item-ID aus local/pruefungen/<datum>/ (nur lokal)."""
    out = {}
    folder = os.path.join(local, "pruefungen", day["date"])
    for it in (day.get("github") or {}).get("items", []):
        if it.get("pruefung") != "ok":
            continue
        rec = None
        try:
            with open(os.path.join(folder, it["full_name"].replace("/", "__") + ".json")) as f:
                rec = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        out[item_id("github", day["date"], it["key"])] = {
            "repo": it["full_name"], "bericht": (rec or {}).get("bericht"),
            "fehlt": None if rec and rec.get("bericht") else "voller Bericht lokal nicht gefunden"}
    return out


def write_voll(day, path, local=LOCAL, keep_days=KEEP_DAYS):
    """Fügt den Tag in local/leitstand-voll.json ein (alle Tage, neueste keep_days)."""
    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    days = (data.get("days") or {}) if data.get("format") == VOLL_FORMAT else {}
    days[day["date"]] = build_voll(day, local)
    days = {d: days[d] for d in sorted(days)[-keep_days:]}
    data = {"format": VOLL_FORMAT, "days": days}
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return data


def report_prompt(day_date, items, cfg):
    with open(os.path.join(ROOT, "prompts", "leitstand.md")) as f:
        head = f.read()
    head = (head.replace("{date}", day_date).replace("{min_words}", str(cfg.get("min_words", 150)))
            .replace("{max_words}", str(cfg.get("max_words", 400))))
    lines = [json.dumps({k: i[k] for k in ("id", "rubrik", "title", "what", "source", "importance")},
                        ensure_ascii=False) for i in items]
    return head + "\n".join(lines)


def validate_report(rep, ids, cfg):
    """Gibt (report, warnungen) zurück; wirft Ungueltig bei erfundenen IDs oder fehlendem Text."""
    if not isinstance(rep, dict) or not str(rep.get("title") or "").strip() \
            or not str(rep.get("text") or "").strip():
        raise Ungueltig("title oder text fehlt")
    text = rep["text"].strip()
    refs = REF.findall(text)
    invented = sorted(set(refs) - set(ids))
    if invented:
        raise Ungueltig(f"erfundene IDs: {', '.join(invented[:10])}")
    warn = []
    missing = [i for i in ids if i not in refs]
    if missing:
        warn.append(f"{len(missing)} Einträge nicht referenziert: {', '.join(missing[:10])}")
    words = len(REF.sub("", text).split())
    if not cfg.get("min_words", 150) <= words <= cfg.get("max_words", 400):
        warn.append(f"Länge {words} Wörter außerhalb {cfg.get('min_words', 150)}–{cfg.get('max_words', 400)}")
    return {"title": rep["title"].strip(), "text": text}, warn


def make_report(day_date, items, cfg, model, log, ask=ask_claude):
    """Gibt (report, fehler: bool) zurück. Fehler werden geloggt, nie geschluckt."""
    items = [i for i in items if i["rubrik"] in ("news", "reddit")]
    ids = [i["id"] for i in items]
    if not items:
        return {"title": f"KI-Radar {day_date}", "text": "Heute keine News- oder Reddit-Meldungen."}, False
    prompt = report_prompt(day_date, items, cfg)
    for attempt in (1, 2):
        try:
            rep, warn = validate_report(ask(prompt, model), ids, cfg)
        except Exception as e:
            log(f"FEHLER Leitstand-Bericht Versuch {attempt}: {type(e).__name__}: {str(e)[:300]}")
            prompt += f"\n\nHinweis: Der vorige Versuch war ungültig ({str(e)[:200]}). Nur IDs aus der Liste verwenden."
            continue
        for w in warn:
            log(f"WARNUNG Leitstand-Bericht: {w}")
        return rep, False
    return {"title": f"KI-Radar {day_date}",
            "text": "Der Tagesbericht konnte heute nicht erzeugt werden (claude -p gescheitert); "
                    "die Meldungen stehen vollständig in der Liste."}, True


def export(day, cfg, log, ask=ask_claude, path=None, voll_path=None, reviews=None, local=LOCAL):
    """Schreibt docs/leitstand.json (und, im echten Lauf, local/leitstand-voll.json). Der Bericht
    wird in day['leitstand_report'] gemerkt und nur neu erzeugt, wenn sich die News-/Reddit-
    Einträge geändert haben oder er gescheitert war. Mit eigenem `path` (Tests) gibt es die
    volle Datei nur bei ausdrücklichem `voll_path`."""
    lc = cfg.get("leitstand") or {}
    if path is None:
        voll_path = voll_path or os.path.join(LOCAL, "leitstand-voll.json")
        reviews = load_reviews() if reviews is None else reviews
    items = build_items(day, reviews)
    ids = sorted(i["id"] for i in items if i["rubrik"] in ("news", "reddit"))
    cached = day.get("leitstand_report")
    if cached and cached.get("ids") == ids and not cached.get("fehler"):
        report = {"title": cached["title"], "text": cached["text"]}
    else:
        report, failed = make_report(day["date"], items, lc, lc.get("model", cfg["model"]), log, ask)
        day["leitstand_report"] = {**report, "ids": ids, "fehler": failed}
    data = {"format": FORMAT, "date": day["date"], "report": report, "items": items}
    path = path or os.path.join(ROOT, "docs", "leitstand.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    if voll_path:  # privat; scheitert sie, bleibt der öffentliche Export trotzdem stehen
        try:
            os.makedirs(os.path.dirname(voll_path), exist_ok=True)
            write_voll(day, voll_path, local)
        except (OSError, ValueError) as e:
            log(f"FEHLER volle Leitstand-Datei {voll_path}: {type(e).__name__}: {e}")
    return data


def _no_model(prompt, model):
    raise RuntimeError("Tagesbericht nicht im Cache; ohne Modell nicht neu erzeugbar")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Tag aus archive/items neu exportieren (ohne Modell)")
    ap.add_argument("--date", help="Standard: neuester Tag im Archiv")
    a = ap.parse_args()
    folder = os.path.join(ROOT, "archive", "items")
    day_file = f"{a.date}.json" if a.date else sorted(os.listdir(folder))[-1]
    with open(os.path.join(folder, day_file)) as f:
        day = json.load(f)
    with open(os.path.join(ROOT, "config.json")) as f:
        cfg = json.load(f)
    rep = day.get("leitstand_report") or {}
    if rep.get("fehler") or not rep.get("text"):
        sys.exit("Kein gültiger Tagesbericht im Archiv — erst `python3 radar/run.py --pruefen`.")
    data = export(day, cfg, print, ask=_no_model)
    gh = [i for i in data["items"] if i["review"]]
    print(f"{day['date']}: docs/leitstand.json + local/leitstand-voll.json; "
          f"{sum(i['review'] == 'ungeprueft' for i in gh)} von {len(gh)} Urteilen ungeprüft")
