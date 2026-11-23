# AI Batch UI

Lokale Streamlit-Oberfläche, um ein **Gemini-4-Modell** (z. B. `gemini-4-carbon`), ein **OpenAI-Modell** (z. B. `gpt-6-astra`) oder ein **Claude-Modell** (z. B. `claude-sonnet-5-5`) mit **einer oder mehreren Dateien** (PDFs, Office-Dokumente, Text, Bilder, bei Gemini auch Audio und Video, bei Claude nur PDF, Text und Bilder) und **vielen Prompts** zu benutzen. Es gibt zwei Betriebsarten:

- **Batch** (Gemini, OpenAI und Claude): asynchron, 50 % des Standardpreises, Ergebnis nach Minuten bis Stunden (bei OpenAI und Claude innerhalb von 24 Stunden, bei Claude meist schon nach einer Stunde).
- **Hintergrund** (nur Gemini): Jeder Prompt läuft als Hintergrund-Interaktion bei Google (Interactions API, `background=true`). Nur so geht **Long Decode** über 65.536 Ausgabe-Token hinaus (bis 1.048.576 minus Eingabe), etwa wenn Carbon bei hoher Denktiefe das Limit von 32.768 im Batch aufbraucht. Standardpreis statt Batch-Rabatt, die App muss nicht durchgehend laufen.

Den früheren Modus „Synchron“ gibt es nicht mehr (Issue #17). Ältere Einträge davon bleiben im Tab „Jobs und Ergebnisse“ les- und löschbar (Abschnitt 4).

Dokumentationsstand: 01.11.2026 (Python 3.12, Streamlit 1.66, google-genai 2.34). Alle Aussagen zur Google-API gelten für diesen Stand, die zu Gemini 4 Carbon beruhen auf der Google-Dokumentation vom 11.11.2026, die zum Hintergrund-Modus (Long Decode, Background Execution) auf der vom 13.11.2026. Die Aussagen zur OpenAI-Anbindung beruhen auf der OpenAI-Dokumentation vom 10.11.2026 (openai 3.46), die zur Claude-Anbindung auf der Anthropic-Dokumentation vom 18.11.2026 (anthropic 2.10). Die Preise der Kosten-Infobox und die Liste der Modelle im Feld „Modell“ (Abschnitt 4) beruhen auf den Preisseiten der Anbieter vom 21.11.2026 (`PRICES_AS_OF`), bei Gemini 4 Neon und Hydrogen auf Berichten Dritter (Abschnitt 13). Vor Änderungen an API-nahem Code die Links in Abschnitt 13 prüfen, Preise und Limits ändern sich.

## Inhalt

1. [Worum es geht und warum](#1-worum-es-geht-und-warum)
2. [Funktionen im Überblick](#2-funktionen-im-überblick)
3. [Schnellstart](#3-schnellstart)
4. [Bedienung](#4-bedienung)
5. [Kosten sparen: Batch und Caching](#5-kosten-sparen-batch-und-caching)
6. [Konfiguration](#6-konfiguration)
7. [Lokale Dateien und Datenformate](#7-lokale-dateien-und-datenformate)
8. [Architektur](#8-architektur)
9. [Weiterentwickeln](#9-weiterentwickeln)
10. [Fehlersuche](#10-fehlersuche)
11. [Bekannte Einschränkungen und Ideen](#11-bekannte-einschränkungen-und-ideen)
12. [Sicherheit und Datenschutz](#12-sicherheit-und-datenschutz)
13. [Verifikationsstand und Quellen](#13-verifikationsstand-und-quellen)

---

## 1. Worum es geht und warum

**Ausgangslage.** Typischer Einsatz: Ein langes PDF (z. B. ein Buch mit rund 80.000 Token) wird mit mehreren Prompts bearbeitet, etwa „erzähle Abschnitt X in einfacher Sprache nach“. Bei jedem Prompt wird das ganze PDF erneut als Eingabe berechnet. Die PDF-Token dominieren deshalb die Kosten.

**Ziele der App**

- **Günstig**: Batch-Rabatt nutzen, und wo möglich das PDF aus dem (impliziten) Cache lesen lassen.
- **Bequem**: kein Skript pro Lauf. Ein Prompts-Feld, Datei-Upload (auch mehrere, nicht nur PDFs) oder PDFs aus Google Drive.
- **Nachvollziehbar**: pro Antwort Modell, Abschlussgrund, Eingabe-, Cache-, Denk- und Ausgabe-Token, rohe Nutzungsdaten und die geschätzten Kosten (Issue #39).
- **Robust**: Batches und Hintergrund-Läufe laufen bei Google (bis zu 24 Stunden), die App fragt nur den Stand ab. Alles überlebt Tab-Wechsel und Seiten-Neuladen. Ergebnisse werden lokal gesichert.

**Nicht-Ziele**: Mehrbenutzerbetrieb, Hosting im Netz, Anmeldung, Kostenabrechnung (die App schätzt die Kosten eines Laufs aus den Token, rechnet aber nichts ab, Abschnitt 4), explizites Caching bei Gemini (Carbon und Argon unterstützen es nicht, siehe Abschnitt 5). Bei Claude gibt es den Prompt-Cache als Kästchen, ein eigenes Cache-Management gibt es nicht.

**Herkunft.** Die Idee war ein kleines Streamlit-Werkzeug für den Batch-Betrieb mit dem Gemini-Batch-API. Daraus wurde zuerst eine Ein-Datei-App und mit dem Umfang ein Hauptskript für die Oberfläche plus das Paket `aibui` für die Logik (Abschnitt 8). Die Oberfläche ist deutsch.

**Name.** Bis Issue #18 hieß das Projekt `gemini-batch-ui`. Weil die App Batches auch bei anderen Anbietern als Google ausführt (derzeit OpenAI und Claude, weitere sollen folgen), heißt sie jetzt `ai-batch-ui` (in der Oberfläche „AI Batch UI“). Gemini-spezifische Teile behalten Gemini im Namen (`gemini.py`, `GEMINI_API_KEY`, `PROVIDER_GEMINI`). Wer von der alten Fassung umsteigt, beachtet vier Namen: Das Hauptskript heißt `src/ai_batch_ui.py` (vorher `src/gemini_batch_ui.py`), das Paket `aibui` (vorher `gbui`), die Umgebungsvariable `AI_BATCH_UI_HOME` (vorher `GEMINI_UI_HOME`, der alte Name wird nicht mehr gelesen) und die conda-Umgebung aus Abschnitt 3 `ai-batch-ui` (vorher `gemini-batch`, umbenennen mit `conda rename -n gemini-batch ai-batch-ui`). Der Inhalt von `conf/` und `data/` bleibt unverändert.

## 2. Funktionen im Überblick

- Drei Anbieter: **Gemini** (Batch und Hintergrund), **OpenAI** (nur Batch, Endpunkt `/v1/responses`) und **Claude** von Anthropic (nur Batch, Message Batches API). Der Anbieter für neue Anfragen steht in der Seitenleiste, jeder Verlaufseintrag merkt sich seinen eigenen.
- Zwei Modi: **Batch** und **Hintergrund** (Hintergrund nur mit Gemini).
- **Mehrere Dateien** pro Anfrage (Issue #16: nicht nur PDFs, siehe „Dateien und erlaubte Typen“ in Abschnitt 4): Datei-Upload (mehrfach), Auswahl aus Google Drive (Liste der 50 zuletzt geänderten PDFs, mehrfach wählbar) und/oder eingefügte Drive-Links oder Datei-IDs (eine pro Zeile). Google Docs/Slides aus Drive werden als PDF exportiert. Gleiche Dateien werden nur einmal gesendet.
- **Mehrere Prompts**, getrennt durch eine Zeile mit `---`. Optional **Systemanweisung**.
- **Denktiefe** (Gemini: `low`, `medium`, `high`. OpenAI: `none` bis `max`. Claude: `low` bis `max`, gesendet als `output_config.effort`. Jeweils „Standard“ = nichts senden) und **max. Ausgabe-Token**.
- **Prompt-Cache bei Claude** (Issue #2, Kästchen im Formular, in der Voreinstellung aus): Die Dateien tragen eine Cache-Marke mit einer Stunde Lebensdauer, damit mehrere Prompts zu denselben Dateien sie aus dem Cache lesen können. Anders als bei Gemini und OpenAI cacht Claude nur auf diese Weise, und das Schreiben in den Cache kostet extra (Abschnitt 5).
- **Long Decode im Hintergrund (nur Gemini)**: Im Modus „Hintergrund“ startet jeder Prompt als Interaktion mit `background=true` (Interactions API). Googles Server setzen die Antwort in Schritten zu je 64K Token fort, bis zu 1.048.576 Token minus Eingabe. Das löst `MAX_TOKENS` bei hoher Denktiefe, wo ein Batch bei 32.768 Token endet. Die App fragt nur den Stand ab, wie bei einem Batch.
- **Modellauswahl** (Issue #11): Das Feld „Modell“ in der Seitenleiste ist eine Combobox. Sie nennt die aktuellen Modelle des gewählten Anbieters (höchstens 5), das teuerste zuerst, und wählt zu Beginn das erste vor. Ein anderer Name lässt sich eintippen, etwa ein neues Modell, das die Liste noch nicht kennt. Die Liste kommt aus der Preistabelle `PRICES` in `src/aibui/pricing.py`, nicht aus der Modellliste der Anbieter-APIs (Begründung: Abschnitt 11).
- **Kosten des Modells** (Issue #12): Unter dem Feld „Modell“ in der Seitenleiste nennt eine Infobox die Preise des gewählten Modells je 1 Mio. Token (Eingabe, Ausgabe, Cache): für den Batch (die Hälfte des Standardpreises) und bei Gemini auch für den Hintergrund-Modus (Long Decode, Standardpreis). Ein feststehender Preiswechsel (Gemini 4 am 01.12.2026) steht schon davor in der Box. Es ist die Preisliste des Modells. Die Preise stehen in `src/aibui/pricing.py`, eigene Preise ersetzen sie über die Datei `conf/prices.toml` (Abschnitt 6.6).
- **Kosten eines Laufs** (Issue #39): Im Tab „Jobs und Ergebnisse“ stehen unter der Summe der Token die geschätzten Kosten des Laufs in USD, je Prompt zusätzlich in der Detailzeile. Sie ergeben sich aus den Token der Antworten und den Preisen der Kosten-Infobox, mit dem Preisstand des Tages, an dem der Lauf gestartet wurde. Bei Gemini steht der Vergleich Batch gegen Hintergrund-Modus dabei (dieselben Token, beide Preise). Es ist eine Schätzung, keine Abrechnung (Abschnitt 4 nennt, was eingerechnet ist und was nicht).
- **Eigene Preise** (Issue #39): Die optionale Datei `conf/prices.toml` ändert Preise der eingebauten Tabelle oder ergänzt Modelle, ohne den Code anzufassen. Die Preise gelten für die Infobox, die Auswahl im Feld „Modell“ und die Kosten der Läufe (Abschnitt 6.6).
- **Jobs und Ergebnisse**: Verlauf aller Läufe, automatische Statusprüfung alle 10 Sekunden solange der Tab offen ist, Ergebnisse mit Token- und Cache-Angaben und geschätzten Kosten, Markdown-Download, Rohdaten-JSON.
- **Lokale Sicherung** der Ergebnisse (`data/batch_jobs.json`), auch nach Ablauf der Aufbewahrung bei Google.
- **Eingaben übernehmen**: Prompts und Einstellungen eines früheren Eintrags zurück ins Formular holen. **Eintrag löschen** (nur lokal).
- **Namen und Suche** (Issue #23): Bleibt das Feld „Name“ leer, erzeugt ein kleines, günstiges Gemini-Modell (Voreinstellung `gemini-3.5-flash-lite`, Denktiefe `medium`) den Namen aus dem Anfang der Prompts, ähnlich den Titeln im Verlauf eines Chatbots. Name und eine freie Beschreibung lassen sich im Tab „Jobs und Ergebnisse“ jederzeit ändern, bei älteren Einträgen erzeugt ein Klick den Namen aus ihrem Prompt. Die **Suche** über der Liste findet Einträge nach Name, Beschreibung, Prompts, Dateinamen und ID.
- **Prompts im Wortlaut**: Im Tab „Jobs und Ergebnisse“ zeigt ein Klick die gesendete Anfrage im Detail (Dateien, Systemanweisung, jeder Prompt, auch solange ein Batch noch keine Ergebnisse hat) und je Ergebnis den vollständigen Prompt.
- **Gespräch fortsetzen**: Zu jeder Antwort erzeugt die App auf Klick den bisherigen Gesprächsverlauf als Text (früherer Prompt und deine Antwort dazu, bei älteren synchronen Gesprächen alle Runden) und legt ihn ins Formular „Neue Anfrage“. Darunter schreibt man den neuen Prompt. Das geht beliebig oft hintereinander, der Verlauf wächst dabei nur um eine Runde.
- **Wiederverwendung hochgeladener Dateien** über Neustarts hinweg (`data/pdf_files.json` bei Gemini, `data/openai_files.json` bei OpenAI, `data/claude_files.json` bei Claude), damit die Datei-Referenz gleich bleibt.
- **Drive-Anmeldung erneuert sich selbst**, wenn die Freigabe abgelaufen ist.
- **Aufgeräumte Ordner**: Zugangsdaten in `conf/`, erzeugte Daten in `data/`.

## 3. Schnellstart

**Voraussetzungen**

- Python 3.12 (vom Besitzer genutzt). Die App und die Tests unterstützen mindestens Python 3.12, außerdem mindestens Streamlit 1.67.0, google-genai 3.3.0, openai 3.51.0 und anthropic 2.10.0 (Abschnitt 6.5). Ältere Versionen werden weder unterstützt noch getestet.
- Ein API-Key für den Anbieter, den man nutzt: Gemini (in Google AI Studio erzeugen), OpenAI (auf der OpenAI-Plattform erzeugen) und/oder Claude (in der Anthropic Console erzeugen).
- Optional für Drive: OAuth-Zugang, siehe 6.4.

**Installation** (am besten in einer eigenen Umgebung, damit andere Pakete unberührt bleiben):

```bash
conda create -n ai-batch-ui python=3.12 -y
conda activate ai-batch-ui
pip install -r requirements.txt
```

Für die Tests zusätzlich `pip install -r requirements-dev.txt` (Abschnitt 9.3).

`requirements.txt`:

```text
streamlit>=1.67.0
google-genai>=3.3.0
openai>=3.51.0
anthropic>=2.10.0
google-api-python-client
google-auth-oauthlib
```

Kein `pip install -U -r ...` in einer gemeinsam genutzten Umgebung (z. B. Anaconda „base“ mit TensorFlow): `-U` hebt unbeteiligte Pakete an und erzeugt Abhängigkeitskonflikte.

**Starten**

```bash
export GEMINI_API_KEY="dein-key"      # optional, sonst in der Seitenleiste eintragen
export OPENAI_API_KEY="dein-key"      # optional, für den Anbieter OpenAI
export ANTHROPIC_API_KEY="dein-key"   # optional, für den Anbieter Claude
streamlit run src/ai_batch_ui.py  # im Projektordner ausführen, öffnet http://localhost:8501
```

Anderer Port: `streamlit run src/ai_batch_ui.py --server.port 8502`. Beenden mit Strg+C (Batches und Hintergrund-Läufe laufen bei Google weiter). Beim ersten Start legt die App die Ordner `conf/` und `data/` im Projektordner neben `src/` an (Abschnitt 7).

**Erster Lauf in 60 Sekunden**

1. Seitenleiste: Anbieter wählen (Gemini, OpenAI oder Claude), API-Key prüfen, Modell aus der Liste wählen oder eintippen.
2. Tab „Neue Anfrage“: Modus wählen (nur bei Gemini), Dateien hochladen, Prompts eintragen (mehrere mit `---` auf eigener Zeile trennen).
3. „Batch starten“ oder „Im Hintergrund starten“. Der neue Eintrag ist danach im Tab „Jobs und Ergebnisse“ vorausgewählt.

## 4. Bedienung

### Seitenleiste

| Element | Bedeutung |
|---|---|
| Anbieter für neue Anfragen | `Gemini` (Voreinstellung), `OpenAI` oder `Claude`. Das Formular „Neue Anfrage“ passt sich an: Mit OpenAI und Claude entfällt der Modus (es gibt nur Batch), und die Denktiefe kennt die Stufen des Anbieters (bei Claude kommt das Kästchen für den Prompt-Cache dazu). Einträge im Tab „Jobs und Ergebnisse“ werden unabhängig von dieser Wahl mit dem Anbieter und dem Key abgefragt, zu denen sie gehören. Beim Hin- und Herwechseln merkt sich die App die Werte aller Anbieter (Modell, Denktiefe, Token-Limit, bei Claude der Cache-Schalter), Prompts und Systemanweisung gelten für alle. |
| Gemini API-Key, OpenAI API-Key, Claude API-Key | Vorbelegt aus `GEMINI_API_KEY`, `OPENAI_API_KEY` bzw. `ANTHROPIC_API_KEY`, alle dürfen eingetragen bleiben. Fehlt der Key des gewählten Anbieters, bleibt die App stehen und sagt es. Fehlt der Key des Anbieters eines Verlaufseintrags, sind dort „Status prüfen / Ergebnisse laden“ und „Batch abbrechen“ (bei Hintergrund-Einträgen „Läufe abbrechen“) gesperrt, gesicherte Ergebnisse bleiben sichtbar. |
| Modell | Combobox (Issue #11), je Anbieter ein eigenes Feld: Sie nennt die aktuellen Modelle aus der Preistabelle (höchstens 5, dazu die Modelle, die `conf/prices.toml` ergänzt, Abschnitt 6.6), das teuerste zuerst (nach dem Ausgabepreis am heutigen Tag, bei gleichem Preis gilt die Reihenfolge der Tabelle), und wählt das erste vor. Stand 21.11.2026 bei Gemini `gemini-4-neon`, `gemini-4-carbon`, `gemini-4-argon` und `gemini-4-hydrogen` (ab 01.12.2026 steht Carbon vorn), bei OpenAI `gpt-6-astra`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6.1-terra` und `gpt-6-luna`, bei Claude `claude-fable-5-2`, `claude-opus-5-5`, `claude-sonnet-5-5` und `claude-haiku-5-5`. Ein anderer Name lässt sich eintippen (Streamlit gleicht Groß- und Kleinschreibung mit der Liste ab), das Feld lässt sich nicht leeren. Ein eigener Name, etwa aus dem Verlauf („Eingaben übernehmen“), steht hinter der Liste, bis ein anderes Modell gewählt wird. Bei OpenAI muss das Modell die Batch API und Dateieingaben (bei Bildern: Bildeingaben) unterstützen. Bei Claude nehmen die aktuellen Modelle die Message Batches API und kennen die Denktiefe (Abschnitt 5). Bei Gemini ist die App auf die Gemini-4-Modelle zugeschnitten. Modelle ergänzen oder entfernen: Abschnitt 9.2 |
| Kosten des Modells (Infobox unter „Modell“, Issue #12) | Die blaue Box nennt die Preise des gewählten Modells in USD je 1 Mio. Token als Tabelle mit den Spalten Eingabe, Ausgabe (einschließlich Denk-Token) und Cache (Eingabe-Token, die aus dem Cache gelesen werden). Die Zeile „Batch“ kostet die Hälfte des Standardpreises, bei Gemini kommt die Zeile „Hintergrund (Long Decode)“ zum Standardpreis dazu. Hängt der Preis von der Länge des Prompts ab (Claude Haiku 5.5 ab 100.000 Token, OpenAI ab 272.000 Eingabe-Token, dann für die ganze Anfrage), gibt es je Stufe eine Zeile. Steht ein Preiswechsel schon fest (Gemini 4 Carbon und Argon: ab 01.12.2026 doppelt so teuer), folgt unter „Ab 01.12.2026“ eine zweite Tabelle, und ab dem Tag zeigt die Box nur noch die neuen Preise. Darunter steht der Stand der Preise, ein Tooltip erklärt die Spalten. Die Box folgt dem Anbieter und dem Feld „Modell“ (Groß- und Kleinschreibung, ein Vorspann „models/“ und ein angehängter Stand wie in `gpt-6-astra-2026-09-01` zählen nicht, eine andere Fassung wie `gpt-6-astra-pro` ist ein anderes Modell) und erscheint auch ohne API-Key. Für ein Modell ohne Eintrag in der Tabelle sagt sie das und nennt die bekannten Modelle in der Reihenfolge der Combobox (ein leerer Name ergäbe keine Box, das Feld „Modell“ lässt sich aber nicht leeren). Die Zahlen stehen ohne Währungszeichen da, weil Streamlit ein `$` als Formel liest. Eigene Preise aus `conf/prices.toml` ersetzen die eingebauten (Abschnitt 6.6): Für ein solches Modell steht unter der Box statt des Stands der Preise „Eigene Preise aus conf/prices.toml“, und Fehler in der Datei meldet eine Warnung unter der Box (Einträge mit Fehlern gelten nicht). Preise ändern: Abschnitt 6.6 und 9.2 |
| Namen der Einträge (Ausklapper) | „Name aus dem Prompt erzeugen“ (Voreinstellung an), „Modell für die Namen“ (Voreinstellung `gemini-3.5-flash-lite`) und „Denktiefe für die Namen“ (`minimal`, `low`, `medium`, `high`, Voreinstellung `medium`). Die Namen entstehen immer mit Gemini und dem Gemini API-Key über die normale Gemini API von Google (ein einfacher `generate_content`-Aufruf, kein Batch, kein Vertex AI), auch bei einem OpenAI-Lauf (zum Datenschutz siehe Abschnitt 12). Ohne Gemini API-Key bekommt jeder neue Eintrag den Standardnamen. |

### Tab „Neue Anfrage“

| Element | Bedeutung |
|---|---|
| Modus | Batch (asynchron, günstiger) oder Hintergrund (Long Decode: jeder Prompt läuft als Interaktion bei Google, Standardpreis). Mit OpenAI und Claude gibt es nur Batch, der Schalter entfällt. |
| Dateien | Mehrere Dateien möglich, eine zweite ersetzt die erste nicht. Das Feld nimmt jeden Typ an. Ob der gewählte Anbieter ihn annimmt, prüft die App nach der Endung (siehe „Dateien und erlaubte Typen“ unten). |
| PDFs aus Google Drive | Button „Meine PDFs aus Drive laden“ füllt die Mehrfachauswahl. Zusätzlich Links oder Datei-IDs einfügen. Reihenfolge: hochgeladene Dateien, dann Drive-Auswahl, dann eingefügte Links. Die Reihenfolge steht als Hinweis unter dem Bereich. |
| Systemanweisung | Optional, gilt für jede Anfrage. |
| Prompts | Ein Textfeld, mehrere Prompts durch eine Zeile nur mit `---` trennen. Beginnt ein Prompt mit einem Gesprächsverlauf (aus „Gespräch fortsetzen“), steht der neue Prompt unter `[Mein neuer Prompt]`. Solange dort nichts steht, ist der Start gesperrt. |
| Denktiefe | Gemini: „Standard“ (kein Parameter, Carbon nutzt dann `medium`), `low`, `medium`, `high`. Voreinstellung `high`. Carbon denkt länger als Argon: `medium` ist laut Google für die meisten Aufgaben richtig, `high` verbraucht die meisten Token. OpenAI: „Standard“ (kein Parameter, es gilt die Voreinstellung des Modells), `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Voreinstellung „Standard“. Welche Stufen ein Modell kennt, hängt vom Modell ab (z. B. kennt `gpt-6-astra` kein `none`). Die API lehnt andere ab, der Fehler steht dann je Prompt im Ergebnis. Claude: „Standard“ (kein Parameter, es gilt die Voreinstellung des Modells: `medium` bei Opus 5.5 und Haiku 5.5, sonst `high`), `low`, `medium`, `high`, `xhigh`, `max`, gesendet als `output_config.effort`. Voreinstellung „Standard“. Die aktuellen Claude-Modelle denken adaptiv, die Stufe bestimmt, wie viel und wann. Auch hier lehnt die API Stufen ab, die ein Modell nicht kennt (`xhigh` gibt es nicht bei allen). |
| Max. Ausgabe-Token | Gemini-Batch: bis 32.768 (Voreinstellung 32.768). Gemini Hintergrund: bis 1.048.576 (Voreinstellung 262.144), über 65.536 setzen Googles Server Long Decode ein, die Eingabe zählt mit (höchstens 1.048.576 minus Eingabe). OpenAI und Claude: bis 128.000 (Voreinstellung 32.768), je nach Modell darunter. Denk-Token zählen zum Limit. |
| Dateien im Prompt-Cache halten (nur Claude) | Kästchen, Voreinstellung aus (`cache_claude`). Setzt auf die letzte Datei jeder Anfrage eine Cache-Marke (`cache_control` mit `ttl` `1h`), damit der Prefix aus Systemanweisung und Dateien für alle Prompts eines Batches gilt. Schreiben in den Cache kostet das Doppelte des Eingabepreises, Lesen nur einen Bruchteil. Das lohnt sich bei vielen Prompts zu denselben Dateien, bei einem einzelnen Prompt kostet es nur mehr. Ohne Dateien passiert nichts. Abschnitt 5 rechnet es vor. |
| Name | Bezeichnung des Eintrags im Verlauf. **Leer lassen** (Voreinstellung): Ein kleines Gemini-Modell erzeugt den Namen aus dem Anfang der Prompts (Grenzen: `NAME_SOURCE_PROMPTS` und `NAME_SOURCE_CHARS`, nie die Dateien oder die Systemanweisung), bei einer Gesprächsfortsetzung nur aus dem neuen Prompt. Der Platzhalter sagt, was passiert: „automatisch aus dem Prompt“ oder, wenn die Namensvergabe aus ist oder der Gemini API-Key fehlt, der Standardname `<Art>-<Datum>-<Uhrzeit>` (`gemini-…` für einen Gemini-Batch, `background-gemini-…` im Modus „Hintergrund“, `openai-…` bei OpenAI, `claude-…` bei Claude). Ein eingetippter Name gilt immer und löst keinen Aufruf aus. Scheitert die Erzeugung, startet der Lauf trotzdem mit dem Standardnamen, und eine Warnung nennt den Grund. Der Name geht beim Start auch an Gemini (Anzeigename des Batches) und OpenAI (Beschreibung), nicht an Claude: Die Message Batches API kennt keinen Namen. Spätere Änderungen bleiben lokal. |
| Start-Button | Lädt die Dateien hoch, sendet bzw. startet. Während dieser Vorbereitung nicht den Tab wechseln, sonst bricht der Start ab. |

Ohne angehängte Datei werden die Prompts ohne Datei gesendet (steht als Hinweis im Formular).

### Dateien und erlaubte Typen (Issue #16)

Das Feld „Dateien“ nimmt jede Datei an. Ob der **gewählte Anbieter** sie annimmt, prüft die App nach der **Endung** (Groß- und Kleinschreibung egal, maßgeblich ist die letzte Endung). Nimmt er eine Datei nicht an, steht unter dem Feld ein Fehler mit den Dateinamen, und der Start ist gesperrt, bis sie entfernt sind. Wechselt man den Anbieter, bleiben die Dateien im Feld, nur die Prüfung ändert sich. Die Typen stehen an einer Stelle, in `src/aibui/files.py`: `FILE_TYPES` (Endung → Art und MIME-Typ), `TEXT_EXTENSIONS` (die Endungen der Textdateien) `PROVIDER_KINDS` (welche Arten ein Anbieter annimmt) und `PROVIDER_EXCLUDED` (welche Endungen er trotz passender Art ablehnt: bei Claude `OFFICE_EXTENSIONS`).

| Art | Endungen | Gemini | OpenAI | Claude |
|---|---|---|---|---|
| Dokumente | `.pdf`, `.docx`, `.doc`, `.odt`, `.pptx`, `.ppt`, `.xlsx`, `.xls`, `.csv` | ja | ja | nur `.pdf` und `.csv` (Word, PowerPoint, Excel und OpenDocument-Text nein) |
| Text | `.txt`, `.md`, `.json`, `.html`, `.xml`, `.py`, `.sql` und weitere (alle in `TEXT_EXTENSIONS`) | ja, als `text/plain` | ja | ja, als `text/plain` |
| Bilder | `.png`, `.jpg`, `.jpeg`, `.webp` | ja | ja | ja |
| Audio | `.mp3`, `.wav`, `.m4a`, `.aac`, `.ogg`, `.flac`, `.aiff` | ja | nein | nein |
| Video | `.mp4`, `.mov`, `.avi`, `.webm`, `.wmv`, `.mpeg`, `.mpg`, `.3gp` | ja | nein | nein |

So steht jede Art in der Anfrage. Die Datei selbst geht immer zuerst in die Files API des Anbieters und steht in der Anfrage nur als Verweis (die Anfragedatei bleibt klein):

| Anfrage | Dokumente und Text | Bilder | Audio und Video |
|---|---|---|---|
| Gemini, Batch | `file_data` mit `file_uri` und dem MIME-Typ, den die Files API für die Datei führt | wie Dokumente | wie Dokumente |
| Gemini, Hintergrund | `document` mit `uri` und `mime_type` | `image` | `audio` bzw. `video` |
| OpenAI, Batch | `input_file` mit `file_id` (Zweck `user_data`) | `input_image` mit `file_id` (Zweck `vision`) | nicht möglich |
| Claude, Batch | `document` mit `source` vom Typ `file` und `file_id` (PDF und `text/plain`) | `image` mit `source` vom Typ `file` und `file_id` | nicht möglich |

Gut zu wissen:

- Der Typ folgt aus der Endung, nicht aus dem Inhalt. Die App prüft auch keine Größen: Bei OpenAI sind es unter 50 MB je Datei und zusammen höchstens 50 MB je Anfrage, das Datei-Feld von Streamlit nimmt standardmäßig bis 200 MB je Datei (Abschnitt 6.3).
- Ob ein **Modell** einen Typ annimmt, hängt vom Modell ab. Laut Modellseite von Gemini 4 Carbon nimmt es neben PDF und Text auch Office- und OpenDocument-Dateien an, andere Modelle womöglich nur PDF und Text. Meldet die API einen Fehler zu einer Datei, hilft meist ein Export als PDF.
- Bei OpenAI liest das Modell von Dokumenten, die kein PDF sind, nur den Text: Bilder und Diagramme in Word- oder PowerPoint-Dateien gehen verloren (dafür als PDF exportieren). Von Tabellen liest es je Blatt nur die ersten 1.000 Zeilen.
- Bei Claude liest die Files API als Dokument nur PDF und `text/plain`. Textformate und CSV gehen deshalb als `text/plain` hoch, Word, PowerPoint, Excel und OpenDocument-Text lehnt die App ab (Fehler unter dem Feld, der Start ist gesperrt). Anthropic nennt dafür den Umweg über PDF oder Text. Dateinamen mit Zeichen, die die Files API ablehnt (z. B. `:` oder `?`), ändert `claude_filename()` nur für den Upload. Der Name im Verlauf bleibt, wie er ist.
- Google Drive bleibt bei PDFs (und Google-Dokumenten als PDF-Export, Abschnitt 11).
- Die Hilfe (?) am Feld nennt alle Endungen und am Ende, was einzelne Anbieter ablehnen („Nicht bei Claude: …“). Sie ist für alle Anbieter gleich, denn ein Text, der sich beim Anbieterwechsel ändert, würde das Feld neu aufbauen und seine Dateien verwerfen (die Kennung eines Widgets ohne `key` hängt auch vom Hilfetext ab).

### Tab „Jobs und Ergebnisse“

- **Suche** (über der Liste, sobald es Einträge gibt): Jedes Suchwort muss vorkommen, Groß- und Kleinschreibung und Reihenfolge sind egal. Durchsucht werden Name, Beschreibung, ID, Dateinamen und Prompts, nicht die Antworten. Die Liste zeigt dann nur die Treffer („Treffer: n von m Einträgen.“), ohne Treffer steht ein Hinweis da. Ein neu gestarteter Eintrag leert die Suche, damit er sichtbar und vorausgewählt ist.
- **Eintrag**: Auswahlliste, neuester Eintrag oben. Jeder Eintrag steht mit seinem Namen, dem Startzeitpunkt und dem Ende der ID da (z. B. „Kapitel 3 einfach erklärt (2026-11-15 03:04) abc123“). Hat der Eintrag eine Beschreibung, steht sie darunter.
- **Name und Beschreibung** (Popover): ändert den Namen und die freie Beschreibung („Speichern“, ein leerer Name behält den bisherigen) oder erzeugt den Namen neu aus den Prompts des Eintrags („Name aus dem Prompt erzeugen“, nutzt die Einstellungen der Seitenleiste, gesperrt ohne Gemini API-Key). So bekommen auch ältere Einträge mit Standardnamen einen sprechenden Namen. Scheitert die Erzeugung, steht der Grund einmalig als Warnung über der Liste, der Name bleibt. Passt der Eintrag nach dem Umbenennen nicht mehr zur Suche, leert die App die Suche, damit er sichtbar bleibt.
- **Eingaben übernehmen**: füllt „Neue Anfrage“ mit Prompts, Systemanweisung, Anbieter, Modell, Modus, Denktiefe, Token-Limit und (bei Claude) dem Cache-Schalter. Einträge des früheren Modus „Synchron“ landen im Modus „Hintergrund“ (jeder Prompt läuft dort für sich, der Hinweis nach dem Übernehmen sagt es). Dateien müssen neu angehängt werden, bereits hochgeladene Dateien werden dabei wiederverwendet.
- **Eintrag löschen** (Bestätigung im Popover): entfernt den lokalen Eintrag samt gesicherter Ergebnisse. Beim Anbieter bleibt alles unverändert. Deaktiviert, solange der Eintrag läuft.
- **Gesendete Anfrage im Detail** (Schalter, standardmäßig aus): zeigt die Dateien in ihrer Reihenfolge, die Systemanweisung und jeden Prompt im Wortlaut, bei älteren synchronen Gesprächen mit Gespräch und Runde. Das geht auch, solange ein Batch noch läuft und es noch keine Ergebnisse gibt.
- **Batch**: Buttons „Status prüfen / Ergebnisse laden“ und „Batch abbrechen“. Solange der Tab offen und der Batch nicht fertig ist, prüft die App alle 10 Sekunden selbst. Ist der Batch fertig, werden die Ergebnisse geladen und lokal gesichert. Danach braucht ein Öffnen keinen Abruf mehr. Bei OpenAI-Einträgen („Batch (OpenAI)“) zeigt die Statuszeile den Status der Batch API (`validating`, `in_progress`, `finalizing`, `completed`, `failed`, `expired`, `cancelling`, `cancelled`). Bei `expired` und `cancelled` lädt die App die bis dahin fertigen Antworten, die übrigen stehen mit Fehlertext in der Liste. Scheitert der ganze Batch (`failed`, z. B. wegen des Token-Limits der Warteschlange), steht der Grund als Fehlermeldung über den Ergebnissen. Bei Claude-Einträgen („Batch (Claude)“) zeigt die Statuszeile den `processing_status` der Message Batches API (`in_progress`, `canceling`, `ended`). Ergebnisse gibt es erst, wenn er `ended` ist, einen Teilstand liefert die API nicht. Danach steht jede Anfrage als Antwort, Fehler (`errored`), Abbruch (`canceled`) oder Ablauf (`expired`, nach 24 Stunden) in der Liste, die beiden letzten werden nicht berechnet. Einen Fehler des ganzen Batches kennt die Message Batches API nicht, jeder Fehler gehört zu einem Prompt.
- **Hintergrund** („Hintergrund (Long Decode)“ in der Kopfzeile): wie beim Batch die Buttons „Status prüfen / Ergebnisse laden“ und „Läufe abbrechen“ und die automatische Prüfung alle 10 Sekunden, solange der Tab offen und nicht alles beendet ist. Je Prompt läuft eine eigene Interaktion bei Google. Die Statuszeile zeigt `in_progress`, solange mindestens eine läuft (dazu „n von m Prompts fertig“), danach `completed` (einzelne Fehler stehen in den Ergebnissen), `cancelled` (alle abgebrochen) oder `failed` (alle fehlgeschlagen). Fertige Antworten erscheinen sofort, auch wenn andere noch laufen. Erst wenn alle beendet sind, sichert die App das Endergebnis lokal. „Läufe abbrechen“ bricht alle Interaktionen ab, bezahlt wird, was bis dahin angefallen ist.
- **Älterer synchroner Eintrag** („synchron“ in der Kopfzeile): Den Modus gibt es nicht mehr, der Eintrag ist nur noch zu lesen. Gezeigt werden der gesicherte Zustand (`fertig`, `abgebrochen`, `fehlgeschlagen` oder `unterbrochen`, so gilt auch ein Lauf, der beim Beenden der App noch lief) und „n von m Prompts“ mit den gesicherten Ergebnissen, ohne Abfrage und ohne Abbruch-Button. Löschen, „Eingaben übernehmen“ und „Gespräch fortsetzen“ gehen weiter.
- **Ergebnisse**: Summenzeile (Eingabe-Token gesamt und davon aus dem Cache) mit den geschätzten Kosten des Laufs darunter (Issue #39, siehe unten), Download „Ergebnisse als Markdown“, pro Prompt ein Ausklappfeld mit Antwort, Warnungen, Detailzeile (Modell, Abschlussgrund, Token, geschätzte Kosten des Prompts, bei älteren synchronen Einträgen auch Dauer) und rohen `usage`-Daten als einklappbarem JSON. Die Überschrift zeigt nur die ersten 90 Zeichen des Prompts (bei einer Fortsetzung ein ↪ und den neuen Prompt). Der Schalter „Prompt im Wortlaut“ zeigt den ganzen Prompt. Unter der Antwort stehen „Gespräch fortsetzen“ und der Schalter „Verlaufstext zeigen“.

**Warnungen in den Ergebnissen.** `MAX_TOKENS` bedeutet: Denk- und Ausgabe-Token haben das Limit erreicht, die Antwort ist abgeschnitten. Jeder andere Abschlussgrund außer `STOP` (z. B. `SAFETY`) wird ebenfalls gemeldet. Bei einem Gemini-Batch weist die App bei `MAX_TOKENS` zusätzlich auf den Modus „Hintergrund“ hin. Im Hintergrund-Modus gilt der Status der Interaktion als Abschlussgrund: `completed` ist `STOP`, `incomplete` (alle `max_output_tokens` verbraucht, der Text ist leer, wenn das Modell noch dachte) ist `MAX_TOKENS`, jeder andere Status erscheint in Großbuchstaben (z. B. `FAILED`, `CANCELLED`).

**Token bei Claude.** Claude zählt in `input_tokens` nur Token, die weder aus dem Cache gelesen noch in ihn geschrieben wurden. Die App rechnet zusammen: „Eingabe“ = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`, „Cache“ = `cache_read_input_tokens`. Denk-Token zählt Claude in `output_tokens` mit. Die App trennt sie, soweit die API sie ausweist: „Denken“ = `output_tokens_details.thinking_tokens`, „Ausgabe“ = `output_tokens` minus Denken. Fehlt diese Angabe, steht Denken 0 und die Denk-Token stecken in „Ausgabe“. Das Schreiben in den Cache (`cache_creation_input_tokens`) kostet mehr als normale Eingabe und steht nur im rohen `usage`. Der Abschlussgrund `end_turn` erscheint als `STOP`, `max_tokens` als `MAX_TOKENS` (dieselbe Warnung wie sonst), jeder andere Grund (z. B. `refusal`) in Großbuchstaben. Lehnt das Modell ohne Text ab, zeigt die Zeile Kategorie und Erklärung der API.

**Token bei OpenAI.** OpenAI rechnet Denk-Token in `output_tokens` ein. Die App trennt sie, damit die Zeilen beider Anbieter gleich zu lesen sind: „Denken“ = `reasoning_tokens`, „Ausgabe“ = `output_tokens` minus `reasoning_tokens`, „Cache“ = `cached_tokens`. Eine unvollständige Antwort (`incomplete` wegen `max_output_tokens`) erscheint als `MAX_TOKENS`, damit dieselbe Warnung greift, jeder andere Grund (z. B. `content_filter`) steht im Wortlaut der API da.

**Kosten eines Laufs (Issue #39).** Keine der drei APIs nennt die Kosten einer Anfrage in der Antwort, sie liefert nur Token-Zahlen, und die Kosten-APIs von Anthropic und OpenAI brauchen einen Admin-Key und liefern nur Tagessummen. Die App rechnet deshalb selbst, beim Anzeigen und ohne Abfrage beim Anbieter (`run_costs()` in `src/aibui/costs.py`), also ohne Verzögerung. Je Prompt gilt: neue Eingabe mal Eingabepreis, plus Cache-Token mal Cache-Preis, plus Denken und Ausgabe mal Ausgabepreis, durch 1 Mio. geteilt. „Neue Eingabe“ ist die Eingabe der Zeile ohne die Token aus dem Cache. Beim Batch kommt der Faktor `BATCH_FACTOR` dazu, die Summe zählt alle Prompts. Die Preise sind die der Kosten-Infobox, auch die eigenen aus `conf/prices.toml` (Abschnitt 6.6), und zwar die Stufe, die zur Länge des Prompts passt, mit dem Preisstand des Tages, an dem der Lauf gestartet wurde (Feld `created`): Ein Lauf vom 30.11.2026 kostet auch am 15.12.2026 noch den alten Preis von Gemini 4 Carbon. Das Modell ist das des Eintrags, sonst das, das die API gemeldet hat, damit ein Alias wie `claude-sonnet-latest` über den Namen in der Antwort seinen Preis findet. Kennt die Tabelle es nicht, steht statt der Kosten ein Hinweis mit dem Weg zu `conf/prices.toml`.

- **Gemini**: Die Zeile nennt zugleich dieselben Token in der anderen Betriebsart: Neben einem Batch (halber Standardpreis) steht der Hintergrund-Modus (Standardpreis), neben einem Hintergrund-Lauf der Batch. Das ist ein Vergleich mit gleichen Token. Bei einem Lauf mit Long Decode ist der Wert für den Batch nur eine Obergrenze: Im Hintergrund-Modus zählt die Eingabe jedes 64K-Schritts erneut (meist als Cache), ein Batch berechnet sie nur einmal und endet bei 32.768 Ausgabe-Token.
- **Claude**: nur Batch, ohne Vergleich. Das Schreiben in den Cache ist eingerechnet, mit dem 2-fachen des Eingabepreises bei einer Stunde Lebensdauer und dem 1,25-fachen bei fünf Minuten (`CLAUDE_CACHE_WRITE`). Die Lebensdauer liest die App aus `cache_creation` in den Nutzungsdaten, was dort fehlt, zählt mit `CLAUDE_CACHE_TTL`. Der Batch-Rabatt gilt zusätzlich, wie Anthropic es beschreibt.
- **OpenAI**: nur Batch, ohne Vergleich. Das Schreiben in den Cache, das OpenAI ab GPT-5.6 gesondert berechnet, ist **nicht** eingerechnet: Die Tabelle hat keinen Preis dafür, und wie die Nutzungsangaben es zur Eingabe zählen, ist nicht eindeutig dokumentiert. Die Schätzung kann bei OpenAI deshalb zu niedrig sein, der Tooltip an der Zeile sagt es.
- **Noch nicht fertige Läufe**: Bei einem Hintergrund-Lauf, der noch läuft, gilt die Summe nur für die fertigen Prompts, und der Satz sagt es („der bisher fertigen Prompts (1 von 2)“). Zeilen ohne Token (Fehler, Abbruch, Ablauf) kosten nichts.
- **Ältere synchrone Einträge** zeigen die Kosten auch, zum Standardpreis und ohne Vergleich.
- **Darstellung**: Beträge in USD mit zwei bis vier Nachkommastellen („Kosten ca. 0,0123 USD“, unter 0,0001 steht „< 0,0001“). Ein Tooltip an der Summenzeile erklärt, was eingerechnet ist. Es ist eine Schätzung, keine Abrechnung: Maßgeblich ist die Rechnung des Anbieters (Abschnitt 11).

**Gespräch fortsetzen.** Gemini behält zwischen zwei Anfragen nichts. Wer ein früheres Gespräch weiterführen will, muss es mitsenden. „Gespräch fortsetzen“ (unter jeder Antwort mit Text) macht das in einem Schritt:

1. Die App baut aus dem früheren Prompt und deiner Antwort dazu einen Text (Format in Abschnitt 7). Bei älteren synchronen Gesprächen (mehrere Prompts pro Gespräch) gehören alle früheren Runden dieses Gesprächs bis zur gewählten Antwort dazu.
2. Sie legt den Text ins Feld „Prompts“ von „Neue Anfrage“ und übernimmt Systemanweisung, Modus, Denktiefe und Token-Limit des Eintrags. Die Dateien müssen wieder angehängt werden (der Hinweis nennt sie).
3. Man schreibt den neuen Prompt unter `[Mein neuer Prompt]` und startet. Der Start bleibt gesperrt, solange dort nichts steht.

„Verlaufstext zeigen“ zeigt denselben Text zum Kopieren, z. B. für ein anderes Programm.

- **Beliebig oft**: Setzt man eine Fortsetzung selbst fort, liest die App den Verlauf aus dem gesendeten Prompt zurück und hängt nur die neue Runde an (Runde 1, 2, 3 …). Verläufe werden nicht ineinander geschachtelt.
- **Kosten**: Der Verlauf geht bei jeder Anfrage als Text mit und zählt als Eingabe. Lange Verläufe kosten entsprechend. Die Dateien stehen weiter an erster Stelle, der gemeinsame Anfang (Prefix) für das implizite Caching bleibt also gleich.
- **Was es technisch ist**: eine einzelne Nutzernachricht mit eingefügtem Verlauf, kein echter Mehr-Runden-Verlauf mit Modellrolle (siehe Abschnitt 11).

## 5. Kosten sparen: Batch und Caching

### Carbon-Besonderheiten (laut Google-Doku, Stand 11.11.2026)

Carbon (`gemini-4-carbon`, seit 10.11.2026) und sein Vorgänger Argon haben laut Google dieselbe Schnittstelle, dieselben Denkstufen, dasselbe Kontextfenster und denselben Preis. Der Umstieg ist deshalb nur ein anderer Modellname. Der Unterschied: Carbon verbraucht bei schweren Aufgaben mehr Denk-Token und braucht länger. Die Tabelle gilt für beide Modelle, wo nichts anderes steht. Ältere Verlaufseinträge behalten ihr Modell (z. B. `gemini-4-argon`), „Eingaben übernehmen“ trägt es im Feld „Modell“ wieder ein.

| Thema | Verhalten | Folge in der App |
|---|---|---|
| Modell-ID | `gemini-4-carbon` (Vorgänger: `gemini-4-argon`) | steht in der Liste im Feld „Modell“ (Issue #11), vorausgewählt ist das teuerste Modell der Liste |
| Denktiefe | `thinking_level` ∈ {`low`, `medium`, `high`}, Standard `medium` | Auswahl „Denktiefe“, „Standard“ sendet nichts |
| Denk-Token | zählen zum Limit `max_output_tokens` und werden wie Ausgabe-Token berechnet (Preisseite). Carbon kann mehr davon verbrauchen als Argon. Google empfiehlt ein Limit ab 32.768, zum Sparen die Denktiefe zu senken | Warnung bei `MAX_TOKENS`, Voreinstellungen 32.768 (Batch) und 262.144 (Hintergrund) |
| Explizites Caching | wird für Carbon (wie für Argon) nicht unterstützt, Aufrufe mit `cached_content` entfallen | kein `cached_content` in der App |
| Implizites Caching | automatisch ab 4.096 Token, gecachte Eingabe-Token 95 % günstiger, keine Garantie | Dateien ganz vorn in fester Reihenfolge |
| Batch | JSONL-Datei mit Zeilen `{"key", "request"}`, 50 % des Standardpreises, Ziel 24 Stunden, Ergebnisse 6 Wochen abrufbar | Batch-Modus |
| Batch-Ausgabelimit | 32.768 Token, kein Long Decode (API-Fehler sonst: „max_output_tokens cannot exceed 32768“). Der Batch läuft über `generateContent` (nicht streamend: 32.768 je Anfrage), und die Interactions API, die 65.536 und Long Decode kennt, bietet laut Google noch keinen Batch. Beobachtet bei Argon, für Carbon nennt die Doku keinen anderen Wert (ungeprüft). Prüfen lässt es sich so: `BATCH_MAX_OUT` auf `65536` setzen und einen kleinen Batch starten, lehnt die API ab, erscheint der Fehler schon beim Start | Feld im Batch-Modus begrenzt |
| Ausgabe pro Anfrage | `generateContent`: 32.768 (nicht streamend), 65.536 (streamend). Das SDK setzt automatisch fort (Long Decode), bis 1.048.576 | nicht genutzt: Der Batch bleibt bei 32.768, Long Decode gibt es im Modus „Hintergrund“ |
| Hintergrund (Long Decode) | Interactions API: 65.536 je Interaktion, wenn `background` fehlt oder `max_output_tokens` nicht gesetzt ist (höhere Werte ohne `background=true` lehnt die API mit 400 ab). Mit `background=true` (verlangt `store=true`) und `max_output_tokens` über 65.536 setzen Googles Server die Antwort in Schritten zu je 64K Token fort, bis 1.048.576 minus Eingabe, Laufzeit bis 24 Stunden. Jedes Token jedes Schritts wird berechnet, wiederholte Eingabe ist durch implizites Caching 95 % günstiger. Google bewahrt Interaktionen bei kostenpflichtigen Konten bis zu 55 Tage auf (in AI Studio auf 7, 14, 28 oder 55 Tage einstellbar), bei kostenlosen 1 Tag | Modus „Hintergrund“, Feld bis 1.048.576, Voreinstellung 262.144 (Empfehlung der Doku für schwere Aufgaben) |
| Timeouts | mindestens 15 bis 20 Minuten pro Aufruf empfohlen (Carbon denkt länger als Argon) | nicht nötig: Batch und Hintergrund-Modus warten nicht auf die Antwort, die App legt nur an, fragt ab und bricht ab (im früheren synchronen Modus waren es 25 Minuten) |
| Preis | wie Argon. Standard je 1 Mio. Token: 2 $ Eingabe und 10 $ Ausgabe (inklusive Denk-Token) bis 30.11.2026, ab 01.12.2026 4 $ und 20 $. Batch: die Hälfte | die Kosten-Infobox unter „Modell“ (Abschnitt 4) nennt die Preise für Batch und Hintergrund und kündigt den Wechsel vom 01.12.2026 an |
| Thought Signatures | Modellantwort unverändert in den Verlauf zurückgeben | entfällt: Die App sendet keinen Mehr-Runden-Verlauf mehr, „Gespräch fortsetzen“ schickt den Verlauf als Text (Abschnitt 11) |

### Cache-Strategie der App

Implizites Caching vergleicht den **Anfang (Prefix)** einer Anfrage mit früheren Anfragen. Deshalb gilt in jeder Anfrage dieselbe Reihenfolge:

```text
[Systemanweisung]  [Datei 1] [Datei 2] …  [Prompt]
 ^ stabil           ^ immer gleiche Reihenfolge, ganz vorn      ^ variabel, ganz hinten
```

- Nichts Variables (Zeitstempel, IDs, Prompt-Text) vor die Dateien setzen.
- Andere Dateimenge oder -reihenfolge, andere Systemanweisung oder anderes Modell ergeben einen anderen Prefix und damit keine Treffer.
- Hochgeladene Dateien werden über ihren SHA-256 in `data/pdf_files.json` gemerkt, damit dieselbe Datei-Referenz (URI) auch nach einem Neustart benutzt wird, solange die Files API sie noch hält (derzeit 48 Stunden). Ob Google intern Dateiinhalt oder Datei-Referenz vergleicht, ist nicht dokumentiert. Eine gleiche Referenz ist der sicherere Weg.
- **Batch** läuft asynchron, die Verarbeitungszeitpunkte bestimmt Google. Zu implizitem Caching im Batch steht in der Doku nichts. Die Batch-Doku nennt Caching dort nur über `cached_content` (explizit, bei Carbon nicht möglich).
- **Hintergrund** startet alle Prompts gleichzeitig. Ein Cache-Treffer für die Dateien ist deshalb weniger wahrscheinlich, weil keine erste Anfrage den Cache vorher füllt. Bei Long Decode zählt `total_input_tokens` die Eingabe jedes 64K-Schritts erneut mit (vor allem als Cache-Token) und ist deshalb viel größer als der Kontext. Für dessen Größe gilt: Token der Dateien plus Denk- plus Ausgabe-Token.
- Sicher sparen lässt sich nur, wenn die Datei gar nicht mehrfach gesendet wird (mehrere Fragen in einem Prompt) oder mit explizitem Caching. Das kennen Carbon und Argon nicht, und bei Claude (Kästchen „Prompt-Cache“, siehe unten) ist der Gewinn in einem Batch nicht garantiert. Mehrere Fragen in einem Prompt sind in der App nicht eingebaut.

### Beobachtung aus der Praxis

Erster echter Batch (19.10.2026, noch mit Argon): 3 Prompts, 1 PDF, je rund 80.260 Eingabe-Token, Denk-Token 2.188 bis 3.359, Ausgabe-Token 1.133 bis 1.827. **Cache-Token: überall 0.** Das deckt sich mit der Annahme, dass Batch bei Argon keine verlässlichen impliziten Treffer liefert. Für Carbon liegt noch keine eigene Beobachtung vor. Ob die API das Feld in Batch-Ergebnissen unter anderem Namen führt, lässt sich im einklappbaren `usage`-JSON jeder Antwort prüfen (die App liest `cachedContentTokenCount`, `cached_content_token_count`, `totalCachedTokens`, `total_cached_tokens`).

Erster Carbon-Batch (12.11.2026, der Eintrag aus Issue #19): Denktiefe `high`, max. 32.768 Ausgabe-Token, Eingabe 32.407 Token. Ergebnis: `finishReason: MAX_TOKENS` mit 32.765 Denk- und nur 3 Ausgabe-Token, also keine Antwort: Carbon hat das gesamte Limit mit Denken verbraucht. Abhilfe: Modus „Hintergrund“ mit höherem Limit (Long Decode) oder eine niedrigere Denktiefe.

### OpenAI-Besonderheiten (laut OpenAI-Doku, Stand 10.11.2026)

| Thema | Verhalten | Folge in der App |
|---|---|---|
| Schnittstelle | Die App nutzt nur die Responses API (Batch-Endpunkt `/v1/responses`). Sie nimmt `reasoning` und Dateien als `file_id` entgegen | `OPENAI_ENDPOINT` |
| Batch | JSONL-Datei mit Zeilen `{"custom_id", "method", "url", "body"}`, 50 % des Standardpreises, Fenster `24h`. Eine Batch-Datei darf nur Anfragen an **ein** Modell enthalten, höchstens 50.000 Anfragen und 200 MB | Batch-Modus, ein Modell je Batch |
| Warteschlangenlimit | OpenAI begrenzt je Modell und Kontostufe die Summe der Token aller eingereihten Batches. Eine lange Datei zählt in jedem Prompt voll mit. Überschreitet ein Batch das Limit, endet er mit `failed` | Der Fehlertext (typisch `token_limit_exceeded`) steht im Eintrag |
| Dokumente und Text | Files API mit Zweck `user_data`, in der Anfrage als `input_file` mit `file_id`. Pro Datei unter 50 MB, zusammen höchstens 50 MB je Anfrage. Außer bei PDFs liest das Modell nur den Text (Bilder und Diagramme in Word- oder PowerPoint-Dateien gehen verloren), von Tabellen je Blatt nur die ersten 1.000 Zeilen | `upload_file_openai()`, `openai_file_part()` |
| Bilder | Files API mit Zweck `vision`, in der Anfrage als `input_image` mit `file_id` (`.png`, `.jpg`, `.jpeg`, `.webp`). `detail` wird nicht gesetzt (`auto`) | `upload_file_openai()`, `openai_file_part()` |
| Audio und Video | nimmt die App bei OpenAI nicht an: Die Dokumentation zu Dateieingaben kennt dafür keine Typen | `check_files()` sperrt den Start |
| PDF-Token | OpenAI schickt Text **und** Seitenbilder des PDFs ans Modell, das erhöht die Eingabe-Token. `detail` (`auto`, `low`, `high`) steuert die Bildverarbeitung. `auto` bedeutet bei GPT-5.6 und neuer `high`, bei älteren Modellen `low` | `detail` wird nicht gesetzt (Idee in Abschnitt 11) |
| Denktiefe | `reasoning.effort` mit `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. Welche Stufen ein Modell kennt, ist verschieden (`gpt-6-astra` kennt kein `none`) | Auswahl „Denktiefe“ mit allen Stufen, „Standard“ sendet nichts. Die API lehnt unpassende Stufen ab |
| Denk-Token | zählen zu `max_output_tokens` und sind in `output_tokens` enthalten (`output_tokens_details.reasoning_tokens`) | `parse_openai_line()` trennt sie ab |
| Caching | automatisch ab 1.024 Token bei gleichem Prefix, ohne Parameter. Bei GPT-5.6 und neuer wird das Schreiben in den Cache gesondert berechnet (`cache_write_tokens` in den Nutzungsdaten) | Dateien ganz vorn. Spalte „Cache“ = `cached_tokens` |
| Dateien bei OpenAI | `user_data`-Dateien bleiben bis zum Löschen, wenn man keinen Ablauf setzt (mit Ablauf: 1 Stunde bis 30 Tage) | Ablauf nach 3 Tagen (`OPENAI_FILE_TTL`) |
| Ergebnisse | `output_file_id` (Antworten) und `error_file_id` (fehlgeschlagene Anfragen). Bei `expired` und `cancelled` liegen dort die bis dahin fertigen Antworten und die übrigen Fehler | `fetch_openai_batch()` liest beide Dateien |

Die **Cache-Strategie** (Reihenfolge `[Systemanweisung] [Datei 1] [Datei 2] … [Prompt]`) gilt bei OpenAI genauso: Die Anfragen eines Batches laufen in unbestimmter Reihenfolge und Zeit, ob und wie oft sie Treffer bekommen, ist unbekannt. Die Preise für Eingabe, Cache-Lesen und Cache-Schreiben stehen je Modell auf der OpenAI-Preisseite.

### Claude-Besonderheiten (laut Anthropic-Doku, Stand 18.11.2026)

| Thema | Verhalten | Folge in der App |
|---|---|---|
| Schnittstelle | Message Batches API: je Prompt eine Anfrage `{"custom_id", "params"}`, `params` sind die Parameter der Messages API. Das SDK nimmt eine Liste, keine JSONL-Datei. `custom_id` erlaubt 1 bis 64 Zeichen aus Buchstaben, Ziffern, `_` und `-` | `start_claude_batch()` und `claude_request()`. Die App legt dieselben Zeilen zur Kontrolle in `data/requests_claude_<unixzeit>.jsonl` ab. Schlüssel `prompt-1`, `prompt-2`, … |
| Batch | 50 % des Standardpreises, höchstens 100.000 Anfragen oder 256 MB je Batch, die meisten Batches enden innerhalb einer Stunde, Anfragen, die nach 24 Stunden noch offen sind, verfallen (`expired`). Die Ergebnisse bleiben 29 Tage nach dem Anlegen abrufbar | Batch-Modus. Die App sichert die Ergebnisse lokal, sobald der Batch endet |
| Ergebnisse | Erst wenn der Batch endet (`processing_status` `ended`), je Anfrage als `succeeded`, `errored`, `canceled` oder `expired`. Die Reihenfolge entspricht nicht der der Anfragen, es zählt `custom_id`. Die Parameter prüft die API erst am Ende, ein falscher Wert erscheint deshalb als `errored` je Anfrage | `fetch_claude_batch()` lädt die Ergebnisse, `parse_claude_line()` macht Zeilen daraus, `sort_rows()` ordnet sie nach der Nummer |
| Abbruch | Der Batch geht auf `canceling` und endet dann. Anfragen, die noch nicht begonnen hatten, sind `canceled`. Abgebrochene, abgelaufene und fehlgeschlagene Anfragen werden nicht berechnet | „Batch abbrechen“ (`cancel_batch()`) |
| Denktiefe | `output_config.effort` mit `low`, `medium`, `high`, `xhigh`, `max`. Ohne Angabe gilt die Voreinstellung des Modells (`high`, bei Opus 5.5 und Haiku 5.5 `medium`). Die aktuellen Modelle denken adaptiv, ein `thinking`-Parameter ist nicht nötig. Nicht jedes Modell kennt alle Stufen | Auswahl „Denktiefe“ mit allen Stufen, „Standard“ sendet nichts. Die API lehnt unpassende Stufen je Anfrage ab |
| Denk-Token | zählen zu `max_tokens` und werden als Ausgabe-Token berechnet, auch wenn der Denktext nicht zurückkommt. `usage.output_tokens_details.thinking_tokens` nennt ihren Anteil | `parse_claude_line()` trennt sie ab |
| Ausgabelimit | `max_tokens` ist Pflicht. Die aktuellen Modelle erlauben bis 128.000, im Batch bei einigen Modellen mit einem Beta-Header (`output-300k-2026-03-24`) bis 300.000 | Feld bis 128.000 (`CLAUDE_MAX_OUT`, Voreinstellung 32.768). Den Beta-Header setzt die App nicht (Abschnitt 11) |
| Dokumente, Text und Bilder | Files API (ohne Beta-Header), in der Anfrage als `file_id`: PDF und `text/plain` als `document`-Block, Bilder als `image`-Block. Word, PowerPoint und Excel liest Claude nicht als Dokument. Dateinamen müssen 1 bis 255 Zeichen lang sein und dürfen u. a. weder `:` noch `?` noch `*` noch Schrägstriche enthalten | `upload_file_claude()`, `claude_file_part()`, `claude_mime()`, `claude_filename()`. `check_files()` sperrt Office-Dateien, Audio und Video |
| Dateien bei Anthropic | Mit `expires_in_seconds` lässt sich eine Lebensdauer von 1 Stunde bis 90 Tagen setzen. Die Metadaten einer abgelaufenen Datei liefert die API noch eine Weile, die Datei selbst nicht mehr | Ablauf nach 3 Tagen (`CLAUDE_FILE_TTL`). Eine gemerkte Datei wird nur wiederverwendet, wenn sie noch mindestens 26 Stunden lebt (`CLAUDE_FILE_MIN_LEFT`), denn ein Batch läuft bis zu 24 Stunden (`file_alive()`) |
| Caching | nur explizit: `cache_control` auf einem Block markiert den Prefix bis dorthin (Reihenfolge Systemanweisung, dann Nachrichten). Lebensdauer 5 Minuten (Voreinstellung) oder 1 Stunde (`ttl`). Schreiben kostet das 1,25-fache (5 Minuten) bzw. das Doppelte (1 Stunde) des Eingabepreises, Lesen höchstens ein Zehntel. Die Mindestlänge liegt je nach Modell zwischen 512 und 4.096 Token, Kürzeres wird nicht gecacht. Anthropic rät bei Batches zur 1 Stunde und nennt Trefferquoten von 30 bis 98 % | Kästchen „Dateien im Prompt-Cache halten (1 Stunde)“ (`CLAUDE_CACHE_TTL`): Die Marke sitzt auf der letzten Datei jeder Anfrage |
| Eingabe-Token | `input_tokens` zählt nur Token ohne Cache, dazu kommen `cache_read_input_tokens` und `cache_creation_input_tokens` | Spalte „Eingabe“ = Summe, „Cache“ = gelesen |
| Abschlussgründe | `end_turn`, `max_tokens`, `refusal`, `model_context_window_exceeded` u. a. | `STOP`, `MAX_TOKENS`, sonst in Großbuchstaben (Abschnitt 4) |

Die **Cache-Strategie** (Reihenfolge `[Systemanweisung] [Datei 1] [Datei 2] … [Prompt]`) gilt bei Claude genauso, nur dass Claude den Prefix nicht von selbst vergleicht: Die Marke auf der letzten Datei sagt, bis wohin er gilt. Der Prompt steht dahinter und darf sich unterscheiden.

**Wann lohnt sich der Prompt-Cache?** Die Anfragen eines Batches laufen gleichzeitig, und ein Eintrag steht erst zur Verfügung, wenn die erste Antwort begonnen hat. Eine Anfrage, die nicht trifft, schreibt den Cache selbst und zahlt dafür den Aufschlag. Das ist eine eigene Rechnung, keine Angabe von Anthropic: Mit Aufschlag 2 (1 Stunde) und Lesefaktor 0,1 kosten die Dateien bei N Prompts ohne Cache das N-fache ihres Eingabepreises F. Mit Cache sind es 2·F für die erste Anfrage plus für jede weitere p·0,1·F bei einem Treffer und 2·F bei einem Fehlversuch (p ist der Anteil der Treffer). Gleichstand gibt es bei N = 3 ab p ≈ 0,8, bei N = 10 ab p ≈ 0,6 und bei N = 20 ab p ≈ 0,55. Bei einem einzelnen Prompt kostet der Cache immer das Doppelte. Darum ist das Kästchen aus, solange man es nicht anschaltet, und es lohnt sich erst bei vielen Prompts zu denselben Dateien. Ob die Treffer tatsächlich zustande kommen, zeigt die Spalte „Cache“ der Ergebnisse (und im rohen `usage` `cache_creation_input_tokens`).

## 6. Konfiguration

### 6.1 API-Key und Modell

- Seitenleiste „Gemini API-Key“, „OpenAI API-Key“ und „Claude API-Key“ (Passwortfelder) oder die Umgebungsvariablen `GEMINI_API_KEY`, `OPENAI_API_KEY` und `ANTHROPIC_API_KEY` (werden als Vorbelegung genutzt). Die Keys werden nicht gespeichert. Gebraucht wird der Key des gewählten Anbieters, dazu die der anderen Anbieter, wenn man deren Verlaufseinträge abfragen will.
- Seitenleiste „Anbieter für neue Anfragen“: `Gemini` (Voreinstellung), `OpenAI` oder `Claude`.
- Seitenleiste „Modell“ (Issue #11), je Anbieter ein eigenes Feld als Combobox (`st.selectbox` mit `accept_new_options=True` und `required=True`, gezeichnet von `model_field()` in `views.py`). Die Liste kommt aus `PRICES` (`model_choices()` in `pricing.py`): die aktuellen Modelle des Anbieters, höchstens `MAX_MODELS`, dazu die Modelle aus `conf/prices.toml` (Abschnitt 6.6, die Grenze gilt nur für `PRICES`), das teuerste zuerst, und der erste Eintrag ist die Voreinstellung (`default_model()`). Sortiert wird nach dem Ausgabepreis am heutigen Tag, bei gleichem Preis gilt die Reihenfolge der Tabelle. Weil sich Preise ändern, ändert sich auch die Reihenfolge: Bei Gemini 4 ist bis 30.11.2026 Neon das teuerste Modell und damit vorausgewählt, ab 01.12.2026 sind es Carbon und Argon (Gleichstand, Carbon steht in der Tabelle zuerst). Eine laufende Sitzung behält ihre Wahl, nur eine neue Sitzung nimmt den ersten Eintrag der Liste von heute. Bei OpenAI steht das ältere `gpt-6-astra` (10/50 USD) vor dem neueren `gpt-6.2-astra` (8/40 USD), weil es mehr kostet: Die Reihenfolge folgt dem Preis, nicht dem Alter. Ein anderer Name lässt sich eintippen. Gemini: Die App ist auf die Gemini-4-Modelle zugeschnitten (Batch-Limit, `thinking_level`-Werte, Caching-Annahmen), ein anderes Modell ist möglich, aber nicht erprobt. OpenAI: Jedes Modell mit Responses API, Batch API und Dateieingabe (bei Bildern: Bildeingabe) geht (Namen laut OpenAI-Doku und Preisseite, Stand 21.11.2026). Claude: Jedes aktuelle Modell mit Message Batches API und Dateieingabe über die Files API geht (Namen laut Anthropic-Doku, Stand 18.11.2026). Für die Denktiefe muss das Modell `effort` kennen.
- Optional die Umgebungsvariable `AI_BATCH_UI_HOME`: Ordner, unter dem `conf/` und `data/` liegen. Voreinstellung ist der Projektordner (der Ordner über `src/`), unabhängig vom Arbeitsordner. Nützlich für getrennte Datenbestände und für Tests. Bis Issue #18 hieß die Variable `GEMINI_UI_HOME`, der alte Name wird nicht mehr gelesen.

### 6.2 Konstanten im Code (`src/aibui/config.py`)

| Konstante | Wert | Bedeutung |
|---|---|---|
| `PROVIDER_GEMINI`, `PROVIDER_OPENAI`, `PROVIDER_CLAUDE` | „Gemini“, „OpenAI“, „Claude“ | Anbieter. Alle stehen im Pflichtfeld `provider` der Verlaufseinträge |
| `PROVIDERS` | alle drei Anbieter | Auswahl in der Seitenleiste, Voreinstellung ist der erste |
| `BASE` | Projektordner: Ordner über `src/` (liegt das Paket `aibui` in keinem Ordner namens `src`, der Ordner mit dem Paket), oder `AI_BATCH_UI_HOME` | Wurzel für `conf/` und `data/` (`_base_dir()`) |
| `CONF_DIR` | `BASE/conf` | Zugangsdaten, geheim |
| `DATA_DIR` | `BASE/data` | erzeugte Daten |
| `CREDENTIALS_FILE`, `TOKEN_FILE` | `conf/credentials.json`, `conf/token.json` | Drive-OAuth-Client und Drive-Login |
| `PRICES_FILE` | `conf/prices.toml` | eigene Preise, optional (Issue #39, Abschnitt 6.6) |
| `HISTORY` | `data/batch_jobs.json` | Verlauf und Ergebnisse |
| `FILES_DB` | `data/pdf_files.json` | Datei-Hash → Datei in der Gemini Files API (der Dateiname stammt aus der Zeit, als nur PDFs möglich waren) |
| `OPENAI_FILES_DB` | `data/openai_files.json` | Datei-Hash → Datei in der OpenAI Files API |
| `CLAUDE_FILES_DB` | `data/claude_files.json` | Datei-Hash → Datei in der Files API von Anthropic |
| `SCOPES` | `drive.readonly` | Drive-Berechtigung (nur lesen) |
| `POLL_SECONDS` | `10` | Abstand der automatischen Prüfung |
| `DONE` | 4 `JOB_STATE_*`-Endzustände (Gemini), `completed`, `failed`, `cancelled`, `expired` (OpenAI) und `ended` (Claude) | Wann ein Batch als abgeschlossen gilt |
| `BATCH_MAX_OUT` | `32768` | Batch-Limit für Ausgabe-Token |
| `BG_MAX_OUT` | `1_048_576` | Obergrenze im Hintergrund-Modus (Long Decode auf Googles Servern, minus Eingabe) |
| `BG_DEFAULT_OUT` | `262_144` | Voreinstellung im Hintergrund-Modus (Empfehlung der Google-Doku für schwere Aufgaben) |
| `BG_RUNNING` | `in_progress`, `queued` | Status einer Hintergrund-Interaktion, solange sie läuft (jeder andere gilt als Ende) |
| `MAX_POLL_ERRORS` | `3` | So viele Abruffehler in Folge stoppen die automatische Prüfung |
| `TABS` | „Neue Anfrage“, „Jobs und Ergebnisse“ | Tab-Namen (auch Schlüsselwerte für `view`) |
| `MODE_BATCH`, `MODE_BG` | Radio-Texte | Werte des Modus-Schalters |
| `THINK_LEVELS` | Standard, low, medium, high | Auswahl Denktiefe bei Gemini |
| `OPENAI_EFFORTS` | Standard, none, minimal, low, medium, high, xhigh, max | Auswahl Denktiefe bei OpenAI (die Stufen von `reasoning.effort`) |
| `OPENAI_ENDPOINT` | `/v1/responses` | Endpunkt der OpenAI Batch API (JSONL-Zeile und `batches.create`) |
| `OPENAI_MAX_OUT` | `128_000` | Obergrenze für Ausgabe-Token bei OpenAI, je Modell kann sie niedriger sein |
| `OPENAI_FILE_TTL` | 3 Tage | Ablauf hochgeladener Dateien bei OpenAI (erlaubt sind 1 Stunde bis 30 Tage) |
| `CLAUDE_EFFORTS` | Standard, low, medium, high, xhigh, max | Auswahl Denktiefe bei Claude (die Stufen von `output_config.effort`) |
| `CLAUDE_MAX_OUT` | `128_000` | Obergrenze für Ausgabe-Token bei Claude, je Modell kann sie niedriger sein |
| `CLAUDE_FILE_TTL` | 3 Tage | Ablauf hochgeladener Dateien bei Anthropic (erlaubt sind 1 Stunde bis 90 Tage) |
| `CLAUDE_FILE_MIN_LEFT` | 26 Stunden | So lange muss eine gemerkte Datei noch leben, damit die App sie wiederverwendet: Ein Batch läuft bis zu 24 Stunden |
| `CLAUDE_CACHE_TTL` | `1h` | Lebensdauer der Cache-Marke (`ttl`) beim Prompt-Cache von Claude: Ein Batch braucht oft länger als die 5 Minuten der Voreinstellung |
| `DEFAULT_NAME_MODEL` | `gemini-3.5-flash-lite` | Voreinstellung für das Modell, das die Namen der Einträge erzeugt (immer Gemini, in der Seitenleiste änderbar) |
| `NAME_THINK_LEVELS`, `DEFAULT_NAME_THINK` | minimal, low, medium, high, Voreinstellung medium | Denktiefe der Namensvergabe. „Standard“ fehlt mit Absicht: Jedes Modell hat eine eigene Voreinstellung (`gemini-3.5-flash-lite` denkt ohne Angabe auf `minimal`), darum wird die Stufe immer gesendet |
| `NAME_MAX_OUT` | `8192` | Denk- plus Ausgabe-Token des Namensaufrufs (der Name selbst braucht nur wenige) |
| `NAME_TIMEOUT_MS` | `30_000` | Zeitlimit des Namensaufrufs in Millisekunden: Er soll den Start nicht lange aufhalten |
| `NAME_MAX_CHARS` | `60` | längere Namen werden an einer Wortgrenze gekürzt und enden dann auf „…“ |
| `NAME_SOURCE_PROMPTS`, `NAME_SOURCE_CHARS` | `3`, `1500` | So viel geht an das Modell: höchstens die ersten drei Prompts, zusammen höchstens 1.500 Zeichen |
| `NAME_INSTRUCTION` | Anweisung an das Modell | Systemanweisung der Namensvergabe (kurzer Name in der Sprache der Prompts, die Prompts nicht ausführen) |
| `FORM_KEYS` | Schlüssel der Formularfelder | Werte, die vor jedem Lauf neu zugewiesen werden, damit sie einen Anbieterwechsel überstehen (siehe „Streamlit-Besonderheiten“) |
| `HINT` | „(bitte den Tab nicht wechseln)“ | Zusatz im Statusfeld beim Start |
| `SEPARATOR` | Muster: Zeile nur mit `---` | trennt im Formular die Prompts |
| `TALK_INTRO` | Einleitungssatz | steht über jedem Gesprächsverlauf („Unten steht der bisherige Verlauf …“) |
| `TALK_BEGIN`, `TALK_END`, `TALK_NEW` | `[Bisheriger Gesprächsverlauf]`, `[Ende des bisherigen Gesprächsverlaufs]`, `[Mein neuer Prompt]` | Marken des Verlaufstexts, je in einer eigenen Zeile |
| `TALK_MINE`, `TALK_YOURS` | `[Runde {n}: Mein Prompt]`, `[Runde {n}: Deine Antwort dazu]` | Marken je Runde |
| `TALK_MARK` | Muster | erkennt genau diese Marken wieder (`parse_conversation()`) |

Die **Preise** der Kosten-Infobox (Issue #12) und die **Liste der Modelle** im Feld „Modell“ (Issue #11) stehen nicht in `config.py`, sondern in `src/aibui/pricing.py`: `PRICES` (Standardpreise in USD je 1 Mio. Token je Anbieter und Modell, mit Preisstufen nach der Länge des Prompts und mit dem Tag, ab dem ein Preis gilt), `MAX_MODELS` (`5`: So viele Modelle hat die Tabelle je Anbieter höchstens, ein Test prüft es), `BATCH_FACTOR` (`0.5`: Der Batch kostet bei allen drei Anbietern die Hälfte), `PRICES_AS_OF` (Stand der Tabelle, steht unter der Infobox) und `CLAUDE_CACHE_WRITE` (`1.25` bei fünf Minuten, `2` bei einer Stunde Lebensdauer: so viel mal den Eingabepreis kostet bei Claude das Schreiben in den Cache, Issue #39. Ein Test prüft, dass `CLAUDE_CACHE_TTL` dort steht). Die Voreinstellung des Felds „Modell“ ist keine Konstante mehr, sondern der erste Eintrag von `model_choices()`. Eigene Preise ohne Änderung am Code: Abschnitt 6.6. Änderungen an der eingebauten Tabelle: Abschnitt 9.2.

Weitere Voreinstellungen stehen direkt im Hauptskript (`src/ai_batch_ui.py`): Denktiefe `high` (`st.session_state.setdefault("think", "high")`), Ausgabe-Token im Batch 32.768 und im Hintergrund `BG_DEFAULT_OUT`. Bei OpenAI: Denktiefe „Standard“ (`st.session_state.setdefault("effort", "Standard")`) und Ausgabe-Token 32.768. Bei Claude: Denktiefe „Standard“ (`st.session_state.setdefault("effort_claude", "Standard")`), Ausgabe-Token 32.768 und der Cache-Schalter aus. Wiederholungen bei vorübergehenden Fehlern: `create_interaction()` (Hintergrund) versucht es bis zu dreimal, Pause 10 s und 20 s, nur bei 429: Nach einem 5xx könnte die Interaktion schon angelegt sein, und ein zweiter Aufruf würde sie doppelt berechnen. Das SDK wiederholt 5xx selbst, kurz und höchstens zweimal.

### 6.3 Streamlit-Konfiguration (optional, `.streamlit/config.toml`)

```toml
[server]
fileWatcherType = "none"   # vermeidet „inotify watch limit reached“ unter Linux, Änderungen am Code laden dann nicht automatisch
maxUploadSize = 500        # MB pro hochgeladener Datei (Standard 200)
```

Streamlit liest diese Datei aus `.streamlit/` im **Arbeitsordner**, in dem `streamlit run` gestartet wird, nicht aus `conf/`. Am besten startet man die App im Projektordner (dann passt auch der Pfad `src/ai_batch_ui.py`).

### 6.4 Google Drive einrichten (optional)

Nur nötig für „PDFs aus Google Drive hinzufügen“. Der Datei-Upload funktioniert ohne.

1. [Google Cloud Console](https://console.cloud.google.com) mit dem Konto öffnen, auf dessen Drive zugegriffen werden soll. Neues Projekt anlegen (die Drive API ist kostenlos, ein Rechnungskonto sollte dafür in der Regel nicht nötig sein).
2. **Drive API aktivieren**: `https://console.cloud.google.com/flows/enableapi?apiid=drive.googleapis.com`, Projekt wählen, aktivieren.
3. **Google Auth Platform** (Menü) → „Get started“: App-Name, Support-E-Mail, Zielgruppe „External“ (mit Workspace-Konto „Internal“), Kontakt-E-Mail, Richtlinie akzeptieren.
4. Nur bei „External“: unter „Audience“ die eigene Google-Adresse als **Test user** eintragen (sonst „Zugriff blockiert“).
5. Unter „Data Access“ den Scope `https://www.googleapis.com/auth/drive.readonly` hinzufügen.
6. Unter „Clients“ → „Create client“ → Anwendungstyp **Desktop-App** → JSON herunterladen und als `conf/credentials.json` ablegen (der Ordner `conf/` liegt im Projektordner neben `src/` und wird beim Start angelegt).
7. In der App „Meine PDFs aus Drive laden“. Beim ersten Zugriff öffnet sich der Browser zur Freigabe (Warnung „Google hat diese App nicht überprüft“ über „Erweitert“ bestätigen). Danach liegt `conf/token.json` vor.

Hinweise:

- Im Status „Testing“ (Zielgruppe „External“) läuft die Freigabe nach **7 Tagen** ab. Die App öffnet dann selbstständig erneut den Browser zur Anmeldung (`drive_service()` fängt `RefreshError`). Dauerhaft vermeidet das „Publish app“ unter „Audience“ (Status „In production“, Warnung bleibt) oder ein Workspace-Konto mit „Internal“.
- Ohne `conf/credentials.json` meldet die App einen klaren Fehler samt Zielordner. `conf/token.json` zu löschen erzwingt eine neue Anmeldung.
- Menünamen der Konsole können je nach Sprache und Version abweichen. Maßgeblich ist der Drive-Python-Quickstart (Abschnitt 13).

### 6.5 Abhängigkeiten

| Paket | Mindestversion | Wofür |
|---|---|---|
| `streamlit` | 1.67.0 | Oberfläche. `st.tabs` kennt mit `key` und `on_change` den aktiven Tab (`.open`), und `AppTest` unterstützt Datei-Uploads. Ältere Versionen werden nicht unterstützt. |
| `google-genai` | 3.3.0 | Gemini-SDK (Files API, Batch-API, Interactions API für den Hintergrund-Modus). Ältere Versionen werden nicht unterstützt. |
| `openai` | 3.51.0 | OpenAI-SDK (Files API, Batch API). `files.create` kennt den Parameter `expires_after`, mit dem die App hochgeladene Dateien ablaufen lässt. Wird erst bei OpenAI-Nutzung importiert: Ohne das Paket läuft Gemini weiter, und die App meldet bei OpenAI, was fehlt. Ältere Versionen werden nicht unterstützt. |
| `anthropic` | 2.10.0 | Anthropic-SDK (Files API, Message Batches API). `files.upload` kennt den Parameter `expires_in_seconds`, mit dem die App hochgeladene Dateien ablaufen lässt, und `Usage` führt `output_tokens_details.thinking_tokens`. Wird erst bei Claude-Nutzung importiert: Ohne das Paket läuft Gemini weiter, und die App meldet bei Claude, was fehlt. Ältere Versionen werden nicht unterstützt. |
| `google-api-python-client`, `google-auth-oauthlib` | beliebig | Drive-Zugriff (werden erst bei Drive-Nutzung importiert) |
| `pytest` | 8 | nur für die Tests (`requirements-dev.txt`) |
| `pyyaml` | 6 | nur für die Tests (`requirements-dev.txt`), prüft die Workflow-Datei |

Die Mindestversionen (Python 3.12, Streamlit 1.67.0, google-genai 3.3.0, openai 3.51.0, anthropic 2.10.0) sind die Versionen, mit denen die Testsuite zuletzt vollständig lief (Abschnitt 13). Ältere Versionen werden nicht unterstützt, der Code enthält keine Ausweichzweige dafür. Beim Anheben der Mindestversionen `requirements.txt`, die Voraussetzungen in Abschnitt 3 und, bei Python, die Matrix des Workflows (Abschnitt 9.5) mitziehen. `tests/test_docs.py` und `tests/test_ci.py` melden Abweichungen.

### 6.6 Eigene Preise (`conf/prices.toml`, Issue #39)

Die Preise der Kosten-Infobox, der Auswahl im Feld „Modell“ und der geschätzten Kosten eines Laufs stehen in `PRICES` (`src/aibui/pricing.py`). Wer andere Preise braucht (ein Anbieter hat sie geändert, ein Rabatt, ein neues Modell), muss den Code nicht anfassen: Die optionale Datei `conf/prices.toml` (`PRICES_FILE`) ändert Preise oder ergänzt Modelle. Es ist eine TOML-Datei mit einem Eintrag `[[price]]` je Preis. TOML erlaubt Kommentare und braucht kein Zusatzpaket (das Modul `tomllib` gehört zu Python 3.12). Die Zahlen im Beispiel sind erfunden.

```toml
# conf/prices.toml: eigene Preise in USD je 1 Mio. Token im Standardtarif. Der Batch ergibt sich daraus (halber Preis).
# Ein Modell hier ersetzt alle eingebauten Preise dieses Modells, ein neuer Name ergänzt die Auswahl im Feld „Modell“.

[[price]]
provider = "Gemini"        # Gemini, OpenAI oder Claude
model = "gemini-4-neon"    # klein geschrieben, ohne Datumsstand
input = 3.5                # neue Eingabe-Token
output = 16                # Ausgabe, einschließlich Denk-Token
cache = 0.20               # Eingabe-Token aus dem Cache (ohne Cache-Rabatt: derselbe Wert wie input)

# Ein neues Modell mit einem Preiswechsel: Der Preisstand ohne from gilt von jeher, ein weiterer gilt ab dem Tag in from.
[[price]]
provider = "Claude"
model = "claude-sonnet-5-6"
input = 2
output = 10
cache = 0.10

[[price]]
provider = "Claude"
model = "claude-sonnet-5-6"
from = 2027-01-01
input = 3
output = 15
cache = 0.30

# Stufen nach der Länge des Prompts: up_to nennt die Obergrenze in Token, die letzte Stufe hat keine.
# Ein längerer Prompt zahlt den Preis der letzten Stufe für die ganze Anfrage.
[[price]]
provider = "OpenAI"
model = "gpt-6.3-astra"
up_to = 272_000
input = 8
output = 40
cache = 0.40

[[price]]
provider = "OpenAI"
model = "gpt-6.3-astra"
input = 16
output = 60
cache = 0.80
```

- **Schlüssel**: `provider`, `model`, `input`, `output` und `cache` sind Pflicht, `from` (ein Datum, auch als Text wie `"2027-01-01"`) und `up_to` (eine ganze Zahl über 0) sind optional. Preise sind Zahlen ab 0, kein Text und kein `true`. Der Anbieter heißt `Gemini`, `OpenAI` oder `Claude` (Groß- und Kleinschreibung egal), der Modellname wird klein geschrieben, ein Vorspann `models/` entfällt (wie bei `find_model()`).
- **Ersetzen, nicht ergänzen**: Steht ein eingebautes Modell in der Datei, gilt für dieses Modell nur noch, was dort steht. Wer eine Stufe oder einen eingebauten Preiswechsel behalten will, schreibt ihn mit hin. Modelle, die nicht in der Datei stehen, behalten ihre eingebauten Preise.
- **Neue Modelle** erscheinen zusammen mit den eingebauten in der Combobox „Modell“, nach Ausgabepreis sortiert (bei Gleichstand stehen die eingebauten vorn). `MAX_MODELS` gilt nur für `PRICES`, die Datei darf mehr Modelle nennen. Ein neues Modell mit dem höchsten Ausgabepreis steht damit vorn und ist vorausgewählt.
- **Preisstände und Stufen**: Einträge mit demselben Anbieter und Modell gehören zusammen. Der erste Preisstand hat kein `from`, und in jedem Preisstand hat genau eine Stufe kein `up_to` (die letzte). Die Reihenfolge in der Datei ist egal.
- **Ohne Neustart**: Die App liest die Datei bei jedem Neuzeichnen, ein geänderter Preis gilt beim nächsten Klick. Auch die Kosten fertiger Läufe ändern sich dann, denn sie werden jedes Mal neu berechnet (den Preisstand bestimmt der Starttag des Laufs, nicht der Tag der Änderung).
- **Fehler**: Die App stürzt wegen der Datei nie ab. Ein Fehler in einem Eintrag (fehlender oder unbekannter Schlüssel, Text statt Zahl, doppelter Eintrag, fehlende letzte Stufe) macht das betroffene Modell ungültig, für das dann die eingebauten Preise gelten, und eine Warnung in der Seitenleiste nennt Eintrag und Grund. Unbekannte Schlüssel zählen bewusst als Fehler: Ein Tippfehler wie `upto` ließe den Preis sonst stumm falsch gelten. Ist die Datei kein gültiges TOML, gelten alle eingebauten Preise.

## 7. Lokale Dateien und Datenformate

Die App legt `conf/` (Konfiguration und Zugangsdaten) und `data/` (erzeugte Daten) im **Projektordner** an, neben `src/` und unabhängig vom Arbeitsordner. Projektordner ist der Ordner über `src/`. Mit der Umgebungsvariable `AI_BATCH_UI_HOME` lässt sich ein anderer Ordner festlegen, unter dem beide liegen.

```text
ai-batch-ui/                        # Projektordner
├── README.md
├── requirements.txt
├── requirements-dev.txt            # zusätzlich pytest und pyyaml, nur für die Tests
├── pytest.ini                      # pytest-Einstellungen
├── src/
│   ├── ai_batch_ui.py              # Hauptskript: nur die Oberfläche
│   └── aibui/                      # Paket mit der Logik, ein Modul je Thema (Abschnitt 8)
├── tests/                          # automatisierte Tests (Abschnitt 9.3)
├── .github/workflows/tests.yml     # GitHub Actions: führt pytest automatisch aus (Abschnitt 9.5)
├── .streamlit/config.toml          # optional, Streamlit-Einstellungen (aus dem Arbeitsordner gelesen)
├── conf/                           # Konfiguration und Zugangsdaten, GEHEIM
│   ├── credentials.json            # optional: Drive-OAuth-Client (von Hand hineinlegen)
│   ├── prices.toml                 # optional: eigene Preise (Abschnitt 6.6)
│   └── token.json                  # automatisch: Drive-Login
└── data/                           # erzeugte Daten
    ├── batch_jobs.json             # Verlauf + Ergebnisse (+ batch_jobs.tmp beim Schreiben)
    ├── batch_jobs.defekt-<ts>.json # Sicherung, falls batch_jobs.json beschädigt war
    ├── pdf_files.json              # Datei-Hash -> Files-API-Name (Gemini)
    ├── openai_files.json           # Datei-Hash -> Datei-ID (OpenAI Files API)
    ├── claude_files.json           # Datei-Hash -> Datei-ID (Files API von Anthropic)
    ├── requests_<unixzeit>.jsonl   # je Gemini-Batch die exakt gesendeten Anfragen
    ├── requests_openai_<unixzeit>.jsonl  # dasselbe für OpenAI-Batches
    └── requests_claude_<unixzeit>.jsonl  # dasselbe für Claude-Batches
```

**Lage von Hauptskript und Paket.** `README.md`, `requirements*.txt` und `pytest.ini` bleiben im Projektordner, weil Werkzeuge sie dort erwarten. Der Ordner `aibui/` muss **neben** `ai_batch_ui.py` liegen: Streamlit nimmt den Ordner des Hauptskripts in den Suchpfad für Importe auf. Liegen beide noch direkt im Projektordner (flaches Layout, älterer Stand), läuft die App ebenfalls: `conf/` und `data/` entstehen dann im Ordner mit dem Paket und damit an derselben Stelle. Für bestehende Installationen genügt es, das Hauptskript **und** den Ordner `aibui/` nach `src/` zu verschieben. `conf/` und `data/` bleiben unverändert, nur der Startbefehl ändert sich zu `streamlit run src/ai_batch_ui.py`.

**Tipp:** `data/batch_jobs.json` vor einem Update der App kopieren, denn Ergebnisse sind nach Ablauf der Aufbewahrung bei Google nicht neu abrufbar.

Empfohlene `.gitignore`:

```text
conf/credentials.json
conf/token.json
data/
.streamlit/secrets.toml
__pycache__/
.pytest_cache/
```

### `data/batch_jobs.json`: Liste von Einträgen, neueste zuerst

Batch-Eintrag (Felder `state`, `rows`, `error`, `api_model` kommen erst, wenn der Batch einen Endzustand hat. `provider` ist ein Pflichtfeld, siehe unten):

```json
{
  "name": "batches/9bo5q27hzqyh6unvm1z9slccnav15hnkybmy",
  "provider": "Gemini",
  "label": "gemini-20261019-1437",
  "model": "gemini-4-carbon",
  "pdf": "Buch 1.pdf, Buch 2.pdf",
  "pdfs": ["Buch 1.pdf", "Buch 2.pdf"],
  "prompts": {"prompt-1": "…", "prompt-2": "…"},
  "system": "",
  "think": "high",
  "max_out": 32768,
  "created": "2026-10-19T14:38:00",
  "state": "JOB_STATE_SUCCEEDED",
  "rows": [],
  "error": null,
  "api_model": "models/gemini-4-carbon"
}
```

`pdf` und `pdfs` heißen so aus der Zeit, als nur PDFs möglich waren. Seit Issue #16 enthalten sie die Namen **aller** angehängten Dateien (Dokumente, Text, Bilder, Audio, Video), in der Reihenfolge der Anfrage. Die Namen blieben, damit ältere Einträge ohne Umstellung lesbar sind.

OpenAI-Eintrag (nur Batch): dieselben Felder, `provider` ist hier `OpenAI`. `name` ist die Batch-ID, `state` der Status der Batch API in Kleinbuchstaben (`completed`, `failed`, `expired`, `cancelled`), `api_model` der von OpenAI gemeldete Modellname:

```json
{
  "name": "batch_<id>",
  "provider": "OpenAI",
  "label": "openai-20261110-0930",
  "model": "gpt-6-astra",
  "think": "high",
  "max_out": 32768,
  "state": "completed",
  "api_model": "gpt-6-astra-<datum>"
}
```

Die übrigen Felder (`pdf`, `pdfs`, `prompts`, `system`, `created`, `rows`, `error`) sind wie beim Batch-Eintrag oben.

Claude-Eintrag (nur Batch): dieselben Felder, `provider` ist hier `Claude`. `name` ist die Batch-ID (`msgbatch_…`), `state` der `processing_status` der Message Batches API (gesichert wird nur der Endzustand `ended`), `api_model` das in den Antworten gemeldete Modell (die Batch-Daten selbst nennen keines). Dazu kommt das Feld `cache`: `true`, wenn die Dateien eine Cache-Marke trugen. Einträge ohne das Feld gelten als „aus“. Ein Feld `error` für den ganzen Batch gibt es bei Claude nicht, jeder Fehler gehört zu einer Zeile in `rows`:

```json
{
  "name": "msgbatch_<id>",
  "provider": "Claude",
  "label": "claude-20261118-1050",
  "model": "claude-sonnet-5-5",
  "think": "high",
  "max_out": 32768,
  "cache": false,
  "state": "ended",
  "api_model": "claude-sonnet-5-5"
}
```

**`provider` ist ein Pflichtfeld** (Issue #8): `Gemini` (`PROVIDER_GEMINI`), `OpenAI` (`PROVIDER_OPENAI`) oder `Claude` (`PROVIDER_CLAUDE`), in Batch-, Hintergrund-, OpenAI- und Claude-Einträgen. Neue Einträge schreiben es immer. Einträge von vor Issue #8 haben das Feld nicht und stammen alle von Gemini (auch die älteren synchronen). Die App ergänzt es nicht nachträglich (seit Issue #34 gibt es keine Migrationen mehr), liest solche Einträge aber als Gemini-Einträge: `entry_provider()` nennt Gemini, wenn das Feld fehlt oder der Wert unbekannt ist.

Älterer synchroner Eintrag (den Modus gibt es nicht mehr, vorhandene Einträge bleiben les- und löschbar. Seine Zeilen wuchsen live):

```json
{
  "name": "sync-20261028-143015-3f9a",
  "provider": "Gemini",
  "mode": "sync",
  "state": "RUNNING",
  "label": "sync-20261028-1430",
  "model": "gemini-4-carbon",
  "pdf": "Buch.pdf",
  "pdfs": ["Buch.pdf"],
  "prompts": {"prompt-1": "…", "prompt-2": "…"},
  "system": "",
  "think": "high",
  "max_out": 65536,
  "group": 2,
  "rows": [],
  "created": "2026-10-28T14:30:15"
}
```

`state` schrieb zuletzt der Thread der alten App: `RUNNING`, `DONE`, `FAILED` (mit Feld `error`), `CANCELLED`. `INTERRUPTED` wird **nicht gespeichert**, sondern in `legacy_sync_panel()` abgeleitet: Steht `RUNNING` in der Datei (oder fehlt `state`), wurde der Lauf mit der App beendet, ein Thread lebt nicht mehr. Neue synchrone Einträge entstehen nicht. Der Eintrag wird weder abgefragt noch verändert, nur gelesen, übernommen, fortgesetzt oder gelöscht.

Hintergrund-Eintrag (die Felder `state`, `rows`, `error`, `api_model` kommen erst, wenn alle Interaktionen beendet sind, wie beim Batch):

```json
{
  "name": "bg-20261112-230500-3f9a",
  "provider": "Gemini",
  "mode": "background",
  "label": "background-gemini-20261112-2305",
  "model": "gemini-4-carbon",
  "pdf": "Buch.pdf",
  "pdfs": ["Buch.pdf"],
  "prompts": {"prompt-1": "…", "prompt-2": "…"},
  "system": "",
  "think": "high",
  "max_out": 262144,
  "interactions": {"prompt-1": "v1_…", "prompt-2": "v1_…"},
  "created": "2026-11-12T23:05:00",
  "state": "completed",
  "rows": [],
  "error": null,
  "api_model": "gemini-4-carbon"
}
```

`name` ist ein lokaler Name (`bg-<Datum>-<Uhrzeit>-<Zufall>`), `interactions` ordnet jedem Prompt-Schlüssel die ID seiner Interaktion bei Google zu. `state` ist `completed`, `cancelled` oder `failed` (klein geschrieben, wie bei OpenAI), solange eine Interaktion läuft, steht es nicht in der Datei. `api_model` ist das von der API gemeldete Modell. Google bewahrt die Interaktionen bei kostenpflichtigen Konten bis zu 55 Tage auf (in AI Studio auf 7, 14, 28 oder 55 Tage einstellbar), bei kostenlosen 1 Tag. Danach sind sie dort weg, das lokal gesicherte Endergebnis bleibt.

Eine Zeile in `rows` (alle Modi und Anbieter, erzeugt von `parse_line()`, bei OpenAI von `parse_openai_line()`, bei Claude von `parse_claude_line()` und im Hintergrund von `parse_interaction()`, dieselbe Form):

```json
{
  "key": "prompt-1",
  "prompt": "…",
  "text": "Antworttext ohne Denk-Teile",
  "model": "gemini-4-carbon",
  "finish": "STOP",
  "usage": {"promptTokenCount": 80259, "cachedContentTokenCount": 0, "thoughtsTokenCount": 2188, "candidatesTokenCount": 1133},
  "error": null,
  "in": 80259, "cached": 0, "think": 2188, "out": 1133,
  "secs": 42
}
```

`secs` gibt es nur in Zeilen älterer synchroner Einträge. `error` ist ein Text (bei Gemini auch das Fehlerobjekt der API, bei OpenAI immer als Text `code: Meldung`, bei Claude als Text `Art: Meldung (request_id: …)`). Bei OpenAI ist `usage` das `usage`-Objekt der Antwort, `out` die Ausgabe ohne Denk-Token, `finish` ist `STOP` (Status `completed`), `MAX_TOKENS` (`incomplete` wegen `max_output_tokens`) oder sonst der Grund bzw. Status. Bei Claude ist `usage` das `usage`-Objekt der Antwort, `in` die Summe aus `input_tokens`, `cache_read_input_tokens` und `cache_creation_input_tokens`, `cached` der gelesene Teil, `think` der Wert `output_tokens_details.thinking_tokens` (0, wenn er fehlt) und `out` die Ausgabe ohne Denk-Token. `finish` ist `STOP` (`end_turn`), `MAX_TOKENS` (`max_tokens`) oder sonst der `stop_reason` in Großbuchstaben, bei Anfragen ohne Antwort (Fehler, Abbruch, Ablauf) `unbekannt`. Abgebrochene und abgelaufene Anfragen tragen als `error` „Abgebrochen …“ bzw. „Abgelaufen …“. Im Hintergrund ist `usage` das `usage`-Objekt der Interaktion (`total_input_tokens` usw., über alle Schritte), der Text die Summe aller Schritte vom Typ `model_output`, `finish` ist `STOP` (Status `completed`), `MAX_TOKENS` (`incomplete`) oder der Status in Großbuchstaben. Übersprungene Prompts eines abgebrochenen Gesprächs (nur ältere synchrone Einträge) haben `error` = „Übersprungen: …“.

`label` ist der Name des Eintrags: eingetippt, aus dem Prompt erzeugt oder der Standardname `<Art>-<Datum>-<Uhrzeit>` (Art: `gemini` für einen Gemini-Batch, `background-gemini` im Hintergrund, `openai` oder `claude`; Gemini-Batches von vor Issue #7 heißen `batch-…` und Hintergrund-Einträge von vor Issue #32 `background-…`, beide behalten ihren Namen). `description` ist eine freie Beschreibung. Sie fehlt, bis im Tab „Jobs und Ergebnisse“ einmal „Speichern“ geklickt wurde (leer ist erlaubt). Beide ändert nur dieser Tab, der Anbieter behält den Namen vom Start (Claude bekommt nie einen).

Ältere Einträge können Felder nicht haben (`system`, `pdfs`, `think`, `group`, `description`, `state`, `rows` …). Neue Felder deshalb **immer optional** lesen (`.get()`). Ausnahme beim Schreiben ist `provider`: Es ist Pflicht (siehe oben). Gelesen wird es trotzdem mit `.get()` (`entry_provider()`), als Sicherheitsnetz.

### `data/pdf_files.json`

```json
{"<sha256 des Dateiinhalts>": "files/<id der Gemini Files API>"}
```

Der Schlüssel ist der SHA-256 des Inhalts, gleich welchen Typs die Datei hat. Der Dateiname stammt aus der Zeit, als nur PDFs hochgeladen wurden. Bei einer wiederverwendeten Datei steht in der Anfrage der MIME-Typ, den die Files API für sie führt.

### `data/openai_files.json`

```json
{"<sha256 des Dateiinhalts>": "file-<id der OpenAI Files API>"}
```

Getrennt von `pdf_files.json`, weil dieselbe Datei bei jedem Anbieter eine andere Kennung hat. Vor jeder Wiederverwendung fragt die App die Datei bei OpenAI ab und lädt neu hoch, wenn sie abgelaufen oder gelöscht ist (hier nach 3 Tagen).

### `data/claude_files.json`

```json
{"<sha256 des Dateiinhalts>": "file_<id der Files API von Anthropic>"}
```

Getrennt von den anderen Merklisten, weil dieselbe Datei bei jedem Anbieter eine andere Kennung hat. Vor jeder Wiederverwendung fragt die App die Metadaten der Datei bei Anthropic ab (`files.retrieve_metadata`) und lädt neu hoch, wenn die Datei fehlt oder nicht mehr mindestens `CLAUDE_FILE_MIN_LEFT` (26 Stunden) lebt. Die Metadaten einer abgelaufenen Datei liefert die API noch eine Weile. Darum zählt die Ablaufzeit (`expires_at`) und nicht, ob die Abfrage gelingt.

### `data/requests_<unixzeit>.jsonl`

Eine Zeile pro Prompt, genau das, was an die Batch-API ging (Anfrageformat `GenerateContentRequest`, Feldnamen in snake_case):

```json
{"key": "prompt-1", "request": {
  "contents": [{"role": "user", "parts": [
    {"file_data": {"mime_type": "application/pdf", "file_uri": "https://generativelanguage.googleapis.com/v1beta/files/…"}},  // je Datei, mit ihrem MIME-Typ
    {"text": "Prompt-Text"}]}],
  "generation_config": {"max_output_tokens": 32768, "thinking_config": {"thinking_level": "high"}},
  "system_instruction": {"parts": [{"text": "…"}]}}}
```

Nützlich zur Kontrolle: `grep -o '"thinking_level": "[a-z]*"' data/requests_*.jsonl | sort | uniq -c`.

### `data/requests_openai_<unixzeit>.jsonl`

Eine Zeile pro Prompt, im Format der OpenAI Batch API (Responses-Endpunkt):

```json
{"custom_id": "prompt-1", "method": "POST", "url": "/v1/responses", "body": {
  "model": "gpt-6-astra",
  "instructions": "…",
  "input": [{"role": "user", "content": [
    {"type": "input_file", "file_id": "file-…"},
    {"type": "input_text", "text": "Prompt-Text"}]}],
  "max_output_tokens": 32768,
  "reasoning": {"effort": "high"}}}
```

`instructions` (Systemanweisung) und `reasoning` (Denktiefe) fehlen, wenn nichts gesetzt ist („Standard“). Kontrolle: `grep -o '"effort": "[a-z]*"' data/requests_openai_*.jsonl | sort | uniq -c`.

### `data/requests_claude_<unixzeit>.jsonl`

Eine Zeile pro Prompt, genau die Anfrage, die an die Message Batches API ging (das SDK bekommt dieselben Einträge als Liste):

```json
{"custom_id": "prompt-1", "params": {
  "model": "claude-sonnet-5-5",
  "max_tokens": 32768,
  "system": "…",
  "output_config": {"effort": "high"},
  "messages": [{"role": "user", "content": [
    {"type": "document", "source": {"type": "file", "file_id": "file_…"}, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
    {"type": "text", "text": "Prompt-Text"}]}]}}
```

`system` (Systemanweisung) und `output_config` (Denktiefe) fehlen, wenn nichts gesetzt ist („Standard“). Bilder stehen als `image`-Block. `cache_control` trägt nur die letzte Datei, und nur, wenn das Kästchen „Prompt-Cache“ an war. Kontrolle: `grep -o '"effort": "[a-z]*"' data/requests_claude_*.jsonl | sort | uniq -c`.

### Gesprächsverlauf im Prompt (Fortsetzung eines Gesprächs)

„Gespräch fortsetzen“ speichert nichts Neues in `batch_jobs.json`. Der Verlauf ist reiner Text im Prompt des neuen Eintrags und sieht so aus (`conversation_text()`):

```text
Unten steht der bisherige Verlauf unseres Gesprächs: meine früheren Prompts und deine Antworten dazu. …

[Bisheriger Gesprächsverlauf]

[Runde 1: Mein Prompt]
<früherer Prompt>

[Runde 1: Deine Antwort dazu]
<Antwort des Modells>

[Runde 2: Mein Prompt]
…

[Ende des bisherigen Gesprächsverlaufs]

[Mein neuer Prompt]
<der neue Prompt, vom Benutzer geschrieben>
```

- Jede Marke steht allein in ihrer Zeile. `parse_conversation()` liest den Text wieder ein. Ist der Aufbau durcheinander (z. B. von Hand bearbeitet), gilt der Prompt als gewöhnlicher Prompt und wird beim nächsten Fortsetzen nicht abgeflacht. Fehlt nur die Marke `[Mein neuer Prompt]`, zählt der Rest nach dem Ende des Verlaufs als neuer Prompt.
- Frühere Prompts und Antworten gehen durch `talk_safe()`: Eine Zeile nur mit `---` würde im Formular die Prompts trennen und wird zu `***` (in Markdown dieselbe Trennlinie). Zeilen, die wie eine Marke aussehen, bekommen einen Rückstrich. Das ist wiederholbar, ohne dass sich etwas ändert.
- Beim Fortsetzen holt `history_turns()` die Runden aus dem Eintrag. Beginnt der erste Prompt selbst mit einem Verlauf, wird dieser davor eingereiht, statt zu verschachteln.

## 8. Architektur

Bewusst ohne Klassen und ohne Datenbank: Die Logik steht als Funktionen im Paket `aibui`, die Oberfläche im Hauptskript `src/ai_batch_ui.py`. Streamlit führt das **Hauptskript** bei **jeder** Interaktion von oben nach unten neu aus, die Module von `aibui` dagegen nur beim ersten Import. Alles, was länger leben muss, steckt deshalb in Dateien, in `st.session_state` oder in `runtime()`.

### Landkarte (Dateien von oben nach unten)

Ein Modul von `aibui` importiert nur Module, die in dieser Tabelle über ihm stehen. So gibt es keine Importzyklen (ein Test prüft es, die Liste steht auch in `src/aibui/__init__.py`).

| Datei | Inhalt |
|---|---|
| `src/aibui/config.py` | Konstanten (siehe 6.2), `_base_dir()` (Wurzel), `prepare_folders()` (legt `conf/` und `data/` an) |
| `src/aibui/files.py` | Dateien als Eingabe (Issue #16), ohne Streamlit und SDK: `FILE_TYPES` (Endung → Art und MIME-Typ), `TEXT_EXTENSIONS`, `PROVIDER_KINDS` (welche Arten ein Anbieter annimmt), `PROVIDER_EXCLUDED` (Endungen, die er trotz passender Art ablehnt), `file_info()` (Art und MIME-Typ einer Datei, `ValueError` bei unbekanntem Typ), `excluded_problem()` (Meldung zu einer abgelehnten Endung), `check_files()` (Meldungen zu Dateien, die der gewählte Anbieter nicht annimmt), `types_overview()` (Hilfetext am Datei-Feld), `mime_kind()` (Art zu einem MIME-Typ, zugleich der Inhaltstyp der Interactions API) und `file_mime()` (MIME-Typ einer hochgeladenen Gemini-Datei) |
| `src/aibui/history.py` | `runtime()` (prozessweit: `lock`, die Sperre für den Verlauf), `load_jobs()`, `mutate_jobs(lock, change)` |
| `src/aibui/rows.py` | die gemeinsame Zeilenform: `pick()`, `parse_line()`, `sort_rows()` (Zeilen nach der Nummer im Schlüssel ordnen), `parse_results()` (mit wählbarem Zeilenleser), für den Hintergrund-Modus `as_dict()` und `parse_interaction()` |
| `src/aibui/drive.py` | `drive_service()` (OAuth, Neuanmeldung bei `RefreshError`), `drive_id()` (ID aus Link), `drive_fetch()` (PDF laden/exportieren) |
| `src/aibui/gemini.py` | `upload_file()` (Files API + `data/pdf_files.json`), `batch_part()` (Dateiteil einer Anfrage), `start_batch()` (JSONL bauen, hochladen, `batches.create`) |
| `src/aibui/background.py` | Hintergrund-Modus (Interactions API, Long Decode): `input_part()` (Eingabeteil je Datei), `interaction_request()` (Anfrage), `create_interaction()` (mit Wiederholung), `start_background()` (alle Prompts starten, Eintrag speichern), `fetch_background()` (Stand, Zeilen, Endzustand), `cancel_background()` |
| `src/aibui/openai_batch.py` | `openai_client()` (lädt das Paket erst hier), `upload_file_openai()` (Files API + `data/openai_files.json`), `openai_file_part()` (Dateiteil einer Anfrage), `openai_request()` (Anfragerumpf), `start_openai_batch()` (JSONL bauen, hochladen, `batches.create`), `openai_error_text()`, `parse_openai_line()`, `fetch_openai_batch()` (Status, Ausgabe- und Fehlerdatei) |
| `src/aibui/claude_batch.py` | `claude_client()` (lädt das Paket erst hier), `claude_filename()` (Dateiname für die Files API), `claude_mime()` (MIME-Typ für den Upload, `ValueError` bei Typen, die Claude nicht annimmt), `file_alive()` (lebt die Datei noch lange genug), `upload_file_claude()` (Files API + `data/claude_files.json`), `claude_file_part()` (Dateiblock einer Anfrage), `claude_request()` (Anfragerumpf, auf Wunsch mit Cache-Marke), `start_claude_batch()` (Anfragen bauen, JSONL zur Kontrolle ablegen, Batch anlegen), `claude_error_text()`, `claude_refusal_text()`, `parse_claude_line()`, `fetch_claude_batch()` (Status, bei `ended` die Ergebnisse) |
| `src/aibui/providers.py` | `make_client()`, `entry_provider()`, `entry_mode()` (`background` oder `batch`, `sync` nur für ältere Einträge), `refresh()` (Status + Ergebnisse laden, Endergebnis sichern, bei OpenAI-Einträgen über `fetch_openai_batch()`, bei Claude-Einträgen über `fetch_claude_batch()`, bei Hintergrund-Einträgen über `fetch_background()`), `batch_info()`, `cancel_batch()` (je Anbieter und Modus) |
| `src/aibui/pricing.py` | Preise (Issue #12), ohne Streamlit: `PRICES` (Standardpreise je Anbieter und Modell), `MAX_MODELS`, `BATCH_FACTOR`, `PRICES_AS_OF`, `CLAUDE_CACHE_WRITE`, `read_price_file()` (liest die Preisdatei `conf/prices.toml`, Issue #39: Preise und Fehlertexte), `current_prices()` (die geltende Tabelle: `PRICES`, überlagert von der Datei), `find_model()` (ordnet den Namen aus dem Feld „Modell“ der Tabelle zu), `price_tier()` (Preise der Stufe zur Länge eines Prompts), `run_day()` (Tag, dessen Preise für einen Lauf gelten), `model_choices()` (die Modelle eines Anbieters für das Feld „Modell“, das teuerste zuerst, Issue #11), `default_model()` (der erste Eintrag davon), `model_costs()` (Kosten an einem Tag, samt den schon feststehenden späteren Preisen), `price_text()`, `costs_markdown()` (Text der Infobox), `costs_caption()` und `costs_help()` (Zeile darunter samt Tooltip), `today()` (das Datum, Tests ersetzen es) |
| `src/aibui/costs.py` | Kosten eines Laufs (Issue #39), ohne Streamlit: `run_costs()` (geschätzte Kosten aus den Token der Zeilen und den Preisen, bei Gemini mit dem Vergleich Batch gegen Hintergrund-Modus), `standard_cost()` (eine Zeile zum Standardpreis), `KINDS` (Abrechnungsart und Faktor je Betriebsart), `cost_text()`, `row_cost_text()`, `run_cost_text()`, `no_price_text()` und `costs_note()` (die Texte der Anzeige) |
| `src/aibui/talk.py` | Gesprächsverlauf als Text: `entry_group()` (Prompts pro Gespräch, über 1 nur bei älteren synchronen Einträgen), `talk_safe()`, `conversation_text()`, `parse_conversation()`, `history_turns()`, `short_prompt()` |
| `src/aibui/naming.py` | Namen der Einträge (ohne Streamlit): `default_label()` (Standardname), `naming_source()` (Text für das Modell), `clean_name()`, `generate_name()` (ein Aufruf von `generate_content`), `choose_label()` (welcher Name beim Start gilt, ein Fehler stoppt den Start nie), Suche mit `entry_text()`, `matches()` und `search_jobs()`, `file_stem()` (Dateiname des Markdown-Downloads) |
| `src/aibui/forms.py` | Verlauf und Formular: `entry_label()`, `fill_form()` (Hilfe), `reuse_inputs()` und `continue_conversation()` (Callbacks), `delete_entry()` (Callback), `save_details()` und `generate_title()` (Callbacks für Name und Beschreibung), `update_entry()` und `keep_visible()` (Hilfen) |
| `src/aibui/views.py` | Anzeige: `model_field()` (das Feld „Modell“ der Seitenleiste, Issue #11), `show_costs()` (die Kosten-Infobox der Seitenleiste, bei Fehlern in der Preisdatei mit einer Warnung), `show_text()`, `show_prompt()`, `request_details()`, `talk_tools()`, `show_rows()` (Ergebnisse mit Token und geschätzten Kosten), `legacy_sync_panel()`, `job_panel()` (läuft als Fragment) |
| `src/ai_batch_ui.py` | Hauptskript, nur Oberfläche: Seitenleiste (Anbieter, Keys, Modell mit Kosten-Infobox, Namen der Einträge), `client_for()` (Client je Anbieter, `None` ohne Key), `gemini_client()` (Gemini-Client für die Namen, auch bei einem OpenAI- oder Claude-Lauf), Tabs, `with tab_new:` (Formular + Start-Handler), `with tab_jobs:` (Suche, Auswahl, Buttons, Fragment mit dem Client des Eintragsanbieters) |

Die Grenze zwischen Logik und Oberfläche ist die Paketgrenze: Das Hauptskript importiert aus `aibui`, `aibui` importiert es nie (ein Test prüft es). Gezeichnet wird nur in `views.py`. Die übrigen Module sind ohne Oberfläche testbar (siehe 9.3): `forms.py` und `providers.py` nutzen von Streamlit nur `st.session_state`, `history.py` nur `@st.cache_resource`, `naming.py`, `pricing.py` und `costs.py` nichts. `views.py` läuft in den Tests über `AppTest`. Die Fixture `app` in `tests/conftest.py` lädt alle Module von `aibui` als ein Objekt.

### Datenfluss Batch

```text
Formular ──► Dateien sammeln (Upload, Drive) ──► Duplikate per SHA-256 entfernen
         ──► upload_file() je Datei: Files API (MIME-Typ nach Endung, wiederverwendet über data/pdf_files.json)
         ──► start_batch(): JSONL (key + request je Prompt) in data/requests_<ts>.jsonl,
             JSONL per Files API hochladen (mime_type "jsonl"), client.batches.create(model, src)
         ──► Verlaufseintrag (provider Gemini, ohne state) in data/batch_jobs.json
Jobs-Tab ──► Fragment alle 10 s: refresh() → client.batches.get(name)
         ──► bei JOB_STATE_SUCCEEDED: client.files.download(dest.file_name) → parse_results() → rows
         ──► Endzustand (state, rows, error, api_model) in den Eintrag schreiben → ab da kein Abruf mehr nötig
```

### Datenfluss Batch (OpenAI)

```text
Formular ──► Dateien sammeln (Upload, Drive) ──► Duplikate per SHA-256 entfernen
         ──► upload_file_openai() je Datei: Files API (Zweck user_data, bei Bildern vision, Ablauf nach 3 Tagen,
             wiederverwendet über data/openai_files.json)
         ──► start_openai_batch(): JSONL (custom_id + Anfrage je Prompt) in data/requests_openai_<ts>.jsonl,
             JSONL per Files API hochladen (Zweck batch), client.batches.create(input_file_id, endpoint, completion_window)
         ──► Verlaufseintrag (provider OpenAI, ohne state) in data/batch_jobs.json
Jobs-Tab ──► Fragment alle 10 s: refresh() → fetch_openai_batch() → client.batches.retrieve(id)
         ──► bei completed, expired, cancelled oder failed: output_file_id und error_file_id per files.content laden
             → parse_results(…, parse_openai_line) → rows
         ──► Endzustand (state, rows, error, api_model) in den Eintrag schreiben → ab da kein Abruf mehr nötig
```

### Datenfluss Batch (Claude)

```text
Formular ──► Dateien sammeln (Upload, Drive) ──► Duplikate per SHA-256 entfernen
         ──► upload_file_claude() je Datei: Files API (Name bereinigt, MIME-Typ PDF, text/plain oder Bild, Ablauf nach
             3 Tagen, wiederverwendet über data/claude_files.json, solange die Datei noch 26 Stunden lebt)
         ──► start_claude_batch(): Anfragen (custom_id + params je Prompt, auf Wunsch mit Cache-Marke auf der letzten
             Datei) als JSONL in data/requests_claude_<ts>.jsonl, client.messages.batches.create(requests)
         ──► Verlaufseintrag (provider Claude, ohne state) in data/batch_jobs.json
Jobs-Tab ──► Fragment alle 10 s: refresh() → fetch_claude_batch() → client.messages.batches.retrieve(id)
         ──► bei processing_status ended: client.messages.batches.results(id) → parse_claude_line() je Ergebnis
             → sort_rows() → rows
         ──► Endzustand (state, rows, api_model) in den Eintrag schreiben → ab da kein Abruf mehr nötig
Abbruch  ──► cancel_batch() → client.messages.batches.cancel(id) (Status canceling, danach ended)
```

### Datenfluss Hintergrund

```text
Formular ──► Dateien sammeln, upload_file() je Datei (wie beim Batch)
         ──► start_background(): je Prompt client.interactions.create(model, input=[Dateien als document, image, audio oder video + uri, Prompt],
             generation_config={max_output_tokens, thinking_level}, background=True, store=True)
             → Interaktions-ID. Scheitert einer, werden die schon gestarteten abgebrochen.
         ──► Verlaufseintrag (provider Gemini, mode background, interactions {Schlüssel: ID}, ohne state) in data/batch_jobs.json
Jobs-Tab ──► Fragment alle 10 s: refresh() → fetch_background() → client.interactions.get(id) je Prompt
             (Zeilen aus der letzten Abfrage bleiben stehen, beendete Interaktionen werden nicht erneut geladen)
         ──► beendet (alles außer in_progress/queued): parse_interaction() → Zeile. Text = alle model_output-Schritte
         ──► alle beendet: Endzustand (state, rows, error, api_model) in den Eintrag schreiben, danach kein Abruf mehr
Abbruch  ──► cancel_batch() → cancel_background() → client.interactions.cancel(id) je Prompt
```

### Datenfluss Namen

```text
Start    ──► Feld „Name“ leer, Namensvergabe an und Gemini API-Key da?
             ja:   choose_label() → generate_name(): client.models.generate_content(model, contents=Auszug der Prompts,
                   config={system_instruction, thinking_level, max_output_tokens, Zeitlimit}) → clean_name()
                   Scheitert der Aufruf oder kommt kein Text: Standardname, der Start läuft weiter, Warnung mit dem Grund
             nein: Standardname <Art>-<Datum>-<Uhrzeit> mit Art gemini, background-gemini, openai oder claude (ein eingetippter Name gilt immer)
         ──► Der Name geht als label in den Eintrag und als Anzeigename an den Anbieter (Gemini: display_name,
             OpenAI: metadata.description, Claude: nichts, die Message Batches API kennt keinen Namen). Danach ist die Suche im Jobs-Tab leer und der Eintrag ausgewählt.
Jobs-Tab ──► Popover „Name und Beschreibung“: save_details() bzw. generate_title() ändern label und description
             nur in data/batch_jobs.json (unter der Sperre, auf dem frischen Stand der Datei), setzen sel auf den
             neuen Namen und leeren jobs_search, falls der Eintrag nicht mehr zur Suche passt
```

### Streamlit-Besonderheiten, die man kennen muss

- **Tab-Erkennung**: `st.tabs(TABS, key="view", on_change="rerun")`. `tab_jobs.open` sagt, ob der Jobs-Tab offen ist. Der Inhalt versteckter Tabs läuft trotzdem, gesteuert wird über `.open`. Ein Tab-Wechsel löst einen **vollständigen Rerun** aus. Das unterbricht jedes Skript, das gerade lange läuft (Uploads im Start-Handler). Lange Arbeit gehört deshalb zum Anbieter: Der Start-Handler legt sie nur an, danach fragt das Fragment den Stand ab (siehe `start_background`).
- **Polling per Fragment**: `st.fragment(run_every=POLL_SECONDS if polling else None)(job_panel)(...)`. Die Entscheidung `polling` wird bei jedem vollen Lauf neu getroffen (Tab offen und Eintrag läuft). Um einen laufenden Timer zu beenden, ruft das Fragment `st.rerun()` auf (voller Rerun). Die Argumente eines Timer-Reruns sind **veraltet** (Stand des letzten vollen Laufs). Ein Fragment muss veränderliche Daten deshalb selbst neu laden (`job_panel` nutzt `batch_info()` und die Session).
- **Button im Fragment, der das Formular füllt**: Ein Klick im Fragment (die Ergebnisse laufen in `job_panel`) löst nur einen Fragment-Lauf aus. „Gespräch fortsetzen“ füllt das Formular deshalb in einem **Callback** (`continue_conversation`: Widget-Werte lassen sich nur setzen, bevor das Widget im Lauf erzeugt wurde) und ruft danach `st.rerun()` auf, damit ein voller Lauf das Formular zeigt und den Tab wechselt. Im `AppTest` ist schon der erste Lauf voll. Dort verbraucht er den einmaligen Hinweis `reused_note`, im Browser erscheint er nach dem Rerun.
- **Felder, die einen Lauf lang fehlen**: Streamlit vergisst den Wert eines Widgets, das in einem Lauf nicht gezeichnet wird (Felder des anderen Anbieters, alles hinter `st.stop()` bei fehlendem API-Key). Das Backend behält dabei teils noch Werte, der Browser baut das Feld aber mit dem Standardwert neu auf: Das Modellfeld war leer, „Max. Ausgabe-Token“ stand auf 256, die Denktiefe auf „Standard“, Prompts und Systemanweisung waren weg. Darum weist das Hauptskript jeden Wert aus `FORM_KEYS` vor dem Zeichnen neu zu (`st.session_state[key] = st.session_state[key]`). Das hält ihn am Leben und schickt ihn mit `set_value` an den Browser. `AppTest` sieht den Fehler nicht, weil es nur den Wert im Backend zeigt. Die Tests in `test_openai.py` und `test_claude.py` prüfen deshalb, was die App dem Browser schickt (`proto.set_value`, Hilfsfunktion `sent_to_browser`). Namensfelder (`label_*`), die Suche und die Auswahl im Jobs-Tab (`jobs_search`, `sel`), der Anbieterschalter und der Tab-Zustand (`view`) brauchen das nicht, ein Test hält die Ausnahmen fest. Die Einstellungen der Namensvergabe (`auto_name`, `name_model`, `name_think`) stehen dagegen in `FORM_KEYS`.
- **Sperre für den Verlauf**: `rt = runtime()` ist prozessweit geteilt und enthält nur noch die Sperre `rt.lock` (jede Browser-Sitzung läuft in einem eigenen Thread, die App startet selbst keine Threads mehr). Schreibzugriffe auf den Verlauf nur über `mutate_jobs(rt.lock, …)` (liest unter Sperre, schreibt atomar über `batch_jobs.tmp` + `os.replace`).
- **Module und Hauptskript**: Streamlit führt das Hauptskript bei jedem Lauf neu aus, die Module von `aibui` dagegen nur beim ersten Import (danach kommen sie aus dem Importspeicher von Python). Darum steht auf Modulebene kein Streamlit-Aufruf außer Dekoratoren wie `@st.cache_resource` (ein Test prüft es), und `st.set_page_config` bleibt im Hauptskript, weil es der erste Streamlit-Aufruf sein muss. Konstanten wie `DATA_DIR` werden einmal je Prozess berechnet. Ändert man beim Entwickeln eine Datei von `aibui`, wirft Streamlit alle beobachteten Module aus dem Importspeicher, und der nächste Lauf importiert sie neu (nur mit Datei-Beobachter, siehe 6.3).
- **Importpfad**: Beim Start mit `streamlit run` nimmt Streamlit den Ordner des Hauptskripts in `sys.path` auf, deshalb findet `import aibui` den Ordner daneben. `AppTest` tut das erst in neueren Versionen (in 1.56.0 noch nicht), darum trägt `pytest.ini` `src` mit `pythonpath = src` ein. Ein Test, der eine Kopie des Hauptskripts an einen anderen Ort stellt, ergänzt den Pfad selbst.

### Session-State- und Widget-Schlüssel

| Schlüssel | Zweck |
|---|---|
| `view` | aktiver Tab. `reuse_inputs` und `continue_conversation` setzen ihn auf „Neue Anfrage“ |
| `provider` | Anbieter-Radio der Seitenleiste (`PROVIDERS`). `fill_form()` setzt es, wenn ein Eintrag übernommen wird |
| `model_gemini`, `model_openai`, `model_claude` | Combobox „Modell“ je Anbieter (Issue #11, `model_field()`). `fill_form()` setzt den Wert beim Übernehmen, auch einen Namen, der nicht in der Liste steht |
| `mode` | Modus-Radio (`MODE_BATCH` / `MODE_BG`). Mit OpenAI und Claude wird es nicht angezeigt |
| `system`, `raw` | Systemanweisung, Prompts-Textfeld |
| `think`, `effort`, `effort_claude` | Denktiefe bei Gemini, OpenAI bzw. Claude (Voreinstellung per `setdefault`) |
| `max_batch`, `max_bg`, `max_openai`, `max_claude` | Ausgabe-Token je Modus bei Gemini bzw. bei OpenAI und Claude (Voreinstellung per `setdefault`) |
| `cache_claude` | Kästchen „Dateien im Prompt-Cache halten“ (nur bei Claude, Voreinstellung aus per `setdefault`, in `FORM_KEYS`) |
| `label_gemini`, `label_background-gemini`, `label_openai`, `label_claude` | Namensfeld für Gemini-Batch, Gemini im Hintergrund, OpenAI bzw. Claude (leer = Name aus dem Prompt oder Standardname) |
| `auto_name`, `name_model`, `name_think` | Einstellungen „Namen der Einträge“ in der Seitenleiste (Voreinstellung per `setdefault`, alle drei in `FORM_KEYS`) |
| `jobs_search` | Suchfeld im Jobs-Tab. Der Start-Handler leert es, damit der neue Eintrag sichtbar ist, `keep_visible()` nach dem Umbenennen, wenn der Eintrag nicht mehr passt |
| `sel` | Auswahl im Jobs-Tab (Wert = `entry_label(eintrag)`). Der Start-Handler setzt ihn auf den neuen Eintrag |
| `drive_pdfs` | `{Anzeigename: Drive-ID}` der geladenen Drive-Liste |
| `reused_note` | einmaliger Hinweis nach „Eingaben übernehmen“ und „Gespräch fortsetzen“ (wird beim Anzeigen entfernt) |
| `name_note` | einmaliger Hinweis über der Liste im Jobs-Tab, wenn „Name aus dem Prompt erzeugen“ scheiterte (wird beim Anzeigen entfernt) |
| `title:<name>`, `descr:<name>` | Felder „Name“ und „Beschreibung“ im Popover „Name und Beschreibung“ je Eintrag (Voreinstellung per `setdefault` aus dem Eintrag, die Callbacks setzen sie nach dem Speichern) |
| `res:<name>` | Ergebnisstand eines Batches oder Hintergrund-Eintrags in der Sitzung (`state`, `rows`, `error`, `model`) |
| `err:<name>`, `errn:<name>` | letzte Abruffehlermeldung, Zähler aufeinanderfolgender Fehler |
| `detail:<name>` | Schalter „Gesendete Anfrage im Detail“ je Eintrag |
| `prompt:<name>`, `hist:<name>` | Schalter „Prompt im Wortlaut“ und „Verlaufstext zeigen“ je Ergebnis (nach dem Eintragsnamen folgt `:` und der Prompt-Schlüssel, z. B. `prompt-1`) |
| Button-Schlüssel | `chk:`, `cx:` (Batch bzw. Hintergrund-Läufe prüfen/abbrechen), `dl:` (Download), `reuse:`, `del:`, `save:`, `gen:` (Name speichern bzw. aus dem Prompt erzeugen), `talk:` (Gespräch fortsetzen) jeweils plus Eintragsname (bei `talk:` danach `:` und der Prompt-Schlüssel) |

## 9. Weiterentwickeln

### 9.1 Spielregeln

1. **Erst diese Datei lesen**, dann das Hauptskript `src/ai_batch_ui.py` und das Modul in `src/aibui/`, das zum Thema passt (Landkarte in Abschnitt 8). Kleine, gezielte Änderungen statt Umbauten. Logik gehört in ein Modul von `aibui`, das Hauptskript bleibt die Oberfläche. Ein neues Thema bekommt ein neues Modul, eingetragen in der Landkarte und in der Liste in `src/aibui/__init__.py`. Ein Modul importiert nur Module, die in dieser Liste über ihm stehen. Wächst eine Datei deutlich über etwa 1.000 Zeilen, wird sie nach Thema geteilt (Importe werden gecacht, nur das Hauptskript läuft bei jedem Rerun neu).
2. **Prefix stabil halten** (Abschnitt 5). Alles, was vor oder zwischen den Dateien steht, beeinflusst die Cache-Trefferquote.
3. **Verlauf nur über `mutate_jobs`** schreiben, nie `data/batch_jobs.json` direkt. Lesen mit `load_jobs()`. Neue Eintragsfelder optional (`.get()`), weil alte Einträge sie nicht haben. Ausnahme ist `provider`: Jeder neue Eintrag bekommt es (Abschnitt 7).
4. **Zeilenform nur in `parse_line()`, `parse_openai_line()`, `parse_claude_line()` und `parse_interaction()` ändern** und dort neue Felder ergänzen (alle vier liefern dieselbe Form). Anzeige in `show_rows()`. Alle Modi und Anbieter nutzen dieselbe Zeilenform, und gespeicherte Zeilen alter Läufe haben neue Felder nicht (`.get()`).
5. **Lange Arbeit nicht im Hauptskript abwarten.** Alles im Hauptskript kann durch einen Tab-Wechsel unterbrochen werden. Der Start-Handler legt die Arbeit beim Anbieter nur an (Batch oder Hintergrund-Interaktion) und speichert einen Verlaufseintrag, das Polling-Fragment fragt den Stand ab (Muster: `start_background` → `fetch_background` → `job_panel`).
6. **Widgets, die per Code gesetzt werden sollen, brauchen einen `key`.** Voreinstellung über `st.session_state.setdefault(key, wert)` setzen und dem Widget kein `value=`/`index=` mitgeben (sonst Streamlit-Warnung). Widget-Zustand nur **vor** dem Erzeugen des Widgets im selben Lauf ändern (in Callbacks oder weiter oben im Skript), danach gibt es eine Ausnahme. Ein neues Formularfeld mit Schlüssel gehört außerdem in `FORM_KEYS`, sonst vergisst Streamlit seinen Wert, sobald es einen Lauf lang fehlt. Ein Test erinnert daran.
7. **Keine verschachtelten Expander** (Streamlit verbietet es). Popover in Spalten ist erlaubt.
8. **Fragmente**: Argumente sind in Timer-Läufen veraltet, Timer mit `st.rerun()` beenden, Zustände für Abbruchbedingungen aus Datei oder Session lesen.
9. **Fehler verständlich melden** (deutsch, mit Hinweis, was zu tun ist). Geheimnisse (API-Key, Tokens) nie loggen oder speichern.
10. **Modellverhalten nicht raten.** Bei neuen Parametern die aktuelle Doku des Anbieters prüfen und im Zweifel die rohen `usage`-Daten und Fehlermeldungen der API ansehen. Carbon und Argon haben Eigenheiten (Abschnitt 5).
11. **Stil**: deutsche Oberflächentexte und Kommentare, 4 Leerzeichen, Zeilen bis etwa 120 Zeichen, flache Funktionen, Docstrings kurz.

### 9.2 Rezepte

**Neuen Generierungsparameter hinzufügen (z. B. Temperatur)**

1. Widget mit `key` neben „Denktiefe“ ergänzen (Voreinstellung per `setdefault`, Schlüssel in `FORM_KEYS` aufnehmen).
2. In `start_batch()` in das Dict `gen` aufnehmen, im Hintergrund-Modus in `interaction_request()` (`generation_config`), bei OpenAI in `openai_request()`, bei Claude in `claude_request()`.
3. Wert im Eintrag speichern (`start_background()` bzw. das Batch-Eintrags-Dict im Start-Handler).
4. `reuse_inputs()` und die Beschriftung im Jobs-Tab erweitern.
5. Testen (9.3). In der Carbon-Doku prüfen, ob der Parameter noch wirkt.

**Neuen Modus hinzufügen (z. B. ein weiterer Rabatt-Tarif)**

1. Konstante `MODE_…` und Eintrag im Modus-Radio.
2. Startfunktion nach dem Muster `start_background()`. Eintrag mit `"mode": "<neu>"`.
3. `job_panel()` verteilt nach `entry_mode()` (in `providers.py`, nennt die Betriebsart). Ein Modus, der wie ein Batch abgefragt wird, braucht kein neues Panel: Muster dafür ist der Hintergrund-Modus (Zweige in `refresh()` und `cancel_batch()`, eigene Beschriftung in `job_panel()`). Wer doch ein eigenes Panel braucht, ergänzt den Zweig in `job_panel()` und die Entscheidung `running` im `with tab_jobs:`-Block.
4. `reuse_inputs()` für den neuen Modus erweitern.

**Weiteren Anbieter ergänzen** (Muster: OpenAI, bei einem Anbieter mit SDK-Aufrufen statt JSONL-Datei: Claude)

1. Konstante `PROVIDER_…` und Eintrag in `PROVIDERS` (`config.py`), der Client in `make_client()` (`providers.py`).
2. Ein neues Modul nach dem Muster von `openai_batch.py` oder `claude_batch.py` (Upload, Start, Zeilen lesen, Status holen), eingetragen in der Landkarte und in `src/aibui/__init__.py`. Der Zeilenleser muss die Form von `parse_line()` liefern, dann laufen Anzeige, Download und „Gespräch fortsetzen“ unverändert.
3. Eintrag mit dem Pflichtfeld `provider` (Konstante des Anbieters) speichern. `entry_provider()`, `refresh()`, `cancel_batch()` (alle in `providers.py`), `fill_form()` (`forms.py`) und die Formularzweige im Hauptskript erweitern, die Endzustände des Anbieters in `DONE` aufnehmen.
4. Einen Fake mit echten SDK-Objekten nach dem Muster von `FakeOpenAI` oder `FakeClaude` bauen und Tests schreiben (9.3). Wo das SDK den HTTP-Client austauschen lässt, prüft ein Test den echten SDK-Code mit abgefangenem HTTP (Muster: `real_claude_client()`). Dateiarten und Endungen, die der Anbieter nicht annimmt, gehören in `PROVIDER_KINDS` und `PROVIDER_EXCLUDED` (`files.py`).

**Eigene Preise eintragen, ohne den Code zu ändern** (Issue #39): In `conf/prices.toml` je Preis einen Eintrag `[[price]]` anlegen (Format und Regeln: Abschnitt 6.6) und die App neu zeichnen lassen, ein Klick genügt. Die Warnung in der Seitenleiste nennt Fehler in der Datei. Die eingebaute Tabelle ändert man mit dem nächsten Rezept.

**Preis eines Modells ändern, ein Modell ergänzen oder entfernen** (Issue #12 und #11: Die Tabelle ist auch die Liste im Feld „Modell“)

1. In `src/aibui/pricing.py` in `PRICES` unter dem Anbieter eintragen: der Modellname in Kleinbuchstaben ohne Datumsstand, dazu eine Liste von Preisständen `(gültig ab, Stufen)`. Der erste Preisstand hat `None` als Datum. Ein feststehender Preiswechsel ist ein weiterer Eintrag mit dem ersten Tag des neuen Preises. Eine Stufe ist `(Prompt bis … Token, Eingabe, Ausgabe, Cache)` in USD je 1 Mio. Token im **Standard**tarif, wie die Preisseite des Anbieters sie nennt, als `Decimal`. Die letzte Stufe hat `None` als Grenze. Der Batch wird nicht eingetragen, er ergibt sich mit `BATCH_FACTOR`. Jedes Modell in der Tabelle steht auch in der Combobox „Modell“, das teuerste zuerst und bei gleichem Preis in der Reihenfolge der Tabelle (das neuere oder stärkere zuerst). Je Anbieter sind es höchstens `MAX_MODELS`, die aktuellen: Kommt ein Modell dazu und wären es mehr, fliegt das älteste heraus, das das neue ersetzt. Es bleibt per Eintippen wählbar, nur kennt die Kosten-Infobox es dann nicht mehr. Das teuerste Modell ist die Voreinstellung.
2. `PRICES_AS_OF` auf den Tag setzen, an dem die Tabelle mit den Preisseiten abgeglichen wurde, und denselben Tag in der README nennen (Kopf und Abschnitt 13, jeweils mit `PRICES_AS_OF`). Sonst schlägt `test_the_date_of_the_prices_is_named_with_its_constant_in_the_readme` an.
3. `pytest tests/test_pricing.py tests/test_models.py`. Ein Test prüft den Aufbau der Tabelle (Reihenfolge der Preisstände und Stufen, Cache < Eingabe < Ausgabe, höchstens `MAX_MODELS` Modelle je Anbieter), die übrigen nennen Preise einzelner Modelle und die erwartete Reihenfolge der Liste und gehören dann angepasst.
4. Nennt ein Anbieter für ein Modell einen anderen Batch-Rabatt als die Hälfte, reicht `BATCH_FACTOR` nicht: dann `_rows()` in `pricing.py` je Modell erweitern. Auch die Kostenrechnung (`KINDS` in `costs.py`) kennt nur einen Faktor je Betriebsart.
5. Ändert sich die Lebensdauer der Cache-Marke bei Claude (`CLAUDE_CACHE_TTL`), braucht sie einen Faktor in `CLAUDE_CACHE_WRITE`, sonst schlägt `test_the_constants_fit_together` an.

**Aufbau des Verlaufstexts ändern** (Einleitung, Marken, Beschriftung): `TALK_*` anpassen. `TALK_MARK` muss zu den Marken passen, `test_every_mark_constant_is_recognized_by_the_mark_pattern` meldet Abweichungen. Bereits gesendete Prompts bleiben nur dann „abflachbar“, wenn ihre Marken noch erkannt werden. Sonst gelten sie als gewöhnliche Prompts.

**Neues Ergebnisfeld anzeigen**: Feld in `parse_line()` berechnen, in `show_rows()` ausgeben (mit `.get()`), bei Bedarf in den Markdown-Download aufnehmen.

**Einen weiteren Dateityp zulassen**: In `src/aibui/files.py` die Endung samt Art und MIME-Typ in `FILE_TYPES` eintragen (Textdateien nur in `TEXT_EXTENSIONS`). Mehr ist nicht nötig: Upload, Anfrageteile, Prüfung und Hilfetext lesen die Tabelle. `tests/test_files.py` prüft, dass jede Zeile zu ihrer Art passt und dass die MIME-Typen in den Aufzählungen des SDK der Interactions API stehen. Eine ganz neue Art (neben Dokument, Bild, Audio, Video) braucht außerdem einen Eintrag in `KIND_LABELS` und `PROVIDER_KINDS` und einen Teil in `batch_part()`, `input_part()`, `openai_file_part()` und `claude_file_part()`. Bei Claude muss außerdem `claude_mime()` den MIME-Typ für den Upload kennen.

**Explizites Caching für andere Modelle**: Für Carbon und Argon nicht möglich. Für Modelle, die es unterstützen, wäre der Weg: Cache mit den Dateien anlegen (`client.caches.create(...)` mit Laufzeit), im Request nur noch `cached_content` referenzieren und die Dateien weglassen, Speicherkosten und Mindestgrößen beachten. Als Umschalter nur anzeigen, wenn das Modell es kann. Garantiert die Ersparnis, kostet aber Speicherzeit.

**Weitere Ideen** stehen in Abschnitt 11.

### 9.3 Automatisierte Tests

Die Testsuite liegt in `tests/` und braucht weder Internet noch API-Key. Alle Google-Dienste sind durch Ersatzobjekte ersetzt (`tests/fakes.py`), und jeder Test läuft in einem Wegwerf-Ordner (`AI_BATCH_UI_HOME`).

**Ausführen**

```bash
pip install -r requirements-dev.txt        # installiert zusätzlich pytest
pytest                                     # alle Tests (rund 720, etwa 60 Sekunden)
pytest -m "not ui"                         # nur die schnellen Tests ohne Oberfläche (unter 2 Sekunden)
pytest tests/test_background.py -k cancel  # einzelne Datei oder Namensausschnitt
```

**Aufbau**

| Datei | Inhalt |
|---|---|
| `pytest.ini` | Einstellungen, Marker `ui` für die langsameren Oberflächentests, `pythonpath = src` (damit `import aibui` in den Tests klappt) |
| `tests/conftest.py` | Fixtures: `home` (Wegwerf-Ordner als `AI_BATCH_UI_HOME`, Dummy-Keys für alle Anbieter), `fresh_package` (importiert die Module von `aibui` in jedem Test neu, weil sie ihre Ordner beim Import aus `AI_BATCH_UI_HOME` berechnen), `app` (alle Module von `aibui` als ein Objekt), `rt` (Ersatz für `runtime()`), `fake_time` (keine echten Pausen, in allen Modulen), `price_day` (alle Tests rechnen die Preise mit demselben Tag, sonst hinge das vorausgewählte Gemini-Modell vom Datum des Laufs ab; der Marker `real_date` schaltet das ab), `pricing`, `on_day` (legt den Tag der Preise fest) und `use_all` (Ersatzdienste aller drei Anbieter). Dazu eine Sperre gegen echte API-Zugriffe und ein Sicherheitsnetz: ändert ein Test `conf/` oder `data/` im Projektordner, schlägt der Lauf am Ende fehl |
| `tests/fakes.py` | `FakeGemini` (Files API, Batch-API, Interactions API mit `create`, `get` und `cancel`, `models.generate_content` für die Namen, zeichnet Aufrufe auf), `make_interaction` (echte SDK-Interaktion), `make_name_response` (echte SDK-Antwort von `generate_content`), `ApiError`, `InteractionsError`, `FakeDrive`, `install`, `install_drive`. Für OpenAI: `FakeOpenAI` (Files API und Batch API, liefert echte SDK-Objekte `Batch` und `FileObject`), `make_openai_body` (Antwortrumpf wie in der Ausgabedatei), `OpenAIError`, `install_openai`. Für Claude: `FakeClaude` (Files API und Message Batches API, liefert echte SDK-Objekte `FileMetadata`, `MessageBatch` und `MessageBatchIndividualResponse`), `make_claude_message` (Antwort wie in den Ergebnissen), `claude_errored` (fehlgeschlagene Anfrage), `ClaudeError`, `install_claude`. Dazu `real_claude_client()` (echter SDK-Client, dessen HTTP-Anfragen an eine Testfunktion gehen) mit `json_response()`, `jsonl_response()`, `batch_json()` und `file_json()` |
| `tests/helpers.py` | Verlauf lesen und schreiben, Eintrags-Vorlagen (`batch_entry`, `sync_entry`, `background_entry`, `finished_batch`, `finished_background`, `openai_entry`, `finished_openai_batch`, `claude_entry`, `finished_claude_batch`, `row`), AppTest-Kürzel (`new_app`, `new_openai_app`, `new_claude_app`, `click`, `set_prompts`, `captions`, `markdown`, `sent_to_browser`, `model_field` für das Feld „Modell“, `type_model` für getippten Text darin) |
| `tests/test_logic.py` | reine Logik: Parser, Hilfsfunktionen, Ordner (Dateien im Projektordner bleiben liegen), Verlaufsdatei, Datei-Upload, Batch-Anfragen, Gesprächsverlauf als Text (Aufbau, Wiedereinlesen, mehrfaches Fortsetzen) |
| `tests/test_background.py` | Hintergrund-Modus: Anfrageaufbau (auch gegen das Schema des SDK, mit Dateien aller Arten), Start mit Wiederholung und Aufräumen bei Fehlern, Abfrage (laufend, beendet, `incomplete`, `failed`, `cancelled`, Long-Decode-Schritte), Abbruch, Zeilenparser, Oberfläche (Formular, Start, Jobs-Tab, Übernehmen, Hinweis bei abgeschnittenem Batch; Oberflächentests mit Marker `ui`) |
| `tests/test_drive.py` | Drive-Anmeldung (Token, Neuanmeldung, Netzwerkfehler) und Laden von Dateien |
| `tests/test_files.py` | erlaubte Dateitypen (Issue #16): Art und MIME-Typ je Endung (auch gegen die Aufzählungen im SDK), Prüfung je Anbieter (bei Claude auch die abgelehnten Office-Endungen), Hilfetext. Die Oberfläche dazu prüfen `test_ui.py`, `test_openai.py` und `test_claude.py` |
| `tests/test_ui.py` | Oberfläche mit AppTest: Formular, Starts (auch mit Dokumenten, Bildern, Text und Audio), Sperre bei Dateitypen, die die App nicht kennt, Jobs-Tab, automatische Prüfung, Übernehmen, Löschen, Altbestand (ältere Einträge, auch synchrone, öffnen sich: Der Start ändert den Verlauf nicht und verschiebt keine Dateien), Ordnerlage, Prompt-Anzeige, Gespräch fortsetzen (Marker `ui`) |
| `tests/test_openai.py` | OpenAI-Anbindung: Anfrageaufbau, Datei-Upload (Dokumente, Text, Bilder), Ergebniszeilen, Status und Ergebnisdateien, Anbieter-Schalter, Formularwerte beim Anbieterwechsel (was die App dem Browser schickt), Start, Jobs-Tab, Übernehmen, Fortsetzen. Ein Test prüft, dass die Beispielantworten des Fakes gültige Objekte des SDK sind (Oberflächentests mit Marker `ui`) |
| `tests/test_claude.py` | Claude-Anbindung (Issue #2): Anfrageaufbau (auch gegen das Schema des SDK, mit und ohne Cache-Marke), Dateiname und MIME-Typ für die Files API, Datei-Upload (wiederverwenden, neu hochladen bei fehlender oder bald ablaufender Datei), Ergebniszeilen (Token mit Cache und Denken, Abschlussgründe, Fehler, Abbruch, Ablauf, Ablehnung), Status und Ergebnisse, Abbruch. Vier Tests lassen den echten SDK-Code laufen und fangen nur das HTTP ab (Upload, Batch anlegen, Status, Ergebnisse, Abbruch, 404). Oberfläche: Anbieter-Schalter, Formularwerte beim Anbieterwechsel zwischen allen drei Anbietern, Start (Dokumente, Text, CSV, Bilder, Sperre für Office-Dateien, Audio und Video), Prompt-Cache, Namensvergabe, Jobs-Tab, Übernehmen, Fortsetzen (Oberflächentests mit Marker `ui`) |
| `tests/test_naming.py` | Namen und Suche: Text für das Modell, Bereinigung der Antwort, Aufruf von `generate_content` (Modell, Denktiefe, Zeitlimit), Standardname je Anbieter bzw. Modus (`gemini-…`, `background-gemini-…`, `openai-…`) und Fallback darauf bei Fehlern und ohne Key, Suche, Dateiname; Oberfläche: Start in allen Modi und auch bei OpenAI, Einstellungen der Seitenleiste, Suche im Jobs-Tab, Name und Beschreibung ändern, Name aus dem Prompt erzeugen (Oberflächentests mit Marker `ui`) |
| `tests/test_pricing.py` | Kosten-Infobox (Issue #12): Aufbau der Preistabelle (höchstens 5 Modelle je Anbieter, zu jedem Modell der Liste gibt es einen Preis), Zuordnung des Modellnamens, Preiswechsel am 01.12.2026, Preisstufen nach der Länge des Prompts, Text der Infobox (ohne `$`, weil Streamlit es als Formel liest), der Stand der Preise in der README und die Infobox in der Seitenleiste für alle drei Anbieter, auch ohne API-Key (`ui`) |
| `tests/test_models.py` | Modell-Combobox (Issue #11): Liste aus der Preistabelle, Sortierung nach Kosten am jeweiligen Tag (auch Gleichstand und der Wechsel bei Gemini 4 am 01.12.2026), Voreinstellung = erster Eintrag, Auswahl aus der Liste und getippter Name bis zum Start, ein Name aus dem Verlauf, den die Liste nicht kennt, die Liste ohne API-Key, „Modell für die Namen“ bleibt ein Textfeld (`ui`) |
| `tests/test_costs.py` | Kosten eines Laufs und Preisdatei (Issue #39): `conf/prices.toml` lesen (Preise ändern und Modelle ergänzen, Stufen und Preisstände, großzügig gelesene Namen und Daten, jeder Fehlerfall mit seinem Text, wirkt ohne Neustart), die Rechnung mit von Hand nachgerechneten Beträgen je Anbieter (Cache, Denken, Stufen, Schreiben in den Cache bei Claude nach Lebensdauer, Preisstand des Starttags, Vergleich Batch gegen Hintergrund-Modus bei Gemini, ältere und unsinnige Zeilen), die Texte (ohne `$`), die Anzeige im Tab „Jobs und Ergebnisse“ und in der Seitenleiste (Warnung bei Fehlern in der Datei, neue Modelle in der Combobox) und das Beispiel der Preisdatei in der README (Oberflächentests mit Marker `ui`) |
| `tests/test_modules.py` | Aufbau des Pakets `aibui`: jedes Modul lässt sich einzeln importieren (keine Importzyklen), keines importiert das Hauptskript, auf Modulebene steht kein Streamlit-Aufruf |
| `tests/test_docs.py` | gleicht README und Code ab: genannte Funktionen, Konstanten, Schlüssel, Versionen, Testdateien, Module von `aibui` |
| `tests/test_ci.py` | prüft die GitHub-Actions-Datei: Auslöser, Befehle, Python-Versionen laut README, Rechte |

**Wie getestet wird**

- Die Module von `aibui` werden in jedem Test frisch importiert (Fixture `fresh_package`) und als `app` bereitgestellt (`app.parse_line(...)`: der Name wird in allen Modulen gesucht, `app.modules["history"]` liefert ein Modul selbst). Streamlit-Aufrufe darin laufen im „bare mode“, das ist gewollt.
- Die Oberfläche läuft in Streamlits `AppTest` (`new_app()`): Widgets per `key` ansprechen, Tabs über `at.session_state["view"]` wechseln, Uploads mit `at.file_uploader[0].set_value([(name, bytes, mime)])`.
- Die Combobox „Modell“ hat eine Eigenheit im `AppTest` (Streamlit 1.67): Er rechnet den Zustand einer Selectbox mit der Position des Werts in den Optionen und wirft einen `ValueError`, wenn der Wert fehlt, auch mit `accept_new_options`. Im Browser gibt es das Problem nicht. Darum hängt `type_model()` in `tests/helpers.py` den getippten Text an die Optionen des Test-Elements an, und `model_field()` in `views.py` nimmt den aktuellen Wert immer in die Optionen auf. Wer in einem Test einen Namen außerhalb der Liste in den Session State schreibt, setzt ihn vor dem ersten Lauf oder nimmt `type_model()`. Die Prüfung `accept_new_options` und `required` steht im Protokoll des Elements (`box.proto`).
- Dienste ersetzt man mit `FakeGemini(...)` (Logiktests) bzw. `use_fake(...)` (Oberflächentests). `batch_state`, `get_error`, `batch_cached` und `batch_text` bestimmen, was die Batch-API meldet und was in den Ergebnissen steht. Für den Hintergrund-Modus bestimmt `interaction_results` je Interaktion, wie `interactions.get` antwortet (Argumente für `make_interaction` oder eine Exception), `interaction_create_errors` lässt einzelne `create`-Aufrufe scheitern. `name_text` und `name_error` bestimmen, was `models.generate_content` für die Namen antwortet, `name_calls` zeichnet die Aufrufe auf.
- OpenAI ersetzt `FakeOpenAI(...)` (in `test_openai.py` über `use_openai(...)`). `batch_status`, `failing`, `bodies` und `batch_errors` bestimmen, was die Batch API meldet und was in Ausgabe- und Fehlerdatei steht. Oberflächentests für OpenAI starten mit `new_openai_app()`: Der Anbieter ist dann schon gewählt, und die Namensvergabe ist aus (sie nutzt immer Gemini), es wird also nie ein Gemini-Client gebaut. Wer sie testen will, ruft `new_openai_app(auto_name=True)` auf und installiert einen `FakeGemini`.
- Claude ersetzt `FakeClaude(...)` (in `test_claude.py` über `use_claude(...)`). `batch_status`, `failing`, `answers`, `batch_text` und `batch_cached` bestimmen, was die Message Batches API meldet und was in den Ergebnissen steht, `gone` und `expiry` was die Files API über hochgeladene Dateien sagt. Oberflächentests starten mit `new_claude_app()` (wie bei OpenAI ohne Namensvergabe). `real_claude_client(handler)` baut einen echten Client des SDK, dessen HTTP-Anfragen an `handler` gehen: So prüfen Tests, welche Anfragen das SDK wirklich sendet (Pfade, Multipart-Upload, JSON-Rumpf, kein Beta-Header) und ob es echte JSONL-Ergebnisse richtig liest.
- Drive ersetzt `install_drive(...)`: Anmeldung und Dienst sind Fakes, `token.json` liegt dann in `conf/` des Wegwerf-Ordners.

**Ein neuer Test**

```python
from fakes import FakeGemini, install
from helpers import TAB_JOBS, click, new_app, read_history, set_prompts


def test_beispiel(monkeypatch, home):
    install(monkeypatch, FakeGemini(batch_cached=500))
    at = new_app()
    at.run()
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    at.session_state["view"] = TAB_JOBS
    at.run()  # der Jobs-Tab fragt den Batch ab und sichert das Ergebnis
    at.run()
    assert read_history(home)[0]["rows"][0]["cached"] == 500
```

**Regeln für Tests**

1. Keine echten Dienste und kein Netzwerk. Wer den Fake-Client vergisst, bekommt sofort einen Fehler (automatische Fixture).
2. Nie im Projektordner schreiben, immer die Fixture `home` nutzen.
3. Pausen über `fake_time` überspringen, nie mit festem `sleep` warten.
4. Neue Funktion: Test in `test_logic.py`, bei einem Modus in der Datei des Modus (z. B. `test_background.py`). Neue Oberflächenfunktion: ein `ui`-Test. Neue Datei, Konstante, Schlüssel oder Funktion, die die README nennt: README anpassen, sonst schlägt `test_docs.py` an.
5. Ältere Einträge ohne neue Felder müssen offen bleiben. `test_entries_from_older_versions_still_open` ist das Muster dafür.

**Grenze der Tests.** Sie zeigen, dass die App mit Antworten in der Form des echten SDK richtig umgeht. Sie beweisen nicht, dass Google so antwortet wie `FakeGemini`, OpenAI wie `FakeOpenAI` und Anthropic wie `FakeClaude` (Caching, Limits, Fehlertexte). Das bleibt beim ersten echten Einsatz zu beobachten (Abschnitt 13).

### 9.4 Checkliste vor der Übergabe

- [ ] `pytest` läuft durch (bei reinen Logikänderungen genügt vorab `pytest -m "not ui"`).
- [ ] Neue Funktionen, Anzeigen und Abläufe haben einen Test (9.3), Fehlerfälle und ältere Einträge ohne neue Felder sind abgedeckt.
- [ ] Neue Voreinstellungen, Schlüssel, Funktionen und Dateien stehen in dieser README (Abschnitte 6, 7, 8). `tests/test_docs.py` prüft die wichtigsten Verweise.
- [ ] Es wird nicht behauptet, etwas sei mit der echten API geprüft, wenn es nur simuliert lief (Abschnitt 13).
- [ ] Liegt das Projekt auf GitHub: Der Lauf „Tests“ im Tab „Actions“ ist grün (Abschnitt 9.5).

### 9.5 Tests automatisch auf GitHub (GitHub Actions)

Die Datei `.github/workflows/tests.yml` führt die Testsuite auf GitHub aus, ohne dass man etwas tun muss.

**Wann.** Bei jedem Push, bei jedem Pull Request, auf Knopfdruck (Tab „Actions“ → „Tests“ → „Run workflow“) und einmal pro Woche (montags, 05:17 UTC). Der Wochenlauf ist gewollt: Die Abhängigkeiten stehen als `>=` in `requirements.txt`. Der Wochenlauf meldet, wenn eine neue Version von Streamlit oder eines der SDKs (google-genai, openai, anthropic) etwas bricht.

**Was.** Für jede Python-Version der Matrix (derzeit nur 3.12, die Mindestversion und zugleich die genutzte Version) installiert der Lauf `requirements-dev.txt` und führt `python -m pytest` aus, also dasselbe wie lokal. Es braucht weder API-Key noch Secrets, denn alle Dienste der Anbieter sind in den Tests ersetzt.

**Einrichten.** Der Projektordner muss das Hauptverzeichnis des Repositorys sein, denn dort liegt `.github/`. Repository anlegen, pushen, danach erscheint im Tab „Actions“ der Lauf „Tests“. Ein Badge für die README:

```markdown
![Tests](https://github.com/<benutzer>/<repository>/actions/workflows/tests.yml/badge.svg)
```

**Bewusste Entscheidungen**

- Nur Leserechte (`permissions: contents: read`), keine Secrets, `persist-credentials: false` beim Auschecken.
- Ein neuer Push bricht den noch laufenden Lauf desselben Branches ab (`concurrency`).
- `fail-fast: false`: Enthält die Matrix mehrere Python-Versionen, läuft jede zu Ende, damit man alle Ergebnisse sieht (derzeit steht nur 3.12 darin).
- Die Actions sind an Hauptversionen gebunden (`actions/checkout@v7`, `actions/setup-python@v6`, Stand November 2026). Neue Hauptversionen zieht man von Hand oder per Dependabot nach.

**Pflegen.** Ändert sich die Mindest- oder die genutzte Python-Version in Abschnitt 3, muss die Matrix im Workflow mitziehen, sonst schlägt `tests/test_ci.py` an. Neue Test-Abhängigkeiten gehören in `requirements-dev.txt`, nicht nur in den Workflow.

**Rote Läufe lesen**

- Rot, besonders im Wochenlauf: Das Log im Schritt „Tests ausführen“ lesen. Meist hat eine neue Paketversion etwas gebrochen. Lokal mit `pip install -U streamlit google-genai openai anthropic` bestätigen, dann den Code anpassen oder in `requirements.txt` eine Obergrenze setzen.
- Der Lauf startet gar nicht: meist ein YAML-Fehler. Die Meldung steht im Tab „Actions“. Lokal prüft `tests/test_ci.py` die Datei mit PyYAML.

## 10. Fehlersuche

| Meldung / Symptom | Ursache | Lösung |
|---|---|---|
| `400 INVALID_ARGUMENT … max_output_tokens cannot exceed 32768` | Batch unterstützt kein Long Decode | Im Batch höchstens 32.768 Token. Mehr im Modus „Hintergrund“. |
| Hintergrund: „Start fehlgeschlagen“ mit `400` | Die Interactions API hat die Anfrage abgelehnt. Laut Doku liefern `max_output_tokens` über 65.536 ohne `background=true` und `background=true` ohne `store=true` einen 400-Fehler, beides sendet die App richtig. Möglich bleiben ein zu großes `max_output_tokens` bei großer Eingabe (Doku: höchstens 1.048.576 minus Eingabe) oder ein Modell ohne Unterstützung für den Hintergrund-Modus | Meldung lesen, Limit verkleinern, Modellnamen prüfen. Schon gestartete Prompts desselben Laufs bricht die App ab. |
| Hintergrund: „Abruf fehlgeschlagen … 403“ | Zugriff verweigert, vermutlich gehört der API-Key zu einem anderen Projekt als der, mit dem der Lauf gestartet wurde (ungeprüft) | Den Key des Startprojekts eintragen (Seitenleiste). |
| Hintergrund: Ergebnis „Die Interaktion gibt es bei Google nicht mehr“ | Google antwortet mit 404: Die Aufbewahrung ist abgelaufen oder die Interaktion wurde gelöscht, und das Ergebnis wurde lokal nie gesichert, weil noch nicht alle Prompts beendet waren | Nichts zu retten. Mit „Eingaben übernehmen“ neu starten. Beendete Läufe sichert die App lokal, sobald alle Prompts fertig sind. |
| Hintergrund: Status `incomplete` oder Warnung `MAX_TOKENS` | Denk- plus Ausgabe-Token haben das Limit erreicht | Limit erhöhen (bis 1.048.576 minus Eingabe) oder Denktiefe senken. |
| Hintergrund: „Eingabe“ viel größer als die Dateien | Bei Long Decode zählt `total_input_tokens` die Eingabe jedes 64K-Schritts erneut mit | Normal, der größte Teil davon ist Cache (95 % günstiger). Kontextgröße = Token der Dateien plus Denk- plus Ausgabe-Token. |
| `OSError: inotify watch limit reached` im Terminal | Linux-Limit für Dateibeobachtung erschöpft (oft durch IDE oder Sync-Programm). Die App läuft trotzdem, nur das automatische Neuladen bei Codeänderung fehlt | `--server.fileWatcherType none` oder in `.streamlit/config.toml` setzen, oder `fs.inotify.max_user_watches` erhöhen. |
| pip-Fehler zu `tensorboard`/`tensorflow` nach Installation | `google-auth-oauthlib` oder `numpy`/`protobuf` wurden hochgezogen, bestehende Pakete verlangen ältere Versionen | Eigene Umgebung benutzen (siehe 3), oder `pip install "google-auth-oauthlib<1.1"`. Kein `-U` in gemeinsamen Umgebungen. |
| Cache-Token überall 0 | implizites Caching ist nicht garantiert. Im Batch zusätzlich undokumentiert. Im Modus „Hintergrund“ starten alle Prompts gleichzeitig, keine erste Anfrage füllt den Cache vorher | `usage`-JSON einer Antwort ansehen. Dateien, Reihenfolge und Systemanweisung unverändert lassen. |
| Drive: „Zugriff blockiert“ | Konto nicht als Test user eingetragen | Cloud Console → Audience → Test users (6.4, Schritt 4) |
| Drive: `credentials.json fehlt. Lege sie nach …/conf` | OAuth-Client nicht in `conf/` abgelegt | 6.4, Schritt 6 |
| Drive fragt nach einer Woche erneut nach Anmeldung | „Testing“-Status, Freigabe läuft nach 7 Tagen ab | erwartetes Verhalten, die App meldet sich selbst neu an. Dauerhaft: „Publish app“ oder Workspace „Internal“. |
| Start bricht ab, Statusfeld verschwindet | Tab während der Vorbereitung gewechselt (löst einen Rerun aus) | Start wiederholen und währenddessen im Tab bleiben. |
| Älterer synchroner Eintrag steht auf „unterbrochen“ | Die App wurde beendet oder neu gestartet, solange er lief (den Modus gibt es nicht mehr) | Bisherige Zeilen sind gespeichert. Mit „Eingaben übernehmen“ im Modus „Hintergrund“ neu starten. |
| Antwort abgeschnitten, Warnung `MAX_TOKENS` | Denk- plus Ausgabe-Token haben das Limit erreicht | Denktiefe senken, Token-Limit erhöhen (im Modus „Hintergrund“) oder Aufgabe auf mehrere Prompts aufteilen. |
| Älterer synchroner Eintrag, Gespräch: Prompt 2 „Übersprungen“ | Prompt 1 lieferte Fehler oder keine Antwort | Mit „Eingaben übernehmen“ neu starten (Modus „Hintergrund“, jeder Prompt läuft dort für sich). |
| „Abruf fehlgeschlagen … 404“ bei altem Batch | Batch existiert bei Google nicht mehr (nach Ablauf) und wurde lokal nie gesichert | Nichts zu retten. Eintrag löschen. Neue Batches sichern ihr Ergebnis lokal. |
| OpenAI-Eintrag: „Der OpenAI API-Key fehlt (Seitenleiste)“ | Das Keyfeld dieses Anbieters ist leer, während ein Eintrag von ihm geöffnet ist | Key eintragen. Gesicherte Ergebnisse sind auch ohne Key sichtbar. |
| „Das Paket openai fehlt“ beim Wechsel auf OpenAI | Nach dem Update wurde `pip install -r requirements.txt` nicht ausgeführt | Nachholen. Gemini läuft auch ohne das Paket. |
| OpenAI: Fehler je Prompt zu `reasoning.effort` | Das Modell kennt die gewählte Denktiefe nicht (z. B. `none` bei `gpt-6-astra`) | Andere Stufe oder „Standard“ wählen und neu starten (Eingaben übernehmen). |
| OpenAI-Batch endet mit `failed`, die Meldung nennt ein Token-Limit | Die Summe der Token aller eingereihten Batches überschreitet das Warteschlangenlimit des Modells | Weniger Prompts oder kürzere Dateien je Batch, warten bis andere Batches fertig sind, Limits der Kontostufe bei OpenAI prüfen. |
| Fehler unter dem Datei-Feld („Der Dateityp … wird nicht unterstützt“, „… nimmt OpenAI nicht an, nur Gemini“ oder „… .docx-Dateien nimmt Claude nicht an …“), der Start ist gesperrt | Die Endung steht nicht in `FILE_TYPES`, oder der gewählte Anbieter nimmt die Art der Datei nicht an (Audio und Video nur bei Gemini, Word, PowerPoint und Excel nicht bei Claude) | Die Datei entfernen oder in einen erlaubten Typ umwandeln (Abschnitt 4, „Dateien und erlaubte Typen“). Soll ein weiterer Typ gehen: Abschnitt 9.2. |
| Der Start geht durch, aber ein Lauf oder einzelne Antworten scheitern mit einem Fehler zu einer Datei | Die App prüft nur die Endung. Ob das Modell den Typ annimmt, hängt vom Modell ab (laut Modellseite kennt Gemini 4 Carbon Office-Dateien, andere Modelle womöglich nur PDF und Text) | Die Datei als PDF exportieren oder ein anderes Modell wählen. Der Fehlertext der API steht im Eintrag. |
| OpenAI-Batch `expired`, einzelne Prompts mit Fehler | Das Zeitfenster von 24 Stunden reichte nicht für alle Anfragen. Die fertigen Antworten sind geladen | Die fehlenden Prompts mit „Eingaben übernehmen“ erneut starten. |
| Claude-Eintrag: „Der Claude API-Key fehlt (Seitenleiste)“ | Das Keyfeld dieses Anbieters ist leer, während ein Eintrag von ihm geöffnet ist | Key eintragen. Gesicherte Ergebnisse sind auch ohne Key sichtbar. |
| „Das Paket anthropic fehlt“ beim Wechsel auf Claude | Nach dem Update wurde `pip install -r requirements.txt` nicht ausgeführt | Nachholen. Gemini und OpenAI laufen auch ohne das Paket. |
| Claude: Fehler je Prompt `invalid_request_error` zu `effort` | Das Modell kennt die gewählte Denktiefe nicht (`xhigh` und `max` gibt es nicht bei jedem Modell). Die API prüft die Parameter erst am Ende des Batches, deshalb steht der Fehler erst dann in den Ergebnissen | Andere Stufe oder „Standard“ wählen und neu starten (Eingaben übernehmen). |
| Claude-Batch steht lange auf `in_progress` | Die meisten Batches enden innerhalb einer Stunde, es kann aber bis zu 24 Stunden dauern. Einen Zwischenstand gibt es nicht: Ergebnisse stehen erst, wenn der Batch endet | Warten. Nach 24 Stunden endet der Batch, offene Anfragen stehen dann als „Abgelaufen“ da und werden nicht berechnet. |
| Claude: Prompts mit „Abgelaufen …“ oder „Abgebrochen …“ | Der Batch erreichte das 24-Stunden-Limit bzw. wurde abgebrochen, bevor die Anfragen bearbeitet wurden | Die fehlenden Prompts mit „Eingaben übernehmen“ erneut starten. |
| Claude: Spalte „Cache“ bleibt 0, obwohl „Dateien im Prompt-Cache halten“ an war | Der Prefix war kürzer als die Mindestlänge des Modells (je nach Modell 512 bis 4.096 Token), die Anfragen eines Batches liefen gleichzeitig (ein Eintrag steht erst nach der ersten Antwort bereit), oder Dateien, Reihenfolge, Systemanweisung oder Modell unterschieden sich | Im `usage`-JSON zeigt `cache_creation_input_tokens`, ob in den Cache geschrieben wurde. Ohne Treffer hat das Kästchen nur den Aufschlag gekostet: beim nächsten Lauf ausschalten (Abschnitt 5). |
| Claude: Prompt ohne Text, Warnung mit dem Grund „REFUSAL“ | Das Modell hat die Anfrage abgelehnt, Kategorie und Erklärung der API stehen in der Zeile | Prompt umformulieren oder ein anderes Modell wählen. |
| `data/batch_jobs.defekt-<zahl>.json` taucht auf | `data/batch_jobs.json` war beschädigt, die App hat sie gesichert und neu begonnen | Sicherung prüfen, ggf. Einträge von Hand zurückkopieren. |
| Verlauf leer nach dem Wechsel auf `conf/` und `data/` oder nach der Umbenennung (Issue #18) | `batch_jobs.json` liegt noch im Projektordner statt in `data/` (die App verschiebt seit Issue #34 nichts mehr), oder `AI_BATCH_UI_HOME` zeigt woanders hin bzw. ist nicht gesetzt (bis Issue #18 hieß die Variable `GEMINI_UI_HOME`, der alte Name gilt nicht mehr) | Datei von Hand nach `data/` verschieben bzw. `AI_BATCH_UI_HOME` prüfen. |
| Kosten: „Für `…` ist kein Preis hinterlegt“ | Die Preistabelle kennt das Modell des Eintrags nicht, und der Name, den die API gemeldet hat, ist ihr auch unbekannt (ein älteres oder ein neues Modell) | Den Preis in `conf/prices.toml` eintragen (Abschnitt 6.6): Ab dann gilt er auch für ältere Einträge dieses Modells. |
| Warnung in der Seitenleiste zu `conf/prices.toml` | Ein Eintrag der Preisdatei ist fehlerhaft oder die Datei ist kein gültiges TOML. Die Warnung nennt Eintrag und Grund | Den Fehler beheben, ein Klick in der App genügt. Bis dahin gelten für das betroffene Modell (bei einem Fehler im TOML für alle) die eingebauten Preise. |
| Die geschätzten Kosten weichen von der Rechnung des Anbieters ab | Es ist eine Schätzung: Die Tabelle kann veraltet sein (`PRICES_AS_OF`), bei OpenAI fehlt das gesonderte Schreiben in den Cache (ab GPT-5.6), der Vergleich bei Gemini nimmt gleiche Token an (bei Long Decode nur eine Näherung), und Rabatte oder Gutschriften kennt die App nicht | Preise mit der Preisseite abgleichen (Abschnitt 6.6 oder 9.2). Maßgeblich ist die Rechnung des Anbieters. |
| `ModuleNotFoundError: No module named 'aibui'` | Das Hauptskript steht ohne den Ordner `aibui/` daneben (z. B. nur die eine Datei kopiert) | Den Ordner `aibui/` neben `ai_batch_ui.py` legen und mit `streamlit run src/ai_batch_ui.py` starten (Abschnitt 7). |

## 11. Bekannte Einschränkungen und Ideen

**Einschränkungen**

- OpenAI und Claude gibt es nur im **Batch-Modus**. Der Modus „Hintergrund“ ist Gemini vorbehalten, weil er die Interactions API von Google nutzt.
- Den früheren **synchronen Modus** (Prompts nacheinander, optional als Gespräch über mehrere Prompts mit echtem Mehr-Runden-Verlauf) gibt es nicht mehr (Issue #17). Ältere Einträge davon bleiben les- und löschbar, neue entstehen nicht. Wer ein Gespräch weiterführen will, nutzt „Gespräch fortsetzen“ (der Verlauf geht als Text im Prompt mit).
- Die gültigen Denktiefen sind bei OpenAI und Claude nicht je Modell hinterlegt, weil sie sich schnell ändern: Die Auswahl zeigt alle Stufen, unpassende lehnt die API je Prompt ab.
- OpenAI bekommt PDFs mit Text und Seitenbildern, die Detailstufe (`detail`) ist nicht einstellbar. Die Eingabe-Token können sich deshalb von denen bei Gemini unterscheiden.
- **Claude** (Issue #2): Die App sendet nur `output_config.effort` und kein `thinking`, denn die aktuellen Modelle denken adaptiv. Für ältere Modelle, die Denken nur mit `thinking` und `budget_tokens` kennen, gibt es keinen Schalter. Mehr als 128.000 Ausgabe-Token erlaubt Anthropic im Batch laut Doku nur mit dem Beta-Header `output-300k-2026-03-24` und nur bei einigen Modellen, die App setzt ihn nicht. Ein Batch zeigt keinen Zwischenstand: Die Ergebnisse stehen erst, wenn er endet. Die Message Batches API kennt keinen Namen für den Batch, der Name bleibt lokal. Word, PowerPoint und Excel nimmt Claude nicht als Dokument an, die App sperrt sie, Audio und Video gibt es dort nicht. Den Prompt-Cache gibt es nur als Ganzes (Marke auf der letzten Datei, Lebensdauer 1 Stunde, Abschnitt 5), die 5-Minuten-Variante und mehrere Marken sind nicht einstellbar.
- Implizites Caching ist nicht garantiert und bei Carbon (wie bei Argon) die einzige Cache-Art. Im Batch gibt es dazu keine Doku, und im Modus „Hintergrund“ starten alle Prompts gleichzeitig, was Treffer eher verhindert.
- Der Modus „Hintergrund“ startet alle Prompts **gleichzeitig** (mögliche Ratenbegrenzungen bei vielen Prompts, ein Cache-Treffer für die Dateien ist weniger wahrscheinlich), kennt keine Gespräche (je Prompt eine Interaktion, eine Fortsetzung steckt im Prompt), hat keinen Batch-Rabatt und zeigt keine Zwischenstände oder Denk-Zusammenfassungen. Eine Interaktion läuft laut Google höchstens 24 Stunden, danach gilt sie als `failed`. Long Decode im **Batch** gibt es nicht, solange die Interactions API keinen Batch kennt.
- Der Start (Dateien laden, hochladen) läuft im Hauptskript. Ein Tab-Wechsel währenddessen bricht ihn ab (im Statusfeld vermerkt).
- Die Sperre in `runtime()` gilt nur innerhalb **eines** Streamlit-Prozesses. Nicht zwei Instanzen im selben Ordner starten.
- Der Verlauf wächst ohne Seitenaufteilung. Löschen geht nur einzeln. `data/requests_*.jsonl` sammeln sich an.
- Die **Kosten** (Issue #12 und #39) sind eine Schätzung. Die Infobox nennt die Preise des gewählten Modells, die Kosten eines Laufs rechnet die App aus den Token der Antworten und diesen Preisen, nach dem Lauf und nur für fertige Prompts. Vor dem Start zählt sie keine Token. Die Preise stehen in `src/aibui/pricing.py` (die Anbieter liefern sie nicht über die API) und lassen sich in `conf/prices.toml` ändern, nur für die Modelle dort, und sie veralten, wenn niemand sie pflegt: Der Stand steht unter der Box, maßgeblich sind die Preisseite und die Rechnung des Anbieters. Der Preiswechsel gilt nach dem Starttag des Laufs, nicht auf die Stunde genau (ein Lauf, der am 30.11. spät startet und erst am 01.12. rechnet, zählt noch zum alten Preis). Nicht eingerechnet sind das gesonderte Schreiben in den Cache bei OpenAI (ab GPT-5.6), Rabatte, Gutschriften, Steuern und Preisstufen, die die Tabelle nicht kennt. Der Vergleich Batch gegen Hintergrund-Modus nimmt dieselben Token an, bei Long Decode ist das nur eine Näherung (Abschnitt 4).
- Die **Liste der Modelle** im Feld „Modell“ (Issue #11) kommt aus `PRICES`, nicht aus der Modellliste der Anbieter-APIs. Ein neues Modell erscheint erst, wenn jemand es nach Abschnitt 9.2 einträgt (bis dahin lässt es sich eintippen), und die Liste veraltet wie die Preise. Die APIs wurden geprüft (Stand 21.11.2026, am Quelltext der SDKs und an der Anthropic-Doku, nicht gegen die echten APIs): `models.list()` liefert bei Anthropic `id`, `display_name`, `created_at` (neueste zuerst), `lifecycle`, `line` und `capabilities` (darunter `batch`), bei Google `name`, `display_name`, Token-Limits und `supported_actions` (ob dort die Batch-Eignung je Modell zuverlässig steht, ist ungeprüft), bei OpenAI nur `id`, `created` und `owned_by`, dazu die Modelle für Einbettungen, Bilder und Audio. **Keine der drei liefert Preise**: Eine Sortierung nach Kosten bliebe auf `PRICES` angewiesen, und ein neues Modell ohne Preis ließe sich nicht einordnen, am Ende der Liste stünde das womöglich teuerste. Dazu kämen ein API-Aufruf mit Key (die Seitenleiste steht vor der Prüfung des Keys, die Liste gäbe es ohne Key nicht), ein Zwischenspeicher für die Antwort und bei OpenAI ein Filter nach Namensmustern.
- Keine Streaming-Anzeige, keine Prompt-Bibliothek.
- Texte der Oberfläche sind fest auf Deutsch im Code.
- Drive: nur PDFs und Google-Dokumente (Export als PDF), andere Dateitypen aus Drive (Bilder, Office-Dateien) gibt es noch nicht. Liste zeigt höchstens 50 Dateien, weitere per Link oder ID.
- **Dateien** (Issue #16): Die App prüft nur die Endung, nicht den Inhalt und nicht die Größe (OpenAI: unter 50 MB je Datei, zusammen höchstens 50 MB je Anfrage). Ob ein Modell einen Typ annimmt, hängt vom Modell ab. Bei OpenAI gehen Bilder und Diagramme aus Office-Dateien verloren, Tabellen werden auf die ersten 1.000 Zeilen je Blatt gekürzt, und Audio und Video gibt es nur bei Gemini. Bei Claude gehen nur PDF, Text (auch CSV) und Bilder, Größen und Seitenzahlen der Dateien prüft die App nicht (die Grenzen stehen in der Anthropic-Dokumentation). Textdateien meldet die App Gemini als `text/plain`, auch Markdown, JSON und Quelltext.
- „Gespräch fortsetzen“ schickt den Verlauf als Text in **einer** Nutzernachricht. Es ist kein echter Mehr-Runden-Verlauf mit Modellrolle, und gespeichert sind nur die sichtbaren Antworten (ohne Denkteile). Lange Verläufe kosten bei jeder Anfrage Eingabe-Token, und die Dateien müssen neu angehängt werden.
- Die **Namen** der Einträge entstehen immer mit Gemini (Gemini API-Key nötig), auch bei OpenAI- und Claude-Läufen, ein OpenAI- oder Claude-Modell für die Namen gibt es nicht. Sie sind Vorschläge eines kleinen Modells und können danebenliegen, jeder Name lässt sich ändern. Der Anbieter erfährt von späteren Änderungen nichts: Der Anzeigename des Batches bleibt der vom Start (Claude bekommt nie einen).
- Die **Suche** ist eine einfache Textsuche über Name, Beschreibung, ID, Dateinamen und Prompts (jedes Wort muss vorkommen, ohne Unschärfe). In den Antworten sucht sie nicht.

**Ideen** (grob nach Nutzen)

- Prompt-Vorlagen mit Platzhaltern und einer Werteliste (ein Prompt pro Wert), z. B. „Kapitel {k}, Abschnitt {a}“.
- Einzel-Download je Antwort als `.txt` (z. B. zum Vorlesen) und alle Ergebnisse als ZIP.
- Token zählen vor dem Start (`count_tokens`), um die Größe der Dateien und die 4.096-Token-Schwelle zu sehen und um die Kosten eines Laufs vorab zu schätzen (Issue #39 rechnet erst nach dem Lauf).
- Eingaben des Formulars beim Neustart wiederherstellen.
- Fortsetzung als echter Mehr-Runden-Verlauf (`user`/`model`-Nachrichten statt Text im Prompt). Dazu müsste der Eintrag die Modellantworten samt Denk-Signaturen speichern.
- Long Decode im Batch, sobald Google die Interactions API für die Batch API öffnet (laut Doku „noch nicht verfügbar“), und die clientseitige Fortsetzung der Interactions API (laut Doku „bald“) als Alternative ohne Speicherung auf dem Server.
- Streaming für Hintergrund-Läufe (`stream`, `thinking_summaries`) mit Zwischenständen im Eintrag.
- Tarif/Modus „Flex“ oder andere Preisstufen, falls Google sie für Carbon anbietet (Doku prüfen).
- Explizites Caching als Umschalter für Modelle, die es unterstützen.
- Aufräumen alter `data/requests_*.jsonl` (und `data/requests_openai_*.jsonl` und `data/requests_claude_*.jsonl`).
- Dateien: Größen vor dem Upload prüfen (OpenAI: 50 MB), Bilder und Office-Dateien auch aus Drive laden.
- Claude: der Beta-Header für bis zu 300.000 Ausgabe-Token im Batch, die 5-Minuten-Cache-Marke als Alternative zur Stunde, ein Hinweis nach einem Batch, dessen Prompt-Cache keine Treffer brachte, und Modellvorschläge aus der Modellliste der API.
- OpenAI: Detailstufe der PDF-Seitenbilder und der Bilder (`detail`) wählbar machen.
- Neue Modelle aus der Modellliste der API anbieten, wenn ein Key da ist: hinter der Liste aus `PRICES`, ohne Preis, mit Zwischenspeicher. Bei Anthropic lässt es sich mit `lifecycle`, `line` und `capabilities.batch` sauber filtern, bei Google womöglich mit `supported_actions` (zu prüfen), bei OpenAI nur über Namensmuster (Einschränkungen).
- Dependabot für die Versionen der Actions (`.github/dependabot.yml`).
- Wenige, bewusst kostenpflichtige „Live“-Tests gegen die echte API (eigener Marker, standardmäßig übersprungen), die Annahmen aus Abschnitt 5 prüfen.
- Namen: ein Sammelknopf, der alle Einträge mit Standardnamen auf einmal benennt, ein OpenAI- oder Claude-Modell als Alternative zu Gemini (damit bei OpenAI- und Claude-Läufen nichts an Google geht) und eine Suche auch in den Antworten.

## 12. Sicherheit und Datenschutz

- **Daten verlassen den Rechner**: Dateien, Prompts und Ergebnisse gehen an den gewählten Anbieter: Google (Gemini Files API, Batch-API, Modell), OpenAI (Files API, Batch API, Modell) oder Anthropic (Files API, Message Batches API, Modell). Bei Google liegen hochgeladene Dateien zeitlich begrenzt (derzeit 48 Stunden), Batch-Ergebnisse 6 Wochen. Bei OpenAI setzt die App für Dateien einen Ablauf von 3 Tagen (`OPENAI_FILE_TTL`), die Batch-Datei folgt dem Standard von OpenAI (30 Tage). Die Ausgabe- und Fehlerdateien der Batches löscht die App nicht, sie unterliegen den Aufbewahrungsregeln der OpenAI-Plattform. Bei Anthropic setzt die App für Dateien einen Ablauf von 3 Tagen (`CLAUDE_FILE_TTL`), die Ergebnisse eines Batches bleiben dort laut Doku 29 Tage nach dem Anlegen abrufbar. Wie Anthropic Anfragen und Antworten sonst aufbewahrt und nutzt, steht in dessen Bedingungen und Datenschutzhinweisen (bitte selbst prüfen). Das gilt für Inhalte, die diese Weitergabe erlauben.
- **Namensvergabe**: Ist das Feld „Name“ leer und die Namensvergabe an (Voreinstellung), geht ein Auszug der Prompts (die ersten drei, zusammen höchstens `NAME_SOURCE_CHARS` Zeichen, nie die Dateien oder die Systemanweisung) an das Gemini-Modell für die Namen (Voreinstellung `gemini-3.5-flash-lite`), **auch bei einem OpenAI- oder Claude-Lauf**, sobald ein Gemini API-Key da ist. Das Formular weist bei OpenAI und Claude darauf hin. Wer Prompts nicht an Google geben will, schaltet „Name aus dem Prompt erzeugen“ in der Seitenleiste aus (oder lässt den Gemini API-Key weg) oder tippt den Namen selbst ein. Ob Google Eingaben zur Verbesserung seiner Produkte nutzen darf, hängt vom Tarif des Keys ab: Laut Preisseite von Google (Stand November 2026, bitte selbst prüfen) werden Eingaben und Antworten im kostenlosen Tarif der Gemini API dafür genutzt, im kostenpflichtigen nicht. Das gilt dann auch für diesen Auszug.
- **Drive**: nur Lesezugriff (`drive.readonly`). Die App kann nichts ändern oder löschen.
- **Geheimnisse**: `conf/` (vor allem `credentials.json` und `token.json`) nicht weitergeben und nicht einchecken. Die API-Keys stehen nur in den Browserfeldern oder in den Umgebungsvariablen.
- **Lokale Daten**: `data/` (z. B. `batch_jobs.json`, `requests_*.jsonl`) enthält Prompts und Antworten im Klartext. Ordner entsprechend schützen (`.gitignore`, Dateirechte).
- Die App ist für **einen Benutzer auf dem eigenen Rechner** gedacht, ohne Anmeldung. Streamlit lauscht standardmäßig auch im lokalen Netz (die Startmeldung nennt eine „Network URL“), dann könnte jeder im Netz die App samt API-Key-Feld bedienen. Wer das nicht möchte, startet mit `streamlit run src/ai_batch_ui.py --server.address localhost`. Nicht ungeschützt im Internet betreiben.

## 13. Verifikationsstand und Quellen

**Verifikationsstand (bitte beim ersten echten Einsatz beobachten)**

- Automatisierte Tests (`pytest`, Abschnitt 9.3) prüfen die App durchgehend gegen Ersatzdienste. Sie bestätigen die Logik, nicht das Verhalten der echten Google-Dienste. Alle 324 Tests (Stand der Änderung für Issue #23) liefen grün in einer frisch installierten Umgebung mit Python 3.12.3 und der niedrigsten unterstützten Kombination (Streamlit 1.67.0, google-genai 3.3.0, openai 3.51.0). Alle drei Mindestversionen sind derzeit zugleich die neuesten Versionen, ein zweiter Lauf mit neueren Versionen entfällt deshalb. Gegenüber dem Stand davor (257 Tests) kamen 66 Tests in `tests/test_naming.py` hinzu, dazu einer in `test_modules.py` (dort läuft ein Test je Modul von `aibui`). Angepasst wurden `test_defaults_in_background_mode` und `test_openai_shows_its_own_defaults_and_no_mode_switch` (das Namensfeld ist nun leer statt mit einem Standardnamen gefüllt), `test_every_form_widget_with_a_key_is_kept_alive_between_runs` (Ausnahme `jobs_search`) und der Helfer `new_openai_app()` (er schaltet die Namensvergabe aus, damit nie ein Gemini-Client gebaut wird). Mit Python 3.11 und mit älteren Versionen von Streamlit, google-genai und openai wird nicht mehr getestet. Die GitHub-Actions-Matrix deckt 3.12 ab.
- Die Aufteilung in Module (Abschnitt 8) wurde zusätzlich ohne die Testsuite geprüft: Ein Vergleich der Syntaxbäume mit dem Stand davor zeigte, dass der Code unverändert verschoben wurde (nur `_base_dir()` ist angepasst, weil nun der Ort des Pakets zählt) und der Oberflächenteil identisch ist. Außerdem lief die App unter einem echten `streamlit run` (Streamlit 1.55.0, 1.56.0 und 1.67.0) gegen eine echte WebSocket-Sitzung ohne Browser: Beide Tabs wurden ohne Ausnahme gezeichnet, und nach einer Änderung an `aibui/config.py` zeigte der nächste Lauf den neuen Wert (die Module wurden neu importiert). Dieser Serverlauf gehört nicht zur Testsuite.
- „Gespräch fortsetzen“ und die Prompt-Anzeige wurden zusätzlich einmal in einem echten Headless-Chromium gegen die laufende App mit Ersatzdiensten durchgespielt (Klick im Fragment, Tab-Wechsel, Hinweis, Startsperre, zweites Fortsetzen ohne Verschachtelung). Dieser Browsertest gehört nicht zur Testsuite.
- Der Anbieterwechsel (Gemini, OpenAI, zurück zu Gemini, mit leerem und mit gesetztem OpenAI-Key, auch bei geöffnetem Jobs-Tab) wurde ebenfalls in einem echten Headless-Chromium gegen die laufende App durchgespielt. Modell, Denktiefe, Token-Limit, Prompts und Systemanweisung blieben erhalten, beide Anbieter behielten ihre eigenen Werte. Ohne die Zuweisung vor dem Zeichnen (`FORM_KEYS`) standen nach dem Rückwechsel das Modellfeld leer, das Token-Limit auf 256, die Denktiefe auf „Standard“, und Prompts und Systemanweisung fehlten. Auch dieser Browsertest gehört nicht zur Testsuite.
- Der GitHub-Workflow (Abschnitt 9.5) wurde mit `actionlint` geprüft, und seine Befehle liefen wie oben beschrieben in frischen Umgebungen. Auf GitHub selbst lief er noch nicht.
- **Namen und Suche (Issue #23): nur mit simulierten Diensten getestet**, nicht gegen die echte Gemini-API (in der Entwicklungsumgebung gab es keinen API-Key). `FakeGemini` liefert für `models.generate_content` echte SDK-Antworten (`types.GenerateContentResponse`, mit Denk-Teil). Zusätzlich lief `generate_name()` einmal durch den echten SDK-Code von google-genai 3.3.0, nur der HTTP-Aufruf war abgegriffen: Die Anfrage enthielt Modell, Systemanweisung, `maxOutputTokens`, die Denktiefe und ein Zeitlimit von 30 Sekunden, und die Antworten (Text mit Denk-Teil, nur Denk-Teil, blockierter Prompt) wurden richtig gelesen. Dieser Lauf gehört nicht zur Testsuite. Das Verhalten der neuen Oberflächenteile (Popover, Suchfeld, Platzhalter) wurde nur mit `AppTest` geprüft, nicht in einem echten Browser. Zum Modell der Namen, `gemini-3.5-flash-lite` (Aufruf über die normale Gemini API von Google mit dem Gemini API-Key, nicht über Vertex AI oder ein Gateway), stützt sich die Doku auf Googles Seiten unter ai.google.dev (Stand 15.11.2026): Modell-ID, Einstufung als allgemein verfügbar und weiter für den Betrieb nutzbar (Vorgängergeneration, das neueste Flash-Modell ist Gemini 3.8 Flash), die Voreinstellung der Denktiefe `minimal`, die Empfehlung `medium` oder `high` für Agenten und die Preise (0,30 USD je Million Eingabe-Token, 2,50 USD je Million Ausgabe-Token) stehen im Leitfaden „What's new in Gemini 3.6 Flash and 3.5 Flash-Lite“. Gelesen wurden dort Auszüge aus Suchtreffern, nicht die ganze Seite. Dass Denk-Token als Ausgabe zählen, steht auf der Preisseite. Dass `thinking_level` bei Gemini 3.x die Werte `minimal`, `low`, `medium` und `high` kennt und Temperatur, `top_p` und `top_k` entfallen sollen (die App sendet keinen davon), steht auf der geöffneten Seite zu Gemini 3.5 Flash. Eine eigene Tabelle der Stufen für 3.5 Flash-Lite wurde nicht gefunden. Der Hinweis, dass Google Eingaben im kostenlosen Tarif zur Verbesserung seiner Produkte nutzt, im kostenpflichtigen nicht, stammt von der Preisseite (Auszüge aus Suchtreffern). Ungeprüft, bitte beim ersten echten Einsatz beobachten: ob `gemini-3.5-flash-lite` den Aufruf mit allen vier Stufen annimmt (bei einem Fehler gilt der Standardname, und eine Warnung nennt den Grund), ob `NAME_MAX_OUT` mit der Denktiefe `medium` immer reicht (die Denk-Token zählen mit, bleibt der Text leer, gilt der Standardname und eine Warnung nennt den Grund), ob das Zeitlimit `NAME_TIMEOUT_MS` genügt, ob der kostenlose Tarif die Aufrufe begrenzt und ob die Namen brauchbar sind.
- Mit der echten API bestätigt (19.10.2026, noch mit Argon): Batch-Modus mit **einem** PDF und mehreren Prompts, Denktiefe `high`, Ergebnisabruf und Anzeige. Dabei meldeten alle Antworten Cache 0.
- **Umstellung auf Gemini 4 Carbon: nur anhand der Google-Dokumentation (11.11.2026) und mit den simulierten Diensten der Testsuite geprüft**, nicht gegen die echte API. Geändert wurden der Modellname der Voreinstellung (damals eine Konstante, seit Issue #11 der erste Eintrag der Modellliste), Beschriftungen und die Doku. Anfrageformat, `thinking_level`-Werte, SDK-Mindestversion (damals 2.30.1 für `generate_content`) und Token-Limits blieben unverändert, weil Google den Umstieg von Argon als reinen Modellnamenwechsel beschreibt.
- **Nur mit simulierten Diensten getestet**, nicht gegen echte Dienste: mehrere PDFs, Drive-Anbindung samt Neuanmeldung, lokale Sicherung der Batch-Ergebnisse, „Eingaben übernehmen“, „Gespräch fortsetzen“ (wie das Modell auf einen Prompt mit eingefügtem Verlauf antwortet), Löschen, Fehlerzähler der automatischen Prüfung. Die Ordnerstruktur (`src/`, `conf/`, `data/`) samt Übernahme alter Dateien lief nur in Wegwerf-Ordnern, noch nicht im echten Projektordner.
- **OpenAI-Anbindung: nur mit simulierten Diensten getestet**, nicht gegen die echte OpenAI-API (in der Entwicklungsumgebung gab es weder Key noch Zugriff). `FakeOpenAI` liefert echte SDK-Objekte (`Batch`, `FileObject`), und ein Test stellt sicher, dass die Beispielantworten gültige `Response`-Objekte des SDK sind (openai 3.51.0). Feldnamen, Endpunkt, Parameter und die erlaubten Denktiefen stammen aus der OpenAI-Dokumentation und dem SDK. Ungeprüft, bitte beim ersten echten Einsatz beobachten: ob ein Batch am Endpunkt `/v1/responses` PDFs per `file_id` (`input_file`) annimmt (die gelesenen Dokumentationsstellen schließen es nicht aus, bestätigen es für Batches aber auch nicht), welche Denktiefen das gewählte Modell kennt, ob Cache-Treffer im Batch vorkommen, die Fehlercodes der Fehlerdatei (die Beispiele in den Tests sind nicht aus echten Läufen) und die Meldung bei überschrittenem Warteschlangenlimit.
- **Claude-Anbindung (Issue #2): nur mit simulierten Diensten getestet**, nicht gegen die echte Anthropic-API (in der Entwicklungsumgebung gab es keinen API-Key). Alle 562 Tests liefen grün mit Python 3.12.3, sowohl in der niedrigsten unterstützten Kombination (Streamlit 1.67.0, google-genai 3.3.0, openai 3.51.0, anthropic 2.10.0) als auch mit den neuesten Versionen vom 18.11.2026 (google-genai 3.5.0, openai 3.55.0). `FakeClaude` liefert echte SDK-Objekte (`FileMetadata`, `MessageBatch`, `MessageBatchIndividualResponse`). Tests stellen sicher, dass die Beispielantworten gültige `Message`-Objekte des SDK sind und dass jede gesendete Anfrage dem Schema `MessageCreateParamsNonStreaming` entspricht (anthropic 2.10.0), auch mit Cache-Marke und allen Stufen der Denktiefe. Zusätzlich laufen vier Tests durch den echten SDK-Code, nur das HTTP ist abgefangen (`real_claude_client()`): Sie prüfen die Pfade, den Multipart-Upload mit `expires_in_seconds`, den JSON-Rumpf von `messages/batches` samt Cache-Marke, das Lesen eines JSONL-Ergebnisstroms (Antwort, Fehler, Ablauf), den Abbruch, den 404-Fehler samt `status_code` und dass das SDK für Files API und Message Batches API keinen Beta-Header setzt. Feldnamen, Parameter, Limits und Verhalten stammen aus der Anthropic-Dokumentation (Stand 18.11.2026: Batch processing, Effort, Thinking, Files API, Prompt caching, Links in „Quellen“) und aus dem SDK. Die Seiten wurden gelesen, nicht gegen die echte API ausprobiert. Ungeprüft, bitte beim ersten echten Einsatz beobachten: ob ein Batch `file_id`-Verweise in `document`- und `image`-Blöcken annimmt (die gelesenen Stellen der Batch-Doku nennen keine Einschränkung, bestätigen es aber nicht ausdrücklich), ob die Files API Textdateien und CSV als `text/plain` annimmt (so empfiehlt es die Doku, getestet ist nur, dass die App sie so hochlädt), welche Denktiefen das gewählte Modell kennt (`xhigh` und `max` nicht überall), ob `usage.output_tokens_details.thinking_tokens` in Batch-Ergebnissen gefüllt ist (sonst steht „Denken“ auf 0 und die Denk-Token stecken in „Ausgabe“), ob und wie oft Cache-Treffer in einem Batch vorkommen (Anthropic nennt 30 bis 98 %) und die genauen Fehlertexte (die Beispiele in den Tests sind nicht aus echten Läufen). Die Annahmen zu Preisen und Aufschlägen im Abschnitt 5 (Rechnung zum Prompt-Cache) sind eigene Rechnungen mit den dort genannten Faktoren, die Preisseite von Anthropic nennt die Beträge je Modell. Auch hier wurde die Oberfläche nur mit `AppTest` geprüft, nicht in einem echten Browser.
- **Kosten-Infobox (Issue #12): Preise von den Preisseiten der Anbieter (20.11.2026), Oberfläche nur mit `AppTest` geprüft**, nicht gegen echte Dienste und nicht in einem echten Browser. Ob Streamlit die Markdown-Tabelle in der blauen Box der schmalen Seitenleiste so darstellt wie gedacht, ist ungesehen. Alle 605 Tests liefen grün mit Python 3.12.3, Streamlit 1.67.0, google-genai 3.6.1, openai 3.57.0 und anthropic 2.11.0, ebenso mit den Mindestversionen aus `requirements.txt` (google-genai 3.3.0, openai 3.51.0, anthropic 2.10.0). Die Preise für Claude (Sonnet 5.5, Opus 5.5, Haiku 5.5 mit der Stufe ab 100.000 Token, Fable 5.2) stammen von der Preisseite von Anthropic, die für Gemini 4 Carbon und Argon samt dem Wechsel am 01.12.2026 von der Preisseite von Google und die für `gpt-6-astra`, `gpt-6.1-sol` und `gpt-6-luna` (kurzer und langer Kontext) von der Preisseite von OpenAI. Nicht abgelesen, sondern abgeleitet oder aus anderer Quelle: (1) Der Batch kostet überall die Hälfte des Standardpreises (`BATCH_FACTOR`). Bei Gemini und OpenAI nennen die Preisseiten das auch für den Cache, bei Claude nur für Eingabe und Ausgabe. Den Cache-Preis im Batch hat die App selbst gerechnet: Cache-Faktor der Preisseite mal Batch-Rabatt, weil Anthropic schreibt, dass sich beide multiplizieren. (2) Dass der Hintergrund-Modus den Standardpreis kostet, steht schon in Abschnitt 5 (Google-Doku zu Long Decode, 13.11.2026) und wurde für diese Änderung nicht erneut geprüft. (3) Die Grenze von 272.000 Eingabe-Token für den höheren Preis bei OpenAI stammt aus einem Hilfeartikel von OpenAI zu den Preisen und aus Berichten Dritter, nicht von der Preisseite selbst. (4) Zu welcher Uhrzeit und in welcher Zeitzone der Preiswechsel von Gemini 4 am 01.12.2026 gilt, fand die Recherche nicht. Die Tabelle enthielt zunächst nur die Modelle, die die App in Hilfetexten und Voreinstellungen nannte, dazu Argon. Issue #11 hat sie auf die aktuellen Modelle erweitert und `gpt-6.1-sol` entfernt (siehe den nächsten Punkt).
- **Modell-Combobox (Issue #11): Oberfläche nur mit `AppTest` geprüft**, nicht gegen echte Dienste und nicht in einem echten Browser. Ungesehen: wie die Combobox in der schmalen Seitenleiste aussieht, wie Streamlit einen getippten Namen anbietet und ob sich das Feld im Browser wirklich nicht leeren lässt (`required` prüft nur der Browser). Alle 630 Tests liefen grün mit Python 3.12.3, Streamlit 1.67.0, google-genai 3.6.1, openai 3.57.0 und anthropic 2.12.0, ebenso mit den Mindestversionen aus `requirements.txt` (google-genai 3.3.0, openai 3.51.0, anthropic 2.10.0). Die Preise für `gpt-6.2-astra`, `gpt-6.2-sol` und `gpt-6.1-terra` (kurzer und langer Kontext) stammen von der Preisseite von OpenAI (21.11.2026 gelesen), die für `gpt-6-astra` und `gpt-6-luna` wurden dabei erneut verglichen. Die Auswahl der OpenAI-Modelle folgt der Preisseite: Dort nennt ein Hinweis zu den Abschlägen für Hintergrundanfragen genau GPT-6.2 Astra, GPT-6.2 Sol, GPT-6.1 Terra und GPT-6 Luna, dazu kommt `gpt-6-astra`, der bisherige Standard. `gpt-6.1-sol` kostet wie das neuere `gpt-6.2-sol` und fiel wegen der Grenze von 5 Modellen heraus. **Nicht von der Preisseite von Google gelesen** sind die Preise für Gemini 4 Neon (3/15 USD, Cache 0,15) und Hydrogen (1,50/7,50 USD, Cache 0,075), je flach über das ganze 1-Mio.-Fenster: Die Seite war bei der Recherche nur als Zwischenspeicher von Anfang Juni 2026 ohne Gemini 4 abrufbar. Die Zahlen beruhen auf übereinstimmenden Berichten Dritter (Quellen unten). Einer davon gibt die Preisseite von Google vom 19.11.2026 wieder: bei Neon mit Batch (1,50/7,50 USD, Cache 0,075) und ohne Enddatum für den Preis, bei Hydrogen mit 1,50/7,50 USD, ebenfalls ohne Enddatum. Dass der Batch bei Hydrogen die Hälfte kostet und dass der Hintergrund-Modus bei beiden den Standardpreis kostet, ist abgeleitet wie bei Carbon und Argon. **Vor dem Merge gegen die Preisseite von Google prüfen.** Ungeprüft ist auch, ob Batch, Hintergrund-Modus und die Einstellungen zur Denktiefe bei Neon und Hydrogen so laufen wie bei Carbon (Neon kennt laut dem Bericht zusätzlich die Stufe `xhigh`, die die App nicht anbietet): Sie stehen jetzt in der Liste, die App ist aber nur mit Argon gegen die echte API und mit Carbon anhand der Dokumentation geprüft. Die Aussagen zu den Modelllisten der APIs (Abschnitt 11) stammen aus dem Quelltext der SDKs und der Anthropic-Doku, nicht aus einem Aufruf der echten APIs.
- **Kosten eines Laufs und Preisdatei (Issue #39): Rechnung und Oberfläche nur mit Ersatzdiensten und `AppTest` geprüft**, nicht gegen echte Dienste, nicht gegen eine echte Rechnung und nicht in einem echten Browser. Die erwarteten Beträge der Tests sind von Hand nachgerechnet, nicht mit dem Code der App. In einem Mutationslauf (gezielt eingebaute Fehler in der Rechnung, der Preisdatei und der Anzeige) bemerkten die neuen Tests jeden der 13 Fehler. Alle 719 Tests liefen grün mit Python 3.12.3, Streamlit 1.67.0, google-genai 3.6.1, openai 3.57.0 und anthropic 2.12.0. Aus der Dokumentation der Anbieter gelesen (22.11.2026): bei Anthropic die Preisfaktoren (Schreiben in den Cache das 1,25- bzw. das Doppelte des Eingabepreises, Lesen ein Bruchteil je nach Modell, der Batch-Rabatt gilt zusätzlich) und dass die Cost API einen Admin-Key braucht und Kosten nur als Tagessummen liefert, dazu am SDK die Felder von `Usage` (`input_tokens` ohne Cache, dazu `cache_creation_input_tokens`, `cache_read_input_tokens` und `cache_creation` mit der Lebensdauer); bei Google, dass die Eingabe-Token einer Antwort die Token aus dem Cache einschließen; bei OpenAI, dass ab GPT-5.6 das Schreiben in den Cache gesondert berechnet wird (die Preisseite führt eine eigene Spalte). Dass die Costs-Schnittstelle von OpenAI einen Admin-Key braucht und nur Tagessummen liefert, stammt nur aus Forumsbeiträgen, nicht aus der API-Referenz. Ungeprüft, bitte beim ersten echten Einsatz mit der Rechnung vergleichen: ob die Schätzung zur Rechnung passt, ob bei OpenAI `cache_write_tokens` in `input_tokens` stecken (Doku und Forumsbeiträge sind dazu nicht eindeutig, darum fehlt das Schreiben in den Cache bei OpenAI in der Rechnung), ob Google bei Long Decode im Hintergrund-Modus so abrechnet, wie die Schätzung annimmt (Eingabe jedes Schritts zum Standardpreis, der Cache-Anteil zum Cache-Preis), und wie Streamlit die zusätzliche Zeile in den Ergebnissen darstellt.
- **Hintergrund-Modus (Issue #19): nur anhand der Google-Dokumentation (Long Decode, Background Execution, Interactions API, Developer Guide zu Carbon, Stand 13.11.2026) und mit den simulierten Diensten der Testsuite geprüft**, nicht gegen die echte API (in der Entwicklungsumgebung gab es keinen API-Key). `FakeGemini` liefert echte SDK-Objekte (`google.genai.interactions.Interaction`), und ein Test stellt sicher, dass die gesendete Anfrage dem Schema des SDK entspricht (`CreateModelInteraction`). Ungeprüft, bitte beim ersten echten Einsatz beobachten: ob `gemini-4-carbon` die Interactions API mit `background=true` wie dokumentiert annimmt (der Developer Guide zu Carbon beschreibt `background=True`, die Doku zu Background Execution nennt in ihrer Modellliste, Stand 21.10.2026, nur Argon und Gemini 3.8 Flash), ob die Files-API-Referenz eines PDFs als `document` mit `uri` angenommen wird (so zeigt es die Doku zur Dokumentverarbeitung), ob die API ein `max_output_tokens` nahe 1.048.576 bei großer Eingabe ablehnt oder kürzt (Doku: „minus Eingabe“), ob mehrere gleichzeitige Läufe in Ratenbegrenzungen laufen und wie die Abrechnung der Schritte aussieht. Die App behandelt jeden Status außer `in_progress` und `queued` als Ende, damit eine unerwartete Statusangabe das Abfragen nicht endlos weiterlaufen lässt.
- **Dateien statt nur PDFs (Issue #16): nur mit simulierten Diensten getestet**, nicht gegen die echten APIs (in der Entwicklungsumgebung gab es keinen API-Key). Die Typen und Wege stützen sich auf die Dokumentation (Stand 18.11.2026). Bei OpenAI auf die Seite „File inputs“ (ganz gelesen: Responses API, `input_file` mit Dokumenten, Text und Tabellen, Zweck `user_data`, unter 50 MB je Datei und zusammen höchstens 50 MB je Anfrage, außer bei PDFs nur der Text) und auf Auszüge der Seite zu Bildern (PNG, JPEG, WEBP und GIF ohne Animation, ein Bild per Datei-ID aus der Files API). Bei Google auf Auszüge der Modellseite zu Gemini 4 Carbon in der Cloud-Dokumentation (PDF, Text, Office- und OpenDocument-Dateien, Bilder, Audio, Video) und der Files-API-Anleitung der Interactions API (Dateien mit `uri` und `mime_type` der hochgeladenen Datei). Dazu kommen die Aufzählungen der MIME-Typen im SDK (google-genai 3.4.0): Ein Test gleicht `FILE_TYPES` damit ab, und ein weiterer stellt sicher, dass eine Anfrage mit allen vier Arten dem Schema `CreateModelInteraction` entspricht. `FakeGemini` und `FakeOpenAI` halten MIME-Typ und Zweck jedes Uploads fest. Ungeprüft, bitte beim ersten echten Einsatz beobachten: ob ein OpenAI-Batch am Endpunkt `/v1/responses` Bilder als `input_image` mit `file_id` annimmt (der Zweck `vision` stammt aus Beispielcode des OpenAI-.NET-SDKs zur Bilddokumentation, die gelesenen Auszüge der Seite nennen ihn nicht) und Office-Dateien als `input_file`. Ob Gemini Textdateien als `text/plain` und Office-Dateien als `document` annimmt, im Batch (`file_data`) wie in der Interactions API (deren SDK führt `text/plain` nicht unter den Dokumenttypen, lässt aber auch andere Werte zu), und ob das für andere Modelle als `gemini-4-carbon` gilt. Ob Audio und Video samt Verarbeitungszeit der Files API (Zustand PROCESSING) in beiden Modi klappen und wie sich Cache-Treffer bei Bildern, Audio und Video verhalten. Die Oberfläche (Datei-Feld ohne Typbeschränkung, Fehlermeldung, gesperrter Start, Dateien bleiben beim Anbieterwechsel im Feld) wurde nur mit `AppTest` geprüft, nicht in einem echten Browser.
- Zur Frage in Issue #19, ob Carbon ohne Long Decode schon 65.536 statt 32.768 schafft: laut Google-Doku **ja, aber nur in der Interactions API** (Standardlimit 65.536, ohne `background=true` auch Obergrenze). Der Batch läuft über `generateContent` (nicht streamend 32.768 je Anfrage) und die Interactions API kennt laut Doku noch keinen Batch. Ob Carbon im Batch dennoch mehr als 32.768 annimmt, bleibt **ungeprüft** (Prüfweg in Abschnitt 5, Tabelle „Batch-Ausgabelimit“).
- Ungeprüft, bisher nur mit Argon beobachtet oder dokumentiert: ob die Batch-Antworten für Carbon ein Cache-Feld unter anderem Namen führen (siehe `usage`-JSON) und ob der Batch bei Carbon dasselbe Ausgabelimit von 32.768 Token hat.

**Quellen** (Stand Oktober 2026, bitte auf Änderungen prüfen)

- Was ist neu in Gemini 4 Carbon (Modell-ID, Denktiefe, Long Decode, Umstieg von Argon, Stand 11.11.2026): <https://aistudio.google.com/docs/whats-new-gemini-4-carbon>
- Preise für Gemini 4 Carbon und Argon (Standard, Batch, Preiswechsel am 01.12.2026, Stand 11.11.2026, für die Kosten-Infobox am 20.11.2026 erneut gelesen): <https://aistudio.google.com/docs/pricing>
- Token und Nutzungsangaben der Interactions API (Eingabe, Cache, Denken; für Issue #39 am 22.11.2026 gelesen): <https://ai.google.dev/gemini-api/docs/interactions/tokens>
- Preise für Gemini 4 Neon und Hydrogen (Issue #11, am 21.11.2026 nur aus Berichten Dritter gelesen, nicht von der Preisseite von Google): <https://computingforgeeks.com/gemini-4-neon-pricing-api/>, <https://dev.to/hassann/gemini-4-neon-pricing-3-input-15-output-and-what-a-call-really-costs-5g09>, <https://munderdiffl.in/blog/gemini-4-neon/>, <https://www.eesel.ai/blog/gemini-4-hydrogen-pricing>
- Gemini 3.6 Flash und 3.5 Flash-Lite (Modell-ID `gemini-3.5-flash-lite`, Voreinstellung der Denktiefe `minimal`, Preise, Stand November 2026): <https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.6>
- Denktiefen und Parameter bei Gemini 3.x (`thinking_level` mit `minimal`, `low`, `medium`, `high`, keine Temperatur): <https://ai.google.dev/gemini-api/docs/generate-content/whats-new-gemini-3.5>
- Gemini 4 Argon, Modellseite: <https://ai.google.dev/gemini-api/docs/models/gemini-4-argon>
- Was ist neu in Gemini 4 Argon (Denktiefe, Long Decode, Timeouts, Caching): <https://ai.google.dev/gemini-api/docs/generate-content/latest-model>
- Batch-API (JSONL-Format, Preis, Aufbewahrung): <https://ai.google.dev/gemini-api/docs/batch-api>
- Long Decode (Interactions API, `background=true`, Limits, Abrechnung, Statuswerte): <https://ai.google.dev/gemini-api/docs/long-decode>
- Background Execution (Anlegen, Abfragen, Abbrechen, Aufbewahrung): <https://ai.google.dev/gemini-api/docs/background-execution>
- Interactions API (Überblick, Aufbewahrung 55 Tage, Batch API „noch nicht verfügbar“): <https://ai.google.dev/gemini-api/docs/interactions-overview>
- Long Decode mit `generateContent` (clientseitige Fortsetzung, 32K je nicht streamender Anfrage): <https://ai.google.dev/gemini-api/docs/generate-content/long-decode>
- Gemini 4 Carbon: Developer Guide (65.536 Standardlimit der Interactions API, `background=True` bis 1M): <https://aistudio.google.com/learn/gemini-4-carbon-developer-guide>
- Context Caching (implizit/explizit, Nutzungsfelder): <https://ai.google.dev/gemini-api/docs/caching>
- Files API in der Interactions API (Dateien hochladen, `uri` und `mime_type`, Stand 18.11.2026): <https://ai.google.dev/gemini-api/docs/interactions/files>
- Gemini 4 Carbon, Modellseite in der Google-Cloud-Dokumentation (unterstützte Eingabetypen, Stand 18.11.2026): <https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/4-carbon>
- Drive-API-Quickstart für Python (OAuth-Einrichtung): <https://developers.google.com/workspace/drive/api/quickstart/python>
- Streamlit-Dokumentation (`st.tabs`, `st.fragment`, `AppTest`): <https://docs.streamlit.io>

OpenAI (Stand 10.11.2026, bitte auf Änderungen prüfen):

- Batch API (Format, Fenster, Limits, Statuswerte, Ergebnis- und Fehlerdatei): <https://developers.openai.com/api/docs/guides/batch>
- Batch anlegen (Parameter): <https://developers.openai.com/api/docs/api-reference/batch/create>
- Dateien als Eingabe (`input_file`, erlaubte Typen, `user_data`, Größenlimits, Stand 18.11.2026): <https://developers.openai.com/api/docs/guides/file-inputs>
- Bilder als Eingabe (`input_image`, Formate, Datei-ID, Stand 18.11.2026): <https://developers.openai.com/api/docs/guides/images-vision>
- PDF-Dateien (Text und Seitenbilder, `detail`): <https://developers.openai.com/api/docs/guides/pdf-files>
- Prompt Caching (Prefix, `cached_tokens`, Cache-Schreiben): <https://developers.openai.com/api/docs/guides/prompt-caching>
- Aktuelle Modelle und ihre Denktiefen: <https://developers.openai.com/api/docs/guides/latest-model> und Modellseite <https://developers.openai.com/api/docs/models/gpt-6-astra>
- Preise (Standard, Batch, kurzer und langer Kontext, für die Kosten-Infobox am 20.11.2026 gelesen, für Issue #11 am 21.11.2026 erneut, für Issue #39 am 22.11.2026 wegen der Spalte zum Schreiben in den Cache ab GPT-5.6): <https://developers.openai.com/api/docs/pricing>
- Forumsbeitrag zur Abrechnung von Cache-Lese- und Schreib-Token bei GPT-5.6 (die Zahlen passen nicht eindeutig zusammen, darum ist das Schreiben in den Cache bei OpenAI nicht eingerechnet): <https://community.openai.com/t/question-about-gpt-5-6-api-cache-read-write-token-billing/1386256>

Anthropic (Stand 18.11.2026, bitte auf Änderungen prüfen):

- Batch processing (Message Batches API: Format, Limits, Statuswerte, Ergebnisse, Abbruch, Preis, Caching im Batch): <https://platform.claude.com/docs/en/build-with-claude/batch-processing>
- Effort (`output_config.effort`, Stufen, Voreinstellungen, adaptives Denken): <https://platform.claude.com/docs/en/build-with-claude/effort>
- Thinking (Denk-Token, `max_tokens`, Abrechnung): <https://platform.claude.com/docs/en/build-with-claude/thinking>
- Files API (Hochladen, `expires_in_seconds`, `document`- und `image`-Blöcke mit `file_id`, Dateinamen, erlaubte Typen): <https://platform.claude.com/docs/en/build-with-claude/files>
- Prompt caching (`cache_control`, `ttl`, Mindestlängen, Preisfaktoren, Nutzungsfelder): <https://platform.claude.com/docs/en/build-with-claude/prompt-caching>
- Pricing (Standard, Batch, Cache-Faktoren, höhere Stufe ab 100.000 Token bei Haiku 5.5, für die Kosten-Infobox am 20.11.2026 gelesen, für Issue #39 am 22.11.2026 erneut: Cache-Faktoren, der Batch-Rabatt gilt zusätzlich): <https://platform.claude.com/docs/en/about-claude/pricing>
- Usage and Cost API (Admin-Key, Kosten nur als Tagessummen, für Issue #39 am 22.11.2026 gelesen): <https://platform.claude.com/docs/en/build-with-claude/usage-cost-api>
- Modelle (aktuelle Modelle und Modell-IDs, `line` für Modellauswahlen in der Models API, für Issue #11 am 21.11.2026 gelesen): <https://platform.claude.com/docs/en/about-claude/models/overview>

## Glossar

- **Anbieter**: Gemini (Google), OpenAI oder Claude (Anthropic). Jeder Verlaufseintrag gehört zu einem Anbieter (Pflichtfeld `provider`: `Gemini`, `OpenAI` oder `Claude`).
- **Combobox**: Auswahlfeld mit freier Eingabe. Das Feld „Modell“ ist eine (`st.selectbox` mit `accept_new_options=True`): Man wählt aus der Liste oder tippt einen anderen Namen.
- **Responses API**: OpenAIs Schnittstelle für Textantworten. Die Batch API nimmt sie als Endpunkt `/v1/responses` und liefert Ausgabe- und Fehlerdatei.
- **Message Batches API**: Anthropics Schnittstelle für Batches der Messages API. Sie nimmt die Anfragen als Liste (`custom_id` und `params`) statt als hochgeladene JSONL-Datei, liefert die Ergebnisse erst, wenn der Batch endet, und kennt keinen Namen für den Batch.
- **Prompt-Cache** (Claude): explizites Caching mit einer Cache-Marke (`cache_control`) auf einem Block: Sie gilt für den Prefix bis dorthin. Schreiben kostet einen Aufschlag, Lesen ist günstiger, Treffer sind in einem Batch nicht garantiert.
- **Prefix**: der gemeinsame Anfang zweier Anfragen. Implizites Caching greift darauf.
- **Implizites Caching**: Google erkennt gleiche Anfänge automatisch und berechnet sie günstiger. Keine Zusage.
- **Explizites Caching**: man legt selbst einen Cache an und referenziert ihn. Garantiert die Ersparnis, für Carbon und Argon nicht verfügbar.
- **Long Decode**: automatische Fortsetzung über mehrere Teilanfragen, wenn die Ausgabe das Limit pro Anfrage überschreitet. Im Hintergrund-Modus setzen Googles Server die Antwort fort (Schritte zu je 64K Token). Im Batch gibt es das nicht.
- **Hintergrund-Interaktion** (Background Execution): eine Anfrage der Interactions API mit `background=true`. Sie läuft bei Google bis zu 24 Stunden und wird über ihre ID abgefragt oder abgebrochen.
- **Runde**: ein früherer Prompt samt deiner Antwort dazu. Ein Gesprächsverlauf besteht aus Runden (Abschnitt 7).
- **Fragment**: ein Streamlit-Abschnitt, der sich allein neu ausführen kann (hier für die automatische Statusprüfung).
- **Preisdatei**: die optionale Datei `conf/prices.toml`, die Preise der eingebauten Tabelle ändert oder Modelle ergänzt (Abschnitt 6.6).
- **Kostenschätzung**: die Kosten eines Laufs, aus den Token der Antworten und den Preisen der Tabelle berechnet, mit dem Preisstand des Starttags (Abschnitt 4). Keine Abrechnung.
