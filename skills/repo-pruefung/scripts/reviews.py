"""Reviews der Repo-Prüfungen auswerten: Übersicht + Regressionsfälle.

  python3 skills/repo-pruefung/scripts/reviews.py [local/reviews] [local/pruefungen]
      → local/reviews/uebersicht.md            (Trefferquote je Teil, häufigste Korrekturen)
      → local/reviews/regression/<id>.json     (je als falsch/teilweise markierte Prüfung)

Eingang: local/reviews/<id>.json (schreibt `leitstand radar reviews`, Format repo-pruefung-review/1):
  {id, repo, datum, bericht, review: {status, teile_falsch, korrektur, at}}
Alles bleibt in local/ (gitignored): Berichte und Korrekturen können Skill-Namen enthalten.

Ein Regressionsfall wird zum Test, sobald jemand eine neue Pflicht in pruefschema.validate
schreibt und im Fall `erwartung` setzt: {"ungueltig": true} (validate muss werfen) oder
{"warnung_enthaelt": "..."} (eine Warnung muss den Text enthalten). Neu erzeugte Fälle
behalten eine schon gesetzte `erwartung`. tests/test_radar.py spielt alle lokalen Fälle mit
`erwartung` nach (ReviewRegressionLocalTest).
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pruefschema  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LOCAL = os.path.join(ROOT, "local")
TEILE = ("vergleichbar", "besser", "adaptierbar", "urteil", "belege")
STATUS = ("stimmt", "teilweise", "falsch")
CASE_FORMAT = "repo-pruefung-regression/1"


def load(review_dir):
    out = []
    for p in sorted(glob.glob(os.path.join(review_dir, "*.json"))):
        with open(p) as f:
            r = json.load(f)
        rv = r.get("review") or {}
        if rv.get("status") in STATUS:
            out.append(r)
    return out


def wrong_parts(review):
    """Welche Teile gelten als falsch. 'falsch' ohne Angabe heißt: das Urteil ist falsch."""
    teile = [t for t in (review.get("teile_falsch") or []) if t in TEILE]
    if review["status"] == "falsch" and not teile:
        return ["urteil"]
    return [] if review["status"] == "stimmt" else teile


def summary(reviews):
    """Trefferquote je Teil: richtig / bewertet. Ein 'teilweise' ohne markierte Teile
    sagt über keinen Teil etwas und zählt nur in `ohne_angabe`."""
    teile = {t: {"bewertet": 0, "falsch": 0, "korrekturen": []} for t in TEILE}
    status = {s: 0 for s in STATUS}
    ohne_angabe = 0
    for r in reviews:
        rv = r["review"]
        status[rv["status"]] += 1
        wrong = wrong_parts(rv)
        if rv["status"] == "teilweise" and not wrong:
            ohne_angabe += 1
            continue
        for t in TEILE:
            teile[t]["bewertet"] += 1
            if t in wrong:
                teile[t]["falsch"] += 1
                if (rv.get("korrektur") or "").strip():
                    teile[t]["korrekturen"].append({"id": r["id"], "repo": r.get("repo"),
                                                    "text": rv["korrektur"].strip()})
    for t in teile.values():
        t["quote"] = round(1 - t["falsch"] / t["bewertet"], 3) if t["bewertet"] else None
    return {"n": len(reviews), "status": status, "ohne_angabe": ohne_angabe, "teile": teile}


def markdown(s):
    lines = ["# Reviews der Repo-Prüfung", "",
             f"{s['n']} Reviews: " + ", ".join(f"{n} {k}" for k, n in s["status"].items())
             + (f"; {s['ohne_angabe']} × teilweise ohne markierten Teil" if s["ohne_angabe"] else ""), "",
             "| Teil | bewertet | falsch | Trefferquote |", "|---|---|---|---|"]
    for t, v in s["teile"].items():
        q = f"{v['quote']:.0%}" if v["quote"] is not None else "–"
        lines.append(f"| {t} | {v['bewertet']} | {v['falsch']} | {q} |")
    lines += ["", "## Häufigste Korrekturen (Teil mit den meisten Fehlern zuerst)", ""]
    ranked = sorted(s["teile"].items(), key=lambda kv: -kv[1]["falsch"])
    for t, v in ranked:
        if not v["falsch"]:
            continue
        lines.append(f"### {t} ({v['falsch']}× falsch)")
        lines += [f"- {k['repo'] or k['id']}: {k['text']}" for k in v["korrekturen"]] or ["- (ohne Korrekturtext)"]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _pruefung(r, pruef_dir):
    """Original-Lauf aus local/pruefungen/<datum>/<owner__name>.json, falls noch da."""
    if not r.get("repo") or not r.get("datum"):
        return None
    p = os.path.join(pruef_dir, r["datum"], r["repo"].replace("/", "__") + ".json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def case_for(r, pruef_dir, old=None):
    """Regressionsfall: Eingabe zum Nachspielen (roh + Dateiliste + Skill-Namen) und das Review-Urteil.
    Ältere Läufe ohne `dateien` bekommen die Auszugs- und Belegdateien als Näherung."""
    run = _pruefung(r, pruef_dir) or {}
    bericht = r.get("bericht") or run.get("bericht") or {}
    files = run.get("dateien")
    if not files:
        files = set(run.get("auszug_dateien") or [])
        for k, key in (("besser", "beleg"), ("adaptierbar", "beleg"), ("belege", "datei")):
            files |= {e.get(key) for e in bericht.get(k) or [] if isinstance(e, dict) and e.get(key)}
        files = sorted(files)
    skills = run.get("skills") or sorted({v.get("skill") for v in bericht.get("vergleichbar") or []
                                          if isinstance(v, dict) and v.get("skill")})
    return {"format": CASE_FORMAT, "id": r["id"], "repo": r.get("repo"), "datum": r.get("datum"),
            "review": r["review"], "falsche_teile": wrong_parts(r["review"]),
            "eingabe": {"roh": run.get("roh") or bericht, "dateien": files, "skills": skills,
                        "roh_ist_original": bool(run.get("roh"))},
            "bericht": bericht, "erwartung": (old or {}).get("erwartung")}


def write_cases(reviews, out_dir, pruef_dir):
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for r in reviews:
        if r["review"]["status"] == "stimmt":
            continue
        path = os.path.join(out_dir, r["id"] + ".json")
        old = None
        if os.path.exists(path):
            with open(path) as f:
                old = json.load(f)
        with open(path, "w") as f:
            json.dump(case_for(r, pruef_dir, old), f, indent=1, ensure_ascii=False)
        written.append(path)
    return written


def check_case(case, sperr=()):
    """None = noch keine Erwartung gesetzt; sonst (ok, meldung)."""
    exp = case.get("erwartung")
    if not exp:
        return None
    e = case["eingabe"]
    try:
        out = pruefschema.validate(e["roh"], e["dateien"], set(e["skills"]), sperr)
    except pruefschema.Ungueltig as err:
        return (bool(exp.get("ungueltig")), f"ungültig: {err}")
    if exp.get("ungueltig"):
        return (False, "validate hätte werfen müssen")
    needle = exp.get("warnung_enthaelt")
    if needle:
        hit = any(needle in w for w in out["warnungen"])
        return (hit, "Warnung gefunden" if hit else f"keine Warnung mit {needle!r}: {out['warnungen']}")
    return (True, "gültig")


def main(review_dir, pruef_dir):
    os.makedirs(review_dir, exist_ok=True)
    reviews = load(review_dir)
    s = summary(reviews)
    with open(os.path.join(review_dir, "uebersicht.md"), "w") as f:
        f.write(markdown(s))
    cases = write_cases(reviews, os.path.join(review_dir, "regression"), pruef_dir)
    print(markdown(s))
    print(f"{len(cases)} Regressionsfall/-fälle in {os.path.join(review_dir, 'regression')}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(LOCAL, "reviews"),
         sys.argv[2] if len(sys.argv) > 2 else os.path.join(LOCAL, "pruefungen"))
