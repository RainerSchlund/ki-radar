"""Kuratierung per `claude -p`: wählt aus, ordnet ein, fasst auf Deutsch zusammen.

Das Modell bekommt nur Kurz-IDs (g1, r7 …) und gibt nur IDs zurück; Links,
Sterne und Autoren kommen aus den Abrufdaten. So kann kein erfundener Link
im Dashboard landen.
"""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYSTEM = ("Du bist ein Redaktionswerkzeug in einer automatischen Pipeline. "
          "Deine Ausgabe wird maschinell als JSON geparst. Gib ausschließlich das "
          "geforderte JSON-Objekt aus — keine Erklärungen, keine Selbstreflexion, "
          "keinen Markdown-Zaun.")


def github_line(i, r):
    return json.dumps({
        "id": f"g{i}", "repo": r["full_name"], "description": r.get("description"),
        "stars": r.get("stars"), "stars_today": r.get("stars_today"),
        "language": r.get("language"), "topics": (r.get("topics") or [])[:8],
        "created": (r.get("created_at") or "")[:10], "found_via": r["sources"][:4],
    }, ensure_ascii=False)


def reddit_line(i, p):
    ext = p.get("external_url")
    return json.dumps({
        "id": f"r{i}", "title": p["title"], "subreddit": p.get("subreddit"),
        "author": p.get("author"), "rank": p.get("rank"), "found_via": p["sources"][:4],
        "links_to": re.sub(r"^https?://", "", ext)[:120] if ext else None,
        "text": (p.get("text") or "")[:400],
    }, ensure_ascii=False)


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError("keine JSON-Ausgabe: " + text[:200])
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def ask_claude(prompt, model, timeout=900):
    cmd = ["claude", "-p", "--model", model, "--output-format", "json",
           "--tools", "", "--no-session-persistence", "--system-prompt", SYSTEM]
    res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                         timeout=timeout, cwd=ROOT)
    if res.returncode != 0:
        raise RuntimeError(f"claude -p exit {res.returncode}: {res.stderr[-500:]}"
                           f" {res.stdout[-500:]}")
    wrapper = json.loads(res.stdout)
    if wrapper.get("is_error"):
        raise RuntimeError(f"claude -p Fehler: {wrapper.get('result')}")
    return extract_json(wrapper["result"])


def curate(kind, candidates, model, max_items=20, ask=ask_claude):
    """kind = 'github' | 'reddit'. Gibt (headline, ausgewählte Items) zurück."""
    if not candidates:
        return "Keine neuen Kandidaten.", []
    line = github_line if kind == "github" else reddit_line
    prefix = "g" if kind == "github" else "r"
    with open(os.path.join(ROOT, "prompts", f"{kind}.md")) as f:
        prompt = f.read().replace("{max_items}", str(max_items)) + "\n".join(line(i, c) for i, c in enumerate(candidates))
    answer = ask(prompt, model)
    by_id = {f"{prefix}{i}": c for i, c in enumerate(candidates)}
    picked, seen = [], set()
    for sel in answer.get("items", []):
        c = by_id.get(sel.get("id"))
        if not c or c["key"] in seen:
            continue
        seen.add(c["key"])
        picked.append({**c, "category": sel.get("category") or "Sonstiges",
                       "what": sel.get("what", ""), "why": sel.get("why", ""),
                       "importance": int(sel.get("importance") or 1)})
    picked.sort(key=lambda x: -x["importance"])  # stabil: Modell-Reihenfolge bleibt je Stufe
    return answer.get("headline", ""), picked[:max_items]
