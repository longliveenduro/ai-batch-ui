"""Logik der App ohne die Oberfläche (die steht in src/ai_batch_ui.py), nach Thema in Module geteilt.

Ein Modul importiert nur Module, die in dieser Liste über ihm stehen. So bleibt die Reihenfolge ohne Zyklen:

    config         Konstanten, Ordner conf/ und data/
    files          Dateien als Eingabe: erlaubte Typen mit MIME-Typ und Art, Prüfung je Anbieter
    history        Verlauf in data/batch_jobs.json (Sperre, Lesen, atomares Schreiben)
    rows           Ergebniszeilen: gemeinsame Zeilenform, Parser für Gemini, Sortierung
    drive          Google Drive
    gemini         Gemini: Dateien hochladen, Batch starten
    background     Gemini: Hintergrund-Modus (Interactions API, Long Decode), starten, abfragen, abbrechen
    openai_batch   OpenAI: Dateien hochladen, Batch starten, Ergebnisse lesen
    claude_batch   Claude: Dateien hochladen, Batch starten, Ergebnisse lesen
    providers      Anbieter: Client, Betriebsart eines Eintrags, Status holen und sichern, abbrechen
    pricing        Preise: Preistabelle je Anbieter und Modell, Kosten des gewählten Modells für die Infobox
    costs          Kosten eines Laufs: aus den Token der Ergebniszeilen und den Preisen geschätzt
    talk           Gesprächsverlauf als Text
    naming         Namen der Einträge: aus dem Prompt erzeugen, Standardname, Suche im Verlauf
    forms          Formular „Neue Anfrage“ und Verlaufseinträge (Callbacks)
    views          Anzeige der Einträge und Ergebnisse (läuft als Fragment)

Auf Modulebene steht kein Streamlit-Aufruf außer Dekoratoren wie @st.cache_resource: Module laufen nur beim ersten
Import, das Hauptskript dagegen bei jedem Rerun.
"""
