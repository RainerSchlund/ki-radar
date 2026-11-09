Du schreibst den Tagesbericht eines deutschsprachigen KI-Briefings für einen erfahrenen Softwareentwickler (Datum: {date}). Unten stehen ALLE heute ausgewählten News- und Reddit-Einträge, jeder mit einer ID.

Aufgabe: Ein zusammenhängender Bericht auf Deutsch, Fließtext ohne Aufzählungen und ohne Zwischenüberschriften, {min_words}–{max_words} Wörter. Verbinde die Meldungen zu Themen (was hängt zusammen, was ist das Wichtigste, was bedeutet es für die Arbeit mit Coding-Agenten und KI-Werkzeugen). Erwähne jeden Eintrag mindestens einmal und setze direkt hinter die Erwähnung seine ID in doppelten eckigen Klammern, z. B. „Anthropic hat … veröffentlicht [[n-20261109-1a2b3c4d]].“ Verwende nur IDs aus der Liste, exakt wie dort geschrieben. Erfinde nichts, was nicht in den Einträgen steht; Reddit-Beiträge als Meinungen oder Berichte aus der Szene kennzeichnen.

Dazu ein Titel (max. 80 Zeichen), der das Hauptthema des Tages nennt.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne Markdown-Zaun, in genau dieser Form:
{"title": "...", "text": "..."}

Einträge (JSON-Zeilen):
