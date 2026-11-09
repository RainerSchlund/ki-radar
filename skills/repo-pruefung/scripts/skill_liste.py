"""Erzeugt die Liste vorhandener Skills (Name, Herkunft, Beschreibung) als JSON.

  python3 skills/repo-pruefung/scripts/skill_liste.py [ausgabe.json]   # Standard: local/skills.json

Quellen: ~/.claude*/skills, ~/.config/cs/profiles.d/*/skills, Plugin-Skills unter
~/.claude*/plugins, dazu ein Firmen-Skill-Katalog (`node <skript> catalog --json`;
Pfad zum Skript in local/katalog.txt, nur wenn vorhanden und erreichbar). Die Datei bleibt lokal (local/ ist gitignored) — sie enthält Profil-
und Plugin-Namen, die nicht ins öffentliche Repo gehören.
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CATALOG_CFG = os.path.join(ROOT, "local", "katalog.txt")  # eine Zeile: Pfad zu skill-share.mjs
DESC_MAX = 300


def frontmatter(text):
    """Liest name/description aus YAML-Frontmatter (einfacher Teil-Parser, auch für | und >)."""
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out, key, block = {}, None, []
    for line in m.group(1).splitlines():
        top = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if top:
            if key and block:
                out[key] = " ".join(block)
            key, val = top.group(1), top.group(2).strip()
            block = [] if val in ("|", ">", "|-", ">-", "") else [val.strip("'\"")]
        elif key and line.strip():
            block.append(line.strip())
    if key and block:
        out[key] = " ".join(block)
    return out


def herkunft(path):
    p = path.replace(HOME, "~")
    if "/plugins/" in p:
        m = re.search(r"/plugins/(?:cache|marketplaces)/[^/]+/(?:plugins/)?([^/]+)", p)
        return "plugin:" + (m.group(1) if m else "?")
    if "/profiles.d/" in p:
        return "profil:" + p.split("/profiles.d/")[1].split("/")[0]
    return "eigen"


def local_skills():
    patterns = [os.path.join(HOME, ".claude*", "skills", "*", "SKILL.md"),
                os.path.join(HOME, ".claude*", "skills", "*", "*", "SKILL.md"),  # Sammelordner
                os.path.join(HOME, ".config", "cs", "profiles.d", "*", "skills", "*", "SKILL.md"),
                os.path.join(HOME, ".claude*", "plugins", "**", "SKILL.md")]
    found, notes = [], []
    for pat in patterns:
        for path in sorted(glob.glob(pat, recursive=True)):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    fm = frontmatter(f.read(4000))
            except OSError as e:  # z. B. kaputter Symlink
                notes.append(f"unlesbar: {os.path.basename(os.path.dirname(path))} ({e.strerror})")
                continue
            name = fm.get("name") or os.path.basename(os.path.dirname(path))
            found.append({"name": name, "herkunft": herkunft(path),
                          "description": (fm.get("description") or "")[:DESC_MAX]})
    return found, notes


def catalog_script():
    try:
        with open(CATALOG_CFG) as f:
            return os.path.expanduser(f.read().strip())
    except OSError:
        return None


def company_catalog(run=subprocess.run, script=None):
    script = script or catalog_script()
    if not script or not os.path.exists(script):
        return [], [f"Firmen-Katalog nicht vorhanden ({CATALOG_CFG} fehlt oder Skript nicht da)"]
    try:
        res = run(["node", script, "catalog", "--json"], capture_output=True, text=True, timeout=90)
        text = res.stdout
        data = json.loads(text[text.index("["):])
    except Exception as e:
        return [], [f"Firmen-Katalog nicht erreichbar: {type(e).__name__}: {str(e)[:200]}"]
    out = []
    for plugin in data:
        for s in plugin.get("skills") or []:
            out.append({"name": s.get("name"), "herkunft": "katalog:" + str(plugin.get("name")),
                        "description": (s.get("description") or "")[:DESC_MAX]})
    return out, []


def build(path=None, catalog=company_catalog):
    path = path or os.path.join(ROOT, "local", "skills.json")
    skills, notes = local_skills()
    cat, cat_notes = catalog()
    merged = {}
    for s in skills + cat:  # gleicher Name in mehreren Profilen/Versionen → ein Eintrag
        if not s["name"]:
            continue
        e = merged.setdefault(s["name"], {"name": s["name"], "herkunft": [], "description": ""})
        if s["herkunft"] not in e["herkunft"]:
            e["herkunft"].append(s["herkunft"])
        if len(s["description"]) > len(e["description"]):
            e["description"] = s["description"]
    data = {"erzeugt": datetime.now().strftime("%Y-%m-%d %H:%M"), "hinweise": notes + cat_notes,
            "skills": sorted(merged.values(), key=lambda s: s["name"])}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    return data


if __name__ == "__main__":
    d = build(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"{len(d['skills'])} Skills; Hinweise: {d['hinweise'] or 'keine'}", file=sys.stderr)
