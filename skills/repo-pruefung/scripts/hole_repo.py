"""Holt ein GitHub-Repo in ein Wegwerf-Verzeichnis und baut einen Lese-Auszug daraus.

  python3 -I skills/repo-pruefung/scripts/hole_repo.py owner/name [auszug.json]

Das Repo ist ungeprüfte Fremddaten: Es wird nur gelesen — nichts ausgeführt, nichts
installiert, keine Submodule, kein LFS, Symlinks werden als Textdateien angelegt
(core.symlinks=false) und beim Lesen zusätzlich übersprungen.
Ergebnis: {"repo", "files": [alle Pfade], "tree": "...", "excerpts": [{"path","text"}]}
"""
import json
import os
import re
import subprocess
import sys
import tempfile

TREE_MAX = 400          # Pfade im Dateibaum für den Prompt
FILE_MAX = 12000        # Zeichen je Datei
README_MAX = 20000
TOTAL_MAX = 90000       # Zeichen aller Auszüge zusammen
SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv"}
TEXT_EXT = {".md", ".py", ".ts", ".tsx", ".js", ".mjs", ".rs", ".go", ".java", ".kt", ".cs",
            ".rb", ".sh", ".toml", ".json", ".yaml", ".yml", ".txt", ".gd", ".cpp", ".c", ".h",
            ".hpp", ".lua", ".swift", ".zig", ".ex", ".php"}
# Dateien, die über Zweck und Aufbau am meisten verraten — in dieser Reihenfolge.
KEY_PATTERNS = [r"(^|/)SKILL\.md$", r"^(CLAUDE|AGENTS)\.md$", r"^\.claude-plugin/plugin\.json$",
                r"^(package\.json|pyproject\.toml|Cargo\.toml|go\.mod|setup\.py)$",
                r"^(src/)?(main|index|cli|app|server|agent)\.[a-z]+$",
                r"^(docs?/)[^/]+\.md$", r"^\.claude/(commands|agents)/[^/]+\.md$"]
SRC_DIRS = re.compile(r"^(src|lib|packages|crates|cmd|internal|app|[a-z_]+)/")


def clone(full_name, dest, run=subprocess.run, timeout=180):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ValueError(f"ungültiger Repo-Name: {full_name!r}")
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    cmd = ["git", "-c", "core.symlinks=false", "-c", "protocol.file.allow=never",
           "clone", "--depth", "1", "--single-branch", "--no-tags", "--filter=blob:limit=1m",
           f"https://github.com/{full_name}.git", dest]
    res = run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"git clone {full_name} exit {res.returncode}: {res.stderr[-300:]}")


def list_files(root):
    out = []
    for d, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS)
        for f in sorted(files):
            full = os.path.join(d, f)
            if not os.path.islink(full):
                out.append(os.path.relpath(full, root))
    return out


def read(root, rel, limit):
    full = os.path.realpath(os.path.join(root, rel))
    if not full.startswith(os.path.realpath(root) + os.sep) or os.path.islink(os.path.join(root, rel)):
        return None
    try:
        with open(full, "rb") as f:
            raw = f.read(limit * 2)
    except OSError:
        return None
    if b"\0" in raw[:2000]:
        return None  # binär
    text = raw.decode("utf-8", "replace")
    return text[:limit] + ("\n[… gekürzt]" if len(text) > limit else "")


def choose(files):
    """Reihenfolge der Auszüge: README, Schlüsseldateien, dann größte Quelltexte nach Ordner."""
    picked = [f for f in files if re.fullmatch(r"README(\.[a-z]+)?", f, re.I)][:1]
    for pat in KEY_PATTERNS:
        for f in files:
            if re.search(pat, f) and f not in picked:
                picked.append(f)
    return picked[:14]


def digest(root, full_name):
    files = list_files(root)
    excerpts, total = [], 0
    chosen = choose(files)
    src = [f for f in files if os.path.splitext(f)[1] in TEXT_EXT and SRC_DIRS.match(f)
           and f not in chosen and not re.search(r"(test|spec|example|fixture)", f, re.I)]
    src.sort(key=lambda f: -os.path.getsize(os.path.join(root, f)))
    for rel in chosen + src[:6]:
        limit = README_MAX if rel.upper().startswith("README") else FILE_MAX
        text = read(root, rel, min(limit, TOTAL_MAX - total))
        if not text:
            continue
        excerpts.append({"path": rel, "text": text})
        total += len(text)
        if total >= TOTAL_MAX:
            break
    tree = "\n".join(files[:TREE_MAX]) + (f"\n[… {len(files) - TREE_MAX} weitere]" if len(files) > TREE_MAX else "")
    return {"repo": full_name, "files": files, "tree": tree, "excerpts": excerpts}


def fetch(full_name, run=subprocess.run):
    with tempfile.TemporaryDirectory(prefix="ki-radar-repo-") as tmp:
        dest = os.path.join(tmp, "repo")
        clone(full_name, dest, run=run)
        return digest(dest, full_name)


if __name__ == "__main__":
    d = fetch(sys.argv[1])
    out = json.dumps(d, indent=1, ensure_ascii=False)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w") as f:
            f.write(out)
    else:
        print(out)
    print(f"{len(d['files'])} Dateien, {len(d['excerpts'])} Auszüge", file=sys.stderr)
