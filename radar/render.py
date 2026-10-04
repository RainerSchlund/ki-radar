"""Erzeugt das Dashboard (docs/) aus den kuratierten Tagesdaten (archive/items/).

Alle Seiten werden bei jedem Lauf neu erzeugt, damit Vor-/Zurück-Links und
Design-Änderungen überall gleich sind. Inhalt kommt nur aus archive/items/.
"""
import glob
import html
import json
import os
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#16181d;--muted:#5b6170;--line:#e3e6ec;--accent:#3b5bdb;
--gh:#24292f;--rd:#d9480f;--imp3:#c92a2a;--imp2:#e67700;--imp1:#868e96;--chip:#eef1f6}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111317;--card:#1a1d23;
--ink:#e8eaee;--muted:#9aa1ae;--line:#2b3039;--accent:#7b96ff;--gh:#c9d1d9;--rd:#ff8a50;
--imp3:#ff6b6b;--imp2:#ffa94d;--imp1:#868e96;--chip:#252a33}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1200px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:8px}
h1{font-size:22px;margin:0}h1 small{color:var(--muted);font-weight:400;font-size:15px}
nav a{margin-left:14px;font-size:14px}
.lage{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.box h3{margin:0 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 14px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 14px}
.stat b{font-size:20px;display:block}.stat span{color:var(--muted);font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 14px}
.chip{border:1px solid var(--line);background:var(--chip);color:var(--ink);border-radius:999px;
padding:3px 11px;font-size:13px;cursor:pointer}.chip.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:start}
h2{font-size:17px;margin:6px 0 10px;display:flex;align-items:center;gap:8px}
h2 .dot{width:10px;height:10px;border-radius:50%}
.card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--imp1);
border-radius:10px;padding:12px 14px;margin-bottom:10px}
.card.i3{border-left-color:var(--imp3)}.card.i2{border-left-color:var(--imp2)}
.card .t{font-weight:600;font-size:15px;word-break:break-word}
.meta{color:var(--muted);font-size:12.5px;margin:2px 0 6px;display:flex;flex-wrap:wrap;gap:4px 10px}
.cat{background:var(--chip);border-radius:6px;padding:0 7px}
.why{color:var(--muted);font-size:14px;margin-top:4px}.why:before{content:"→ "}
.empty{color:var(--muted);font-style:italic;padding:10px 0}
footer{margin-top:30px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:12px}
table{width:100%;border-collapse:collapse;background:var(--card);border-radius:10px;overflow:hidden}
td,th{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;font-size:14px}
th{font-size:12px;text-transform:uppercase;color:var(--muted)}
td.n{text-align:right;white-space:nowrap}
@media (max-width:760px){.lage,.cols{grid-template-columns:1fr}nav a{margin:0 12px 0 0}}
"""

JS = """
document.querySelectorAll('.chip').forEach(c=>c.addEventListener('click',()=>{
 const on=!c.classList.contains('on');document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));
 if(on)c.classList.add('on');const cat=on?c.dataset.cat:null;
 document.querySelectorAll('.card').forEach(k=>{k.style.display=(!cat||k.dataset.cat===cat)?'':'none'})}));
"""


def esc(s):
    return html.escape(str(s or ""), quote=True)


def long_date(d):
    d = date.fromisoformat(d)
    return f"{WEEKDAYS[d.weekday()]}, {d.day}. {MONTHS[d.month - 1]} {d.year}"


def page(title, body, rel=""):
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 16 16%22><circle cx=%228%22 cy=%228%22 r=%227%22 fill=%22%233b5bdb%22/></svg>">
<style>{CSS}</style></head><body><div class="wrap">{body}</div><script>{JS}</script></body></html>"""


def fmt_num(n):
    return f"{n:,}".replace(",", ".") if isinstance(n, int) else ""


def gh_card(r):
    meta = [f'<span class="cat">{esc(r["category"])}</span>']
    if r.get("stars") is not None:
        meta.append(f"★ {fmt_num(r['stars'])}")
    if r.get("stars_today"):
        meta.append(f"+{fmt_num(r['stars_today'])} heute")
    if r.get("language"):
        meta.append(esc(r["language"]))
    if r.get("created_at"):
        meta.append(f"angelegt {r['created_at'][:10]}")
    return f"""<div class="card i{r['importance']}" data-cat="{esc(r['category'])}">
<div class="t"><a href="{esc(r['url'])}" target="_blank" rel="noopener">{esc(r['full_name'])}</a></div>
<div class="meta">{' · '.join(meta)}</div><div>{esc(r['what'])}</div><div class="why">{esc(r['why'])}</div></div>"""


def rd_card(p):
    meta = [f'<span class="cat">{esc(p["category"])}</span>']
    if p.get("subreddit"):
        meta.append(f"r/{esc(p['subreddit'])}")
    if p.get("author"):
        meta.append(f"u/{esc(p['author'])}")
    links = f'<a href="{esc(p["permalink"])}" target="_blank" rel="noopener">{esc(p["title"])}</a>'
    ext = p.get("external_url")
    extra = ""
    if ext:
        dom = ext.split("/")[2] if "://" in ext else ext
        extra = f' <a href="{esc(ext)}" target="_blank" rel="noopener" class="meta">↗ {esc(dom)}</a>'
    return f"""<div class="card i{p['importance']}" data-cat="{esc(p['category'])}">
<div class="t">{links}{extra}</div>
<div class="meta">{' · '.join(meta)}</div><div>{esc(p['what'])}</div><div class="why">{esc(p['why'])}</div></div>"""


def day_page(d, prev_d, next_d):
    gh, rd = d["github"], d["reddit"]
    cats = []
    for it in gh["items"] + rd["items"]:
        if it["category"] not in cats:
            cats.append(it["category"])
    nav = '<a href="../index.html">Archiv</a>'
    if prev_d:
        nav = f'<a href="{prev_d}.html">← {prev_d}</a>' + nav
    if next_d:
        nav += f'<a href="{next_d}.html">{next_d} →</a>'
    body = f"""<header><h1>KI-Radar <small>{long_date(d['date'])}</small></h1><nav>{nav}</nav></header>
<div class="lage"><div class="box"><h3>GitHub heute</h3>{esc(gh['headline'])}</div>
<div class="box"><h3>Reddit heute</h3>{esc(rd['headline'])}</div></div>
<div class="stats"><div class="stat"><b>{len(gh['items'])}</b><span>Repos ausgewählt</span></div>
<div class="stat"><b>{len(rd['items'])}</b><span>Beiträge ausgewählt</span></div>
<div class="stat"><b>{gh['candidates']}</b><span>neue Repos geprüft</span></div>
<div class="stat"><b>{rd['candidates']}</b><span>neue Beiträge geprüft</span></div></div>
<div class="chips">{''.join(f'<button class="chip" data-cat="{esc(c)}">{esc(c)}</button>' for c in cats)}</div>
<div class="cols"><section><h2><span class="dot" style="background:var(--gh)"></span>GitHub · Repos</h2>
{''.join(gh_card(r) for r in gh['items']) or '<div class="empty">Heute nichts Neues von Belang.</div>'}</section>
<section><h2><span class="dot" style="background:var(--rd)"></span>Reddit · Blogs, Meinungen, Berichte</h2>
{''.join(rd_card(p) for p in rd['items']) or '<div class="empty">Heute nichts Neues von Belang.</div>'}</section></div>
<footer>Linke Randfarbe = Wichtigkeit (rot: heute ansehen, orange: lohnend, grau: zur Kenntnis).
Jeder Eintrag erscheint nur einmal; das Archiv merkt sich, was schon gezeigt wurde.<br>
Quellenstatus: GitHub {gh['fetched']} abgerufen, {len(gh['failures'])} Fehler · Reddit {rd['fetched']} abgerufen,
{len(rd['failures'])} Fehler{(' — ' + esc('; '.join((gh['failures'] + rd['failures'])[:6]))) if gh['failures'] or rd['failures'] else ''}<br>
Erzeugt {esc(d['generated'])}</footer>"""
    return page(f"KI-Radar {d['date']}", body)


def index_page(days, status):
    rows = "".join(
        f"""<tr><td><a href="days/{d['date']}.html">{long_date(d['date'])}</a></td>
<td class="n">{len(d['github']['items'])}</td><td class="n">{len(d['reddit']['items'])}</td>
<td>{esc(d['github']['headline'])} {esc(d['reddit']['headline'])}</td></tr>""" for d in reversed(days))
    latest = f'<p>Neueste Ausgabe: <a href="days/{days[-1]["date"]}.html">{long_date(days[-1]["date"])}</a></p>' if days else ""
    body = f"""<header><h1>KI-Radar <small>Archiv</small></h1></header>
<p style="color:var(--muted)">Tägliches Briefing zu KI in Software- und Spieleentwicklung aus GitHub und Reddit.
Zuletzt geprüft: {esc(status.get('last_check', '–'))} ({esc(status.get('last_result', ''))}). Tage ohne Neuigkeiten erscheinen hier nicht.</p>
{latest}<table><tr><th>Datum</th><th>Repos</th><th>Beiträge</th><th>Tageslage</th></tr>{rows}</table>"""
    return page("KI-Radar", body)


def render_all(status):
    days = []
    for p in sorted(glob.glob(os.path.join(ROOT, "archive", "items", "*.json"))):
        with open(p) as f:
            d = json.load(f)
        if d["github"]["items"] or d["reddit"]["items"]:
            days.append(d)
    os.makedirs(os.path.join(ROOT, "docs", "days"), exist_ok=True)
    for i, d in enumerate(days):
        prev_d = days[i - 1]["date"] if i else None
        next_d = days[i + 1]["date"] if i + 1 < len(days) else None
        with open(os.path.join(ROOT, "docs", "days", f"{d['date']}.html"), "w") as f:
            f.write(day_page(d, prev_d, next_d))
    with open(os.path.join(ROOT, "docs", "index.html"), "w") as f:
        f.write(index_page(days, status))
    return days


if __name__ == "__main__":
    render_all({"last_check": datetime.now().strftime("%Y-%m-%d %H:%M")})
