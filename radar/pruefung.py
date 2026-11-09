"""Gründliche Prüfung der Top-N-GitHub-Repos des Tages über den Skill skills/repo-pruefung.

Pro Repo: flach klonen (Fremddaten, nur lesen) → Auszug → `claude -p` mit dem Prüfauftrag
aus SKILL.md → Code prüft Schema und Belege. Der volle Bericht bleibt in local/pruefungen/;
ans öffentliche Item gehen nur urteil, verwendung, urteil_kurz.

Scheitert eine Prüfung (Klonen, Zeitüberschreitung, leere/ungültige Antwort), wird das
sichtbar geloggt und am Item als pruefung="fehler" vermerkt — der Lauf geht weiter.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "repo-pruefung", "scripts"))
import hole_repo  # noqa: E402
import pruefschema  # noqa: E402
import skill_liste  # noqa: E402
from curate import ask_claude  # noqa: E402

LOCAL = os.path.join(ROOT, "local")


def signal(item):
    return (item.get("importance") or 0, item.get("stars_today") or 0, item.get("stars") or 0)


def top_n(items, n):
    """Die n stärksten Repos: Wichtigkeit, dann Sterne heute, dann Sterne gesamt.
    Schon Geprüftes (z. B. bei --only github) zählt nicht noch einmal."""
    todo = [i for i in items if not i.get("pruefung")]
    return sorted(todo, key=signal, reverse=True)[:n]


def review_one(item, skills, model, sperr, fetch=hole_repo.fetch, ask=ask_claude, outdir=None):
    """Gibt den bereinigten Bericht zurück oder wirft (Aufrufer loggt)."""
    auszug = fetch(item["full_name"])
    answer = ask(pruefschema.prompt(skills, auszug), model)
    names = {s["name"] for s in skills["skills"]}
    report = pruefschema.validate(answer, auszug["files"], names, sperr)
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        name = item["full_name"].replace("/", "__")
        with open(os.path.join(outdir, name + ".json"), "w") as f:
            json.dump({"repo": item["full_name"], "bericht": report, "roh": answer,
                       "auszug_dateien": [e["path"] for e in auszug["excerpts"]]},
                      f, indent=1, ensure_ascii=False)
    return report


def review_top(items, cfg, today, log, fetch=hole_repo.fetch, ask=None,
               build_skills=skill_liste.build, local=LOCAL):
    """Prüft die Top-N aus items (in place). Gibt die Namen der Repos zurück, deren Prüfung
    scheiterte (öffentlich unbedenklich; die Fehlertexte stehen nur im Log)."""
    pc = cfg.get("pruefung") or {}
    chosen = top_n(items, pc.get("top_n", 5))
    timeout = pc.get("timeout_seconds", 900)
    ask = ask or (lambda p, m: ask_claude(p, m, timeout=timeout))
    if not chosen:
        return []
    errors = []
    try:
        skills = build_skills(os.path.join(local, "skills.json"))
    except Exception as e:  # ohne Skill-Liste ist der Vergleich wertlos → ganz auslassen
        msg = f"Repo-Prüfung ausgelassen: Skill-Liste nicht erzeugbar ({type(e).__name__}: {e})"
        log("FEHLER " + msg)
        for it in chosen:
            it["pruefung"] = "fehler"
        return [it["full_name"] for it in chosen]
    for h in skills.get("hinweise", []):
        log(f"Skill-Liste: {h}")
    sperr_path = os.path.join(local, "sperrliste.txt")
    sperr = pruefschema.load_sperrliste(sperr_path)
    if not sperr:
        log(f"WARNUNG: keine Sperrliste ({sperr_path}) — öffentliche Kurzbegründung nur auf Pfade/URLs geprüft")
    outdir = os.path.join(local, "pruefungen", today.isoformat())
    run = partial(review_one, skills=skills, model=pc.get("model", cfg["model"]), sperr=sperr,
                  fetch=fetch, ask=ask, outdir=outdir)
    log(f"Repo-Prüfung: {', '.join(i['full_name'] for i in chosen)}")
    with ThreadPoolExecutor(max(1, pc.get("parallel", 2))) as ex:
        jobs = [(it, ex.submit(run, it)) for it in chosen]
        for it, job in jobs:
            try:
                rep = job.result()
            except Exception as e:
                msg = f"Prüfung {it['full_name']}: {type(e).__name__}: {str(e)[:300]}"
                log("FEHLER " + msg)
                errors.append(it["full_name"])
                it.update(pruefung="fehler", urteil=None, verwendung=None, urteil_kurz=None)
                continue
            it.update(pruefung="ok", urteil=rep["urteil"], verwendung=rep["verwendung"],
                      urteil_kurz=rep["kurz_oeffentlich"])
            log(f"geprüft {it['full_name']}: {rep['urteil']}"
                f"{' (' + rep['verwendung'] + ')' if rep['verwendung'] else ''}"
                f"{'; Warnungen: ' + '; '.join(rep['warnungen']) if rep['warnungen'] else ''}")
    return errors
