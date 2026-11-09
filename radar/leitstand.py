"""Export für den Leitstand: docs/leitstand.json (Format ki-radar-leitstand/1).

items  = alle Einträge des Tages (News, Reddit, GitHub) mit über Tage stabiler ID
report = zusammenhängender deutscher Bericht über News + Reddit (eigener `claude -p`-Aufruf),
         der jede erwähnte Meldung mit [[<id>]] referenziert. Code prüft die IDs: erfundene
         IDs → ungültig (ein zweiter Versuch, dann Ersatztext); fehlende/Länge → Warnung.
"""
import hashlib
import json
import os
import re

from curate import ask_claude

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORMAT = "ki-radar-leitstand/1"
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


def build_items(day):
    out = []
    for rubrik in ("news", "reddit", "github"):
        for it in (day.get(rubrik) or {}).get("items", []):
            gh = rubrik == "github"
            out.append({
                "id": item_id(rubrik, day["date"], it["key"]),
                "rubrik": rubrik,
                "title": (it.get("headline_de") or it.get("title")) if not gh else it["full_name"],
                "url": it.get("permalink") if rubrik == "reddit" else it["url"],
                "what": it.get("what", ""),
                "importance": min(3, max(1, int(it.get("importance") or 1))),
                "source": _source(rubrik, it),
                "einsatz": it.get("einsatz") if gh else None,
                "urteil": it.get("urteil") if gh else None,
                "urteil_kurz": _urteil_kurz(it) if gh else None,
            })
    return out


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


def export(day, cfg, log, ask=ask_claude, path=None):
    """Schreibt docs/leitstand.json. Der Bericht wird in day['leitstand_report'] gemerkt und nur
    neu erzeugt, wenn sich die News-/Reddit-Einträge geändert haben oder er gescheitert war."""
    lc = cfg.get("leitstand") or {}
    items = build_items(day)
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
    return data
