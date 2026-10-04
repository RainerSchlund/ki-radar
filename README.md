# KI-Radar

Tägliches Briefing zu KI in Software- und Spieleentwicklung — Tools, Coding-Agenten,
Harnesses, Modelle, Gedächtnis, persönliche Agenten. Zwei Quellen, getrennt beobachtet:

- **GitHub:** Trending-Seiten (alle Sprachen + Python, TypeScript, Rust, Go, C#, C++) und
  Suche nach Repos, die in den letzten 7 Tagen angelegt wurden und schnell Sterne sammeln
  (Suchbegriffe in `config.json`, u. a. Agent-Memory, persönliche Agenten, MCP, Harnesses, Game-AI).
- **Reddit:** Top-Beiträge des Tages aus einschlägigen Subreddits und Beiträge, die auf Blogs
  bekannter Stimmen verlinken (Domain-Liste in `config.json`).

Ergebnis: Dashboard auf https://rainerschlund.github.io/ki-radar/ — pro Tag mit Neuigkeiten eine
Seite, dazu eine Mail (GitHub-Benachrichtigung) mit Direktlink.

## Ablauf

```
systemd-Timer (07:00, 12:00, 17:00; holt verpasste Termine nach)
  └─ radar/run.py  – höchstens ein wirksamer Lauf pro Tag
       ├─ fetch_github.py / fetch_reddit.py   abrufen (reines I/O)
       ├─ archive.py      schon Gezeigtes und kürzlich Aussortiertes herausfiltern
       ├─ curate.py       claude -p wählt aus, ordnet ein, fasst auf Deutsch zusammen
       │                  (je Quelle ein eigener Aufruf; Modell gibt nur IDs zurück,
       │                   Links stammen immer aus den Abrufdaten)
       ├─ render.py       docs/ (GitHub Pages) neu erzeugen
       └─ git push        → .github/workflows/notify.yml legt ein Issue mit Link an
                            → GitHub schickt die Mail
```

Tage ohne Neuigkeiten erzeugen keine Seite und keine Mail; die Startseite zeigt trotzdem,
wann zuletzt geprüft wurde.

## Archiv

- `archive/seen.json` — jeder je geprüfte Kandidat. `reported` = wurde gezeigt, kommt nie wieder.
  `rejected` = aussortiert, wird nach `reject_cooldown_days` erneut geprüft (falls ein Repo später
  doch relevant wird). Ein gezeigter Blogartikel sperrt auch andere Reddit-Beiträge mit demselben Link.
- `archive/items/<datum>.json` — kuratierte Tagesausgabe; die HTML-Seiten werden daraus erzeugt.

## Bedienung

```
python3 radar/run.py               # Tageslauf (macht nichts, wenn heute schon gelaufen)
python3 radar/run.py --no-publish  # ohne git push
python3 radar/run.py --render      # nur HTML neu erzeugen (z. B. nach Design-Änderung)
python3 -m unittest tests/test_radar.py
systemd/install.sh                 # Timer installieren
journalctl --user -u ki-radar      # Laufprotokoll; zusätzlich logs/run.log
```

Quellen, Suchbegriffe und Modell stehen in `config.json`, die Auswahlkriterien in `prompts/`.

## Grenzen

- Reddit erlaubt ohne Anmeldung etwa einen Abruf pro Minute; deshalb sind die Feeds gebündelt
  und der Lauf dauert einige Minuten.
- Läuft nur, wenn der Laptop an ist (dann aber nachholend). Nutzt das Claude-Abo über `claude -p`.
- Die Mail kommt nur, wenn in den GitHub-Einstellungen E-Mail-Benachrichtigungen für
  „Watching“/„Participating“ aktiv sind.
