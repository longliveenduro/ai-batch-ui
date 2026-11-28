"""AI Batch UI: lokale Oberfläche für Batch-Läufe mit Gemini 4 Carbon, OpenAI und Claude (Streamlit).

Start:    pip install -r requirements.txt && streamlit run src/ai_batch_ui.py   (im Projektordner)
API-Key:  Umgebungsvariablen GEMINI_API_KEY, OPENAI_API_KEY und ANTHROPIC_API_KEY oder Seitenleiste.
Anbieter: Gemini (Batch und Hintergrund), OpenAI (nur Batch, Responses-Endpunkt) oder Claude (nur Batch, Message
          Batches API), gewählt in der Seitenleiste.
Modi:     Batch (asynchron, 50 % Rabatt) oder Hintergrund (nur Gemini: Interactions API mit background=true, Long Decode
          bis 1.048.576 Ausgabe-Token, läuft bei Google und braucht die App nicht, Standardpreis).
Modell:   Das Feld „Modell“ ist eine Combobox mit den aktuellen Modellen des Anbieters, das teuerste zuerst. Das
          beste Modell des Anbieters ist vorausgewählt (BEST_MODELS in aibui/pricing.py). Ein anderer Name lässt sich
          eintippen.
Kosten:   Unter dem Feld „Modell“ nennt eine Infobox die Preise des gewählten Modells je 1 Mio. Token (Batch, bei
          Gemini auch Hintergrund). Die Preistabelle, aus der auch die Liste der Modelle kommt, steht in
          aibui/pricing.py.
Ordner:   conf/ (Zugangsdaten, geheim: credentials.json, token.json) und data/ (batch_jobs.json = Verlauf und
          Ergebnisse, pdf_files.json, openai_files.json und claude_files.json = hochgeladene Dateien,
          requests_*.jsonl = gesendete Batch-Anfragen).
          Beide liegen im Projektordner neben src/ (dem Ordner dieser Datei), oder unter dem Ordner aus der
          Umgebungsvariable AI_BATCH_UI_HOME.
Drive:    (optional) In der Google Cloud Console die Drive API aktivieren, eine OAuth-Client-ID
          vom Typ „Desktop-App“ erstellen und als conf/credentials.json ablegen.
          Beim ersten Zugriff öffnet sich der Browser zur Freigabe (nur Lesezugriff).
Namen:    Ist das Feld „Name“ leer, erzeugt ein kleines Gemini-Modell (Voreinstellung gemini-3.5-flash-lite) den
          Namen aus dem Prompt (Seitenleiste „Namen der Einträge“). Im Tab „Jobs und Ergebnisse“ lassen sich Name
          und Beschreibung ändern, und die Suche findet Einträge wieder.
Aufbau:   Diese Datei enthält nur die Oberfläche (Seitenleiste, Tabs, Formular, Start-Handler). Die Logik steht
          im Paket aibui/ neben dieser Datei (Übersicht in der README, Abschnitt 8).
"""
import hashlib
import os
from datetime import datetime

import streamlit as st

from aibui.background import start_background
from aibui.claude_batch import start_claude_batch, upload_file_claude
from aibui.config import (BATCH_MAX_OUT, BG_DEFAULT_OUT, BG_MAX_OUT, CLAUDE_EFFORTS, CLAUDE_MAX_OUT,
                          DEFAULT_NAME_MODEL, DEFAULT_NAME_THINK, DONE, FORM_KEYS, HINT, MAX_POLL_ERRORS, MODE_BATCH,
                          MODE_BG, NAME_SOURCE_CHARS, NAME_THINK_LEVELS, OPENAI_EFFORTS, OPENAI_MAX_OUT, POLL_SECONDS,
                          PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDERS, SEPARATOR, TABS, TALK_NEW,
                          THINK_LEVELS, prepare_folders)
from aibui.drive import drive_fetch, drive_id, drive_service
from aibui.files import check_files, types_overview
from aibui.forms import delete_entry, entry_label, generate_title, reuse_inputs, save_details
from aibui.gemini import start_batch, upload_file
from aibui.history import load_jobs, mutate_jobs, runtime
from aibui.naming import choose_label, default_label, search_jobs
from aibui.openai_batch import start_openai_batch, upload_file_openai
from aibui.providers import batch_info, entry_mode, entry_provider, make_client
from aibui.talk import entry_group, parse_conversation
from aibui.views import job_panel, model_field, show_costs

st.set_page_config(page_title="AI Batch UI", layout="wide")

prepare_folders()
for key in FORM_KEYS:  # hält die Werte am Leben und schickt sie beim erneuten Zeichnen an den Browser
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]
with st.sidebar:
    provider = st.radio("Anbieter für neue Anfragen", PROVIDERS, key="provider", horizontal=True,
                        help="Jeder Eintrag im Tab „Jobs und Ergebnisse“ gehört zu seinem Anbieter und wird mit "
                             "dessen API-Key abgefragt. Alle Keys dürfen deshalb eingetragen bleiben.")
    keys = {PROVIDER_GEMINI: st.text_input("Gemini API-Key", os.getenv("GEMINI_API_KEY", ""), type="password"),
            PROVIDER_OPENAI: st.text_input("OpenAI API-Key", os.getenv("OPENAI_API_KEY", ""), type="password"),
            PROVIDER_CLAUDE: st.text_input("Claude API-Key", os.getenv("ANTHROPIC_API_KEY", ""), type="password")}
    if provider == PROVIDER_OPENAI:
        model = model_field(provider, key="model_openai",
                            tooltip="Das Modell muss die Batch API und Dateieingaben (bei Bildern: Bildeingaben) "
                                    "unterstützen.")
    elif provider == PROVIDER_CLAUDE:
        model = model_field(provider, key="model_claude",
                            tooltip="Das Modell muss die Message Batches API und für die Denktiefe den Parameter "
                                    "effort kennen (die aktuellen Modelle tun es).")
    else:
        model = model_field(provider, key="model_gemini",
                            tooltip="Die App ist auf die Gemini-4-Modelle zugeschnitten (Batch-Limit, Stufen der "
                                    "Denktiefe, Caching).")
    show_costs(provider, model)
    with st.expander("Namen der Einträge"):
        st.session_state.setdefault("auto_name", True)
        st.session_state.setdefault("name_model", DEFAULT_NAME_MODEL)
        st.session_state.setdefault("name_think", DEFAULT_NAME_THINK)
        auto_name = st.checkbox(
            "Name aus dem Prompt erzeugen", key="auto_name",
            help="Ist das Feld „Name“ in „Neue Anfrage“ leer, erzeugt ein kleines Gemini-Modell den Namen aus dem "
                 "Anfang der Prompts, ähnlich den Titeln im Verlauf eines Chatbots. Dafür geht ein Auszug der Prompts "
                 f"(höchstens {NAME_SOURCE_CHARS} Zeichen, nie die PDFs) an Google, auch wenn der Lauf selbst bei "
                 "OpenAI oder Claude läuft. Ohne Gemini API-Key oder bei einem Fehler gilt der Standardname.")
        name_model = st.text_input(
            "Modell für die Namen", key="name_model",
            help="Gemini-Modell für die Namen, mit dem Gemini API-Key von oben. Voreinstellung ist "
                 "gemini-3.5-flash-lite, das schnellste und günstigste Modell der Gemini-3.5-Familie.")
        name_think = st.selectbox(
            "Denktiefe für die Namen", NAME_THINK_LEVELS, key="name_think",
            help="Für einen kurzen Namen genügt minimal oder low. gemini-3.5-flash-lite denkt ohne Angabe auf "
                 "minimal, die App sendet die Stufe immer. Welche Stufen ein anderes Modell kennt, steht in dessen "
                 "Doku. Bei einem Fehler gilt der Standardname.")
        if not keys[PROVIDER_GEMINI]:
            st.caption("Ohne Gemini API-Key bekommt jeder neue Eintrag den Standardnamen.")
if not keys[provider]:
    env_name = {PROVIDER_OPENAI: "OPENAI_API_KEY", PROVIDER_CLAUDE: "ANTHROPIC_API_KEY"}.get(provider, "GEMINI_API_KEY")
    st.info(f"Trage links deinen {provider} API-Key ein oder setze die Umgebungsvariable {env_name}.")
    st.stop()


def client_for(p):
    """Client des Anbieters p, oder None, wenn dessen API-Key fehlt."""
    return make_client(p, keys[p]) if keys[p] else None


try:
    client = client_for(provider)
except RuntimeError as e:  # z. B. das Paket openai oder anthropic fehlt
    st.error(f"Der {provider}-Client lässt sich nicht erstellen: {e}")
    st.stop()


def gemini_client():
    """Gemini-Client für die Namen: der Client des Laufs, bei OpenAI und Claude ein eigener (None ohne Gemini API-Key)."""
    return client if provider == PROVIDER_GEMINI else client_for(PROVIDER_GEMINI)


rt = runtime()

tab_new, tab_jobs = st.tabs(TABS, key="view", on_change="rerun")  # .open sagt, welcher Tab offen ist
on_jobs_tab = tab_jobs.open

with tab_new:
    note = st.session_state.pop("reused_note", None)
    if note:
        st.info(note)
    if provider in (PROVIDER_OPENAI, PROVIDER_CLAUDE):
        mode = MODE_BATCH
        within = {PROVIDER_OPENAI: "Ergebnis innerhalb von 24 Stunden",
                  PROVIDER_CLAUDE: "Ergebnis meist innerhalb einer Stunde, spätestens nach 24 Stunden"}[provider]
        st.caption(f"Mit {provider} läuft nur der Batch-Modus (50 % Rabatt, {within}). "
                   "Der Modus „Hintergrund“ ist Gemini vorbehalten.")
    else:
        mode = st.radio("Modus", [MODE_BATCH, MODE_BG], horizontal=True, key="mode")
    bg = mode == MODE_BG
    # Kein type=: Welche Typen gehen, hängt vom Anbieter ab (check_files). Die Hilfe bleibt gleich, denn ein anderer Text
    # würde das Widget beim Anbieterwechsel neu aufbauen und seine Dateien verlieren.
    uploads = st.file_uploader("Dateien (mehrere möglich)", accept_multiple_files=True, help=types_overview())
    with st.container(border=True):
        st.markdown("**PDFs aus Google Drive hinzufügen** (optional)")
        if st.button("Meine PDFs aus Drive laden"):
            try:
                res = drive_service().files().list(
                    q="mimeType='application/pdf' and trashed=false", orderBy="modifiedTime desc",
                    pageSize=50, fields="files(id,name)", supportsAllDrives=True, includeItemsFromAllDrives=True,
                ).execute()
                st.session_state["drive_pdfs"] = {f"{f['name']} [{f['id'][:6]}]": f["id"] for f in res["files"]}
            except Exception as e:
                st.error(f"Drive-Zugriff fehlgeschlagen: {e}. Falls der Login hängt, conf/token.json löschen.")
        drive_list = st.session_state.get("drive_pdfs", {})
        chosen = st.multiselect("Zuletzt geänderte PDFs", list(drive_list), placeholder="PDFs auswählen") if drive_list else []
        links = st.text_area("Oder Drive-Links / Datei-IDs einfügen (eine pro Zeile)", height=80)
    pasted = [drive_id(x) for x in links.splitlines() if x.strip()]
    drive_refs = [drive_list[c] for c in chosen] + pasted
    file_order = [f.name for f in uploads] + chosen + [f"Drive-Datei {ref[:6]}" for ref in pasted]
    if file_order:
        st.caption("Reihenfolge der Dateien in jeder Anfrage: "
                   + ", ".join(f"{k}. {n}" for k, n in enumerate(file_order, 1))
                   + " (hochgeladene Dateien zuerst, dann Drive). Gleiche Dateien werden nur einmal gesendet.")
    else:
        st.caption("Keine Datei angehängt: Die Prompts werden ohne Datei gesendet. Möglich sind "
                   + ("PDF, Text (auch CSV) und Bilder." if provider == PROVIDER_CLAUDE else
                      "Dokumente (PDF, Word, PowerPoint, Excel, Text), Bilder und bei Gemini auch Audio und Video."))
    problems = check_files(provider, [f.name for f in uploads])  # Typen, die der gewählte Anbieter nicht annimmt
    if problems:
        st.error("\n".join(f"- {p}" for p in problems)
                 + "\n\nDer Start ist gesperrt, bis diese Dateien entfernt sind. Die erlaubten Typen stehen in der "
                   "Hilfe (?) am Feld „Dateien“.")

    system = st.text_area("Systemanweisung (optional)", height=80, key="system")
    raw = st.text_area("Prompts (mehrere mit einer Zeile --- trennen)", height=260, key="raw")
    prompts = [p.strip() for p in SEPARATOR.split(raw) if p.strip()]
    talks = [parse_conversation(p) for p in prompts]  # Prompts, die ein früheres Gespräch fortsetzen
    unfinished = [k for k, (turns, own) in enumerate(talks, 1) if turns and not own]
    if any(turns for turns, _ in talks):
        st.caption(f"{sum(1 for turns, _ in talks if turns)} von {len(prompts)} Prompt(s) setzen ein früheres Gespräch "
                   "fort. Der Verlauf steht im Prompt und zählt bei jeder Anfrage als Eingabe.")
    if unfinished:
        st.warning(f"Unter „{TALK_NEW}“ fehlt noch dein neuer Prompt (Prompt {', '.join(map(str, unfinished))}). "
                   "Der Start klappt erst, wenn dort Text steht.")
    c1, c2, c3 = st.columns(3)
    if provider == PROVIDER_OPENAI:
        st.session_state.setdefault("effort", "Standard")
        think = c1.selectbox("Denktiefe", OPENAI_EFFORTS, key="effort",
                             help="reasoning.effort der Responses API. „Standard“ sendet nichts, dann gilt die "
                                  "Voreinstellung des Modells. Welche Stufen ein Modell kennt, hängt vom Modell ab "
                                  "(z. B. kennt gpt-6-astra kein „none“). Andere Stufen lehnt die API ab, "
                                  "der Fehler steht dann im Ergebnis.")
    elif provider == PROVIDER_CLAUDE:
        st.session_state.setdefault("effort_claude", "Standard")
        think = c1.selectbox("Denktiefe", CLAUDE_EFFORTS, key="effort_claude",
                             help="output_config.effort der Messages API. „Standard“ sendet nichts, dann gilt die "
                                  "Voreinstellung des Modells (medium bei Opus 5.5 und Haiku 5.5, sonst high). Welche "
                                  "Stufen ein Modell kennt, hängt vom Modell ab (xhigh gibt es nicht bei allen). Andere "
                                  "Stufen lehnt die API ab, der Fehler steht dann im Ergebnis.")
    else:
        st.session_state.setdefault("think", "high")
        think = c1.selectbox("Denktiefe", THINK_LEVELS, key="think")
    if provider == PROVIDER_OPENAI:
        st.session_state.setdefault("max_openai", 32768)
        max_out = c2.number_input("Max. Ausgabe-Token", min_value=256, max_value=OPENAI_MAX_OUT, step=1024,
                                  key="max_openai",
                                  help="max_output_tokens. Denk-Token zählen zum Limit. Das Maximum hängt vom "
                                       "Modell ab (bei den aktuellen Modellen bis 128.000).")
    elif provider == PROVIDER_CLAUDE:
        st.session_state.setdefault("max_claude", 32768)
        max_out = c2.number_input("Max. Ausgabe-Token", min_value=256, max_value=CLAUDE_MAX_OUT, step=1024,
                                  key="max_claude",
                                  help="max_tokens. Denk-Token zählen zum Limit. Das Maximum hängt vom Modell ab "
                                       "(bei den aktuellen Modellen bis 128.000).")
    elif bg:
        st.session_state.setdefault("max_bg", BG_DEFAULT_OUT)
        max_out = c2.number_input("Max. Ausgabe-Token", min_value=256, max_value=BG_MAX_OUT, step=1024, key="max_bg",
                                  help="Denk- und Ausgabe-Token zusammen. Bis 65536 ist es eine einzige Anfrage, darüber "
                                       "setzen Googles Server die Antwort in Schritten zu je 64K Token fort (Long Decode). "
                                       "Höchstens 1.048.576 Token minus Eingabe. Berechnet wird nur, was tatsächlich anfällt.")
    else:
        st.session_state.setdefault("max_batch", BATCH_MAX_OUT)
        max_out = c2.number_input("Max. Ausgabe-Token", min_value=256, max_value=BATCH_MAX_OUT, step=1024, key="max_batch",
                                  help="Im Batch-Betrieb begrenzt die API die Ausgabe auf 32768 Token. Mehr geht im "
                                       "Modus „Hintergrund“ (Long Decode).")
    # Art des Eintrags: gibt den Standardnamen (gemini-…, background-gemini-…, openai-…, claude-…) und den Schlüssel
    # des Namensfelds vor. Ein Batch heißt nach dem Anbieter, denn „batch“ gibt es bei allen. Ein Lauf im Hintergrund nennt
    # Modus und Anbieter: Den Modus gibt es nur bei Gemini, der Name unterscheidet ihn von Batches.
    kind = {PROVIDER_OPENAI: "openai", PROVIDER_CLAUDE: "claude"}.get(provider, "background-gemini" if bg else "gemini")
    naming_on = auto_name and bool(keys[PROVIDER_GEMINI])  # sonst gilt der Standardname
    label = c3.text_input("Name", key="label_" + kind,
                          placeholder="automatisch aus dem Prompt" if naming_on else default_label(kind),
                          help="Leer lassen: Der Name wird aus dem Prompt erzeugt (Seitenleiste „Namen der Einträge“), "
                               "sonst gilt der Standardname. Im Tab „Jobs und Ergebnisse“ lassen sich Name und "
                               "Beschreibung später ändern.")
    if naming_on and provider != PROVIDER_GEMINI and not label.strip():
        st.caption(f"Der Name wird mit Gemini erzeugt: Ein Auszug der Prompts (höchstens {NAME_SOURCE_CHARS} Zeichen, "
                   f"ohne Dateien) geht dafür an Google, auch bei einem {provider}-Lauf. Abschalten: Seitenleiste, "
                   "„Namen der Einträge“.")
    cache = False
    if provider == PROVIDER_CLAUDE:
        st.session_state.setdefault("cache_claude", False)
        cache = st.checkbox("Dateien im Prompt-Cache halten (1 Stunde)", key="cache_claude",
                            help="Markiert die Dateien (samt Systemanweisung davor) für den Prompt-Cache von Claude. "
                                 "Schreiben in den Cache kostet das Doppelte des Eingabepreises, Lesen nur einen "
                                 "Bruchteil. Das lohnt sich bei vielen Prompts zu denselben Dateien. Weil ein Batch "
                                 "seine Anfragen gleichzeitig bearbeitet, ist ein Treffer nicht garantiert (Anthropic "
                                 "nennt 30 bis 98 %). Bei einem einzelnen Prompt kostet es nur mehr. Ohne Dateien gibt "
                                 "es nichts zu cachen, und kürzere Präfixe als je nach Modell 512 bis 4.096 Token "
                                 "cacht Claude nicht.")
    if bg:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Jeder Prompt läuft als Hintergrund-Interaktion bei Google (Interactions "
            "API, background=true), alle gleichzeitig. Long Decode setzt die Antwort über 65.536 Token hinaus fort "
            "(bis 1.048.576 Token minus Eingabe). Die App muss nicht laufen, sie fragt nur den Stand ab. Es gilt der "
            "Standardpreis statt des Batch-Rabatts, und weil alle Prompts gleichzeitig starten, ist ein Cache-Treffer "
            "für die Dateien nicht garantiert. Gespräche mit mehreren Prompts gibt es hier nicht (je Prompt eine "
            "Interaktion), eine Fortsetzung steckt im Prompt."
        )
    elif provider == PROVIDER_OPENAI:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Die OpenAI Batch API kostet 50 % des Standardpreises und liefert die "
            "Ergebnisse innerhalb von 24 Stunden. Die Dateien stehen in jeder Anfrage an erster Stelle, damit der "
            "Prefix für das automatische Caching (ab 1.024 Token) identisch ist. Treffer siehst du unter "
            "„Jobs und Ergebnisse“."
        )
    elif provider == PROVIDER_CLAUDE:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Die Message Batches API von Anthropic kostet 50 % des Standardpreises. "
            "Die meisten Batches enden innerhalb einer Stunde, Anfragen, die nach 24 Stunden noch offen sind, verfallen. "
            "Die Dateien stehen in jeder Anfrage an erster Stelle. Claude cacht sie nur, wenn du das Kästchen „Dateien "
            "im Prompt-Cache halten“ anschaltest. Treffer siehst du unter „Jobs und Ergebnisse“."
        )
    else:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Batch kostet 50 % des Standardpreises. Carbon unterstützt nur "
            "implizites Caching (ab 4.096 Token, ohne Rabattgarantie): Die Dateien stehen in jeder Anfrage an erster "
            "Stelle, damit der Prefix identisch ist. Treffer siehst du unter „Jobs und Ergebnisse“."
        )

    # Gesperrt wird nur, was sofort feststeht: die Dateien. Der Text im Feld „Prompts“ kommt erst beim Verlassen des Felds
    # oder mit Strg+Enter beim Server an. Ein Zustand, der daran hängt, liefe dem Tippen hinterher: Der Button wäre grau,
    # obwohl ein Aufruf möglich ist, und ein Klick darauf ginge je nach Timing durch oder verloren (Issue #36). Der Klick
    # übernimmt den Text zuerst und prüft ihn dann hier.
    start = st.button("Im Hintergrund starten" if bg else "Batch starten", type="primary", disabled=bool(problems))
    if start and not prompts:
        st.error("Nicht gestartet: Es fehlt noch ein Prompt. Trage ihn im Feld „Prompts“ ein.")
    elif start and unfinished:
        st.error(f"Nicht gestartet: Unter „{TALK_NEW}“ fehlt noch dein neuer Prompt "
                 f"(Prompt {', '.join(map(str, unfinished))}).")
    elif start:
        try:
            with st.status("Bereite Anfragen vor …" + HINT) as status:
                files = [(f.name, f.getvalue()) for f in uploads]
                if drive_refs:
                    status.update(label="Lade PDFs aus Google Drive …" + HINT)
                    files += [drive_fetch(ref) for ref in drive_refs]
                unique, seen = [], set()
                for fname, data in files:  # gleiche Dateien nur einmal senden
                    digest = hashlib.sha256(data).hexdigest()
                    if digest not in seen:
                        seen.add(digest)
                        unique.append((fname, data))
                names, uploaded = [n for n, _ in unique], []
                upload = {PROVIDER_OPENAI: upload_file_openai, PROVIDER_CLAUDE: upload_file_claude}.get(provider,
                                                                                                    upload_file)
                for k, (fname, data) in enumerate(unique, 1):
                    status.update(label=f"Lade Datei {k} von {len(unique)} zu {provider} hoch …" + HINT)
                    uploaded.append(upload(client, fname, data))
                if naming_on and not label.strip():
                    status.update(label="Erzeuge den Namen …" + HINT)
                title, generated, name_error = choose_label(label, kind, prompts, gemini_client, name_model, name_think,
                                                            auto_name)
                status.update(label="Starte …" + HINT)
                if bg:
                    entry = start_background(client, rt, model, uploaded, names, prompts, system.strip(), think,
                                             max_out, title)
                elif provider == PROVIDER_OPENAI:
                    batch_id, keyed = start_openai_batch(client, model, uploaded, prompts, system.strip(), think,
                                                         max_out, title)
                    # pdf und pdfs heißen aus Kompatibilität mit älteren Einträgen noch so, enthalten aber alle Dateinamen
                    entry = {"name": batch_id, "provider": PROVIDER_OPENAI, "label": title, "model": model,
                             "pdf": ", ".join(names) or None, "pdfs": names, "prompts": keyed, "system": system.strip(),
                             "think": think, "max_out": int(max_out),
                             "created": datetime.now().isoformat(timespec="seconds")}
                    mutate_jobs(rt.lock, lambda jobs: jobs.insert(0, entry))
                elif provider == PROVIDER_CLAUDE:
                    batch_id, keyed = start_claude_batch(client, model, uploaded, prompts, system.strip(), think,
                                                         max_out, cache)
                    entry = {"name": batch_id, "provider": PROVIDER_CLAUDE, "label": title, "model": model,
                             "pdf": ", ".join(names) or None, "pdfs": names, "prompts": keyed, "system": system.strip(),
                             "think": think, "max_out": int(max_out), "cache": cache,
                             "created": datetime.now().isoformat(timespec="seconds")}
                    mutate_jobs(rt.lock, lambda jobs: jobs.insert(0, entry))
                else:
                    job, keyed = start_batch(client, model, uploaded, prompts, system.strip(), think, max_out, title)
                    entry = {"name": job.name, "provider": PROVIDER_GEMINI, "label": title, "model": model,
                             "pdf": ", ".join(names) or None, "pdfs": names, "prompts": keyed,
                             "system": system.strip(), "think": think, "max_out": int(max_out),
                             "created": datetime.now().isoformat(timespec="seconds")}
                    mutate_jobs(rt.lock, lambda jobs: jobs.insert(0, entry))
                status.update(label="Gestartet", state="complete")
            st.session_state["sel"] = entry_label(entry)  # der neue Eintrag ist im Jobs-Tab vorausgewählt
            st.session_state["jobs_search"] = ""  # und eine Suche dort würde ihn vielleicht verstecken
            if bg:
                st.success(f"{entry['name']} läuft bei Google. Im Tab „Jobs und Ergebnisse“ wird der Stand alle "
                           f"{POLL_SECONDS} Sekunden geprüft, die App muss dafür nicht durchgehend laufen.")
            else:
                st.success(f"{entry['name']} läuft. Im Tab „Jobs und Ergebnisse“ wird der Status alle "
                           f"{POLL_SECONDS} Sekunden geprüft.")
            if name_error:
                st.warning(f"{name_error} Der Eintrag heißt „{title}“. Im Tab „Jobs und Ergebnisse“ lässt sich der "
                           "Name ändern.")
            elif generated:
                st.caption(f"Name aus dem Prompt erzeugt: „{title}“. Im Tab „Jobs und Ergebnisse“ lässt er sich "
                           "ändern.")
        except Exception as e:
            st.error(f"Start fehlgeschlagen: {e}")

with tab_jobs:
    all_jobs = load_jobs()
    name_note = st.session_state.pop("name_note", None)  # einmaliger Hinweis (Name erzeugen gescheitert)
    if name_note:
        st.warning(name_note)
    query = st.text_input("Suche", key="jobs_search", placeholder="Name, Beschreibung, Prompt, Datei oder ID",
                          help="Zeigt nur Einträge, in denen alle Suchwörter vorkommen (Groß- und Kleinschreibung "
                               "egal). Durchsucht werden Name, Beschreibung, ID, Dateinamen und Prompts."
                          ) if all_jobs else ""
    jobs = search_jobs(all_jobs, query)
    if query.strip():
        st.caption(f"Treffer: {len(jobs)} von {len(all_jobs)} Einträgen.")
    if not all_jobs:
        st.info("Noch nichts gestartet.")
    elif not jobs:
        st.info(f"Kein Eintrag passt zu „{query.strip()}“.")
    else:
        opts = {entry_label(x): x for x in jobs}
        if st.session_state.get("sel") not in opts:
            st.session_state.pop("sel", None)
        j = opts[st.selectbox("Eintrag", list(opts), key="sel")]
        if j.get("description"):
            st.caption(j["description"])
        mode_j, grp, entry_prov = entry_mode(j), entry_group(j), entry_provider(j)
        kind_txt = ((f"synchron, {grp} Prompts pro Gespräch" if grp > 1 else "synchron") if mode_j == "sync"
                    else "Hintergrund (Long Decode)" if mode_j == "background"
                    else "Batch (OpenAI)" if entry_prov == PROVIDER_OPENAI
                    else "Batch (Claude)" if entry_prov == PROVIDER_CLAUDE else "Batch")
        st.caption(f"{j['name']}, {kind_txt}, gesendet: Modell {j['model']}, "
                   f"Denktiefe {j.get('think', 'unbekannt')}, max. {j.get('max_out', '?')} Ausgabe-Token, "
                   f"Dateien: {j['pdf'] or 'keine'}, {len(j['prompts'])} Prompt(s)"
                   + (", Prompt-Cache (1 Stunde)" if j.get("cache") else ""))
        if mode_j == "sync":
            running = False  # ältere synchrone Einträge: nichts läuft mehr, nichts ist abzufragen
        else:
            info = batch_info(j)
            failed = st.session_state.get("errn:" + j["name"], 0) >= MAX_POLL_ERRORS
            running = not ((info and info["state"] in DONE) or failed)
        a1, a2, a3, _ = st.columns([1, 1, 1, 2])
        a1.button("Eingaben übernehmen", on_click=reuse_inputs, args=(j,), key="reuse:" + j["name"],
                  help="Übernimmt Prompts und Einstellungen ins Formular „Neue Anfrage“.")
        with a2.popover("Eintrag löschen", disabled=running):
            st.write("Entfernt den Eintrag samt lokal gesicherter Ergebnisse aus dem Verlauf. "
                     "Beim Anbieter bleibt alles unverändert.")
            st.button("Ja, endgültig löschen", on_click=delete_entry, args=(j["name"],), key="del:" + j["name"])
        with a3.popover("Name und Beschreibung"):
            st.session_state.setdefault("title:" + j["name"], j["label"])
            st.session_state.setdefault("descr:" + j["name"], j.get("description", ""))
            st.text_input("Name", key="title:" + j["name"])
            st.text_area("Beschreibung (optional)", key="descr:" + j["name"], height=100,
                         help="Freier Text, den die Suche mit durchsucht, z. B. wofür der Lauf war.")
            st.button("Speichern", on_click=save_details, args=(j,), key="save:" + j["name"])
            st.button("Name aus dem Prompt erzeugen", on_click=generate_title,
                      args=(j, gemini_client, name_model, name_think), key="gen:" + j["name"],
                      disabled=not keys[PROVIDER_GEMINI],
                      help="Erzeugt den Namen neu, mit den Einstellungen unter „Namen der Einträge“ (Seitenleiste)."
                           if keys[PROVIDER_GEMINI] else "Dafür fehlt der Gemini API-Key (Seitenleiste).")
        job_client = client if entry_prov == provider else client_for(entry_prov)  # jeder Eintrag mit seinem Anbieter
        polling = on_jobs_tab and running and job_client is not None
        st.fragment(run_every=POLL_SECONDS if polling else None)(job_panel)(job_client, j, polling)
