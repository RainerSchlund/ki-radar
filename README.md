# KI-Radar

Tägliches Briefing zu KI in Software- und Spieleentwicklung — Tools, Coding-Agenten,
Harnesses, Modelle, Gedächtnis, persönliche Agenten. Drei Rubriken, jede getrennt abgerufen
und kuratiert:

- **News des Tages:** 44 Feeds (Hersteller wie OpenAI, DeepMind, Hugging Face, GitHub;
  Stimmen wie Simon Willison, Latent Space, Martin Fowler; Fachmedien wie The Verge, Ars
  Technica, heise, The Decoder, golem; Spieleentwicklung wie Game Developer, 80 Level, Unity,
  Godot; YouTube-Kanäle), Google-News-Suchen und populäre Hacker-News-Beiträge. Dieselbe
  Geschichte aus anderer Quelle wird über die Überschriften der letzten 7 Tage erkannt.

Daneben gezielt beobachtet:

- **GitHub:** Trending-Seiten (alle Sprachen + Python, TypeScript, Rust, Go, C#, C++) und
  Suche nach Repos, die in den letzten 7 Tagen angelegt wurden und schnell Sterne sammeln
  (Suchbegriffe in `config.json`, u. a. Agent-Memory, persönliche Agenten, MCP, Harnesses, Game-AI).
- **Reddit:** Top-Beiträge des Tages aus einschlägigen Subreddits und Beiträge, die auf Blogs
  bekannter Stimmen verlinken (Domain-Liste in `config.json`).

Jedes gezeigte Repo bekommt eine Einsatz-Rubrik „Wofür einsetzbar“ (feste Liste in `config.json`,
Feld `einsatz`, mit Begründung). Die **Top 5 Repos des Tages** (Wichtigkeit, dann Sterne heute, dann
Sterne) prüft ein eigener `claude -p`-Lauf gründlich gegen die vorhandenen Skills — siehe
[Repo-Prüfung](#repo-prüfung). Die übrigen Repos haben nur Rubrik und Kurzeinordnung.

Ergebnis: Dashboard auf https://rainerschlund.github.io/ki-radar/ — pro Tag mit Neuigkeiten eine
Seite, dazu eine Mail (GitHub-Benachrichtigung) mit Direktlink.

## Ablauf

```
systemd-Timer (07:00, 12:00, 17:00; holt verpasste Termine nach)
  └─ radar/run.py  – höchstens ein wirksamer Lauf pro Tag
       ├─ fetch_news.py / fetch_github.py / fetch_reddit.py   abrufen (reines I/O)
       ├─ archive.py      schon Gezeigtes und kürzlich Aussortiertes herausfiltern
       ├─ curate.py       claude -p wählt aus, ordnet ein, fasst auf Deutsch zusammen
       │                  (je Quelle ein eigener Aufruf; Modell gibt nur IDs zurück,
       │                   Links stammen immer aus den Abrufdaten)
       ├─ pruefung.py     Top 5 Repos gründlich prüfen (skills/repo-pruefung, je ein claude -p)
       ├─ leitstand.py    docs/leitstand.json + Tagesbericht über News/Reddit (claude -p)
       ├─ render.py       docs/ (GitHub Pages) neu erzeugen
       └─ git push        → .github/workflows/notify.yml legt ein Issue mit Link an
                            → GitHub schickt die Mail
```

Tage ohne Neuigkeiten erzeugen keine Seite und keine Mail; die Startseite zeigt trotzdem,
wann zuletzt geprüft wurde.

Scheitern Repo-Prüfung oder Leitstand-Bericht (`claude -p`-Helfer teilen das Nutzungslimit und
sterben gern still: Zeitüberschreitung, leere Antwort), läuft der Tag ohne sie weiter. Das steht als
`FEHLER …`/`VERMERK …` im Log und als Hinweis oben auf der Tagesseite; das Repo trägt dann
`pruefung: "fehler"`.

## Repo-Prüfung

Methode als Skill: `skills/repo-pruefung/SKILL.md` (Prüfauftrag ab der PROMPT-Marke) mit Skripten:

- `scripts/skill_liste.py` — erzeugt bei jedem Lauf `local/skills.json`: Name, Herkunft, Beschreibung
  aus den SKILL.md-Frontmattern unter `~/.claude*/skills`, `~/.config/cs/profiles.d/*/skills`,
  `~/.claude*/plugins` und aus einem Firmen-Skill-Katalog (`node <skript> catalog --json`, Pfad zum
  Skript in `local/katalog.txt`; fehlt oder nicht erreichbar → Hinweis in der Datei und im Log).
- `scripts/hole_repo.py` — klont flach in ein Wegwerf-Verzeichnis (ohne Submodule/LFS, Symlinks als
  Text), baut einen Auszug aus Dateibaum, README, Schlüsseldateien und größten Quelltexten. Nichts
  aus dem Repo wird ausgeführt oder installiert; der Prüf-Lauf hat keine Werkzeuge.
- `scripts/pruefschema.py` — prüft die Antwort im Code: Urteil `verworfen`/`vorschlag`
  (+ `verwendung`: übernehmen, idee adaptieren, beobachten), jeder Beleg eine Datei im Repo,
  README-Belege gelten als Selbstauskunft, Vergleichs-Skills müssen existieren, öffentliche
  Kurzbegründung ohne Sperrbegriffe (`local/sperrliste.txt`), Pfade, URLs.

**Was öffentlich wird:** am Repo nur `einsatz`, `urteil`, `verwendung`, `urteil_kurz`. Skill-Liste,
Auszüge und volle Berichte (vergleichbar / besser / adaptierbar / Belege) bleiben in `local/`
(gitignored): `local/pruefungen/<datum>/<owner>__<repo>.json`.

## Export für den Leitstand

`docs/leitstand.json` (wird mit veröffentlicht), Format `ki-radar-leitstand/1`:
`{"format", "date", "report": {"title", "text"}, "items": [{"id", "rubrik", "title", "url", "what",
"importance", "source", "einsatz", "urteil", "urteil_kurz"}]}`.

- `id` = `<n|r|g>-<JJJJMMTT>-<8 Hex aus dem Archiv-Schlüssel>` — stabil, weil jeder Eintrag nur an
  einem Tag erscheint.
- `report.text`: Fließtext (150–400 Wörter) über alle News- und Reddit-Einträge, jede Erwähnung
  mit `[[<id>]]`. Erfundene IDs → ungültig, ein zweiter Versuch, sonst Ersatztext und Vermerk;
  fehlende Referenzen oder falsche Länge → Warnung im Log. Der Bericht wird in der Tagesausgabe
  gemerkt und nur neu erzeugt, wenn sich die Einträge geändert haben.
- GitHub-Repos stehen mit in `items`, der Bericht deckt sie nicht ab.

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
python3 radar/run.py --only news   # einzelne Quelle(n) nachholen, in heutige Ausgabe einfügen
python3 radar/run.py --pruefen --no-publish  # Repo-Prüfung + Leitstand-Export für heute nachholen
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
