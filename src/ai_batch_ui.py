"""AI Batch UI: lokale Oberfläche für Batch-Läufe mit Gemini 4 Carbon und OpenAI (Streamlit).

Start:    pip install -r requirements.txt && streamlit run src/ai_batch_ui.py   (im Projektordner)
API-Key:  Umgebungsvariablen GEMINI_API_KEY und OPENAI_API_KEY oder Seitenleiste.
Anbieter: Gemini (Batch und Hintergrund) oder OpenAI (nur Batch, Responses-Endpunkt), gewählt in der Seitenleiste.
Modi:     Batch (asynchron, 50 % Rabatt) oder Hintergrund (nur Gemini: Interactions API mit background=true, Long Decode
          bis 1.048.576 Ausgabe-Token, läuft bei Google und braucht die App nicht, Standardpreis).
Ordner:   conf/ (Zugangsdaten, geheim: credentials.json, token.json) und data/ (batch_jobs.json = Verlauf und
          Ergebnisse, pdf_files.json und openai_files.json = hochgeladene PDFs, requests_*.jsonl = gesendete
          Batch-Anfragen).
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
from aibui.config import (BATCH_MAX_OUT, BG_DEFAULT_OUT, BG_MAX_OUT, DEFAULT_MODEL, DEFAULT_NAME_MODEL,
                          DEFAULT_NAME_THINK, DEFAULT_OPENAI_MODEL, DONE, FORM_KEYS, HINT, MAX_POLL_ERRORS, MODE_BATCH,
                          MODE_BG, NAME_SOURCE_CHARS, NAME_THINK_LEVELS, OPENAI_EFFORTS, OPENAI_MAX_OUT, POLL_SECONDS,
                          PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDERS, SEPARATOR, TABS, TALK_NEW, THINK_LEVELS,
                          prepare_folders)
from aibui.drive import drive_fetch, drive_id, drive_service
from aibui.forms import delete_entry, entry_label, generate_title, reuse_inputs, save_details
from aibui.gemini import start_batch, upload_pdf
from aibui.history import load_jobs, migrate_history, mutate_jobs, runtime
from aibui.naming import choose_label, default_label, search_jobs
from aibui.openai_batch import start_openai_batch, upload_pdf_openai
from aibui.providers import batch_info, entry_mode, entry_provider, make_client
from aibui.talk import entry_group, parse_conversation
from aibui.views import job_panel

st.set_page_config(page_title="AI Batch UI", layout="wide")

moved = prepare_folders()
if moved:
    print("Dateien einsortiert:", ", ".join(moved))
    st.toast("Dateien einsortiert: " + ", ".join(moved))
if "history_checked" not in st.session_state:  # einmal je Sitzung: ältere Einträge bekommen das Pflichtfeld provider
    st.session_state["history_checked"] = True
    try:
        added = migrate_history(runtime().lock)
    except Exception as e:  # nichts bricht ab: Ohne das Feld gilt ein Eintrag als Gemini-Eintrag (entry_provider)
        added = 0
        print(f"Verlauf nicht aktualisiert: {e}")
        st.warning(f"Der Verlauf (data/batch_jobs.json) ließ sich nicht aktualisieren: {e}. Die App läuft trotzdem, "
                   "ältere Einträge gelten als Gemini-Einträge. Die Seite neu zu laden versucht es erneut.")
    if added:
        note = f"Verlauf aktualisiert: Pflichtfeld provider ({PROVIDER_GEMINI}) bei älteren Einträgen ergänzt ({added})"
        print(note)
        st.toast(note + ".")
for key in FORM_KEYS:  # hält die Werte am Leben und schickt sie beim erneuten Zeichnen an den Browser
    if key in st.session_state:
        st.session_state[key] = st.session_state[key]
with st.sidebar:
    provider = st.radio("Anbieter für neue Anfragen", PROVIDERS, key="provider", horizontal=True,
                        help="Jeder Eintrag im Tab „Jobs und Ergebnisse“ gehört zu seinem Anbieter und wird mit "
                             "dessen API-Key abgefragt. Beide Keys dürfen deshalb eingetragen bleiben.")
    keys = {PROVIDER_GEMINI: st.text_input("Gemini API-Key", os.getenv("GEMINI_API_KEY", ""), type="password"),
            PROVIDER_OPENAI: st.text_input("OpenAI API-Key", os.getenv("OPENAI_API_KEY", ""), type="password")}
    if provider == PROVIDER_OPENAI:
        st.session_state.setdefault("model_openai", DEFAULT_OPENAI_MODEL)
        model = st.text_input("Modell", key="model_openai",
                              help="Modellname laut OpenAI, zum Beispiel gpt-6-astra, gpt-6.1-sol oder gpt-6-luna. "
                                   "Das Modell muss die Batch API und PDF-Eingaben unterstützen.")
    else:
        st.session_state.setdefault("model_gemini", DEFAULT_MODEL)
        model = st.text_input("Modell", key="model_gemini")
    with st.expander("Namen der Einträge"):
        st.session_state.setdefault("auto_name", True)
        st.session_state.setdefault("name_model", DEFAULT_NAME_MODEL)
        st.session_state.setdefault("name_think", DEFAULT_NAME_THINK)
        auto_name = st.checkbox(
            "Name aus dem Prompt erzeugen", key="auto_name",
            help="Ist das Feld „Name“ in „Neue Anfrage“ leer, erzeugt ein kleines Gemini-Modell den Namen aus dem "
                 "Anfang der Prompts, ähnlich den Titeln im Verlauf eines Chatbots. Dafür geht ein Auszug der Prompts "
                 f"(höchstens {NAME_SOURCE_CHARS} Zeichen, nie die PDFs) an Google, auch wenn der Lauf selbst bei "
                 "OpenAI läuft. Ohne Gemini API-Key oder bei einem Fehler gilt der Standardname.")
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
    env_name = "OPENAI_API_KEY" if provider == PROVIDER_OPENAI else "GEMINI_API_KEY"
    st.info(f"Trage links deinen {provider} API-Key ein oder setze die Umgebungsvariable {env_name}.")
    st.stop()


def client_for(p):
    """Client des Anbieters p, oder None, wenn dessen API-Key fehlt."""
    return make_client(p, keys[p]) if keys[p] else None


try:
    client = client_for(provider)
except RuntimeError as e:  # z. B. das Paket openai fehlt
    st.error(f"Der {provider}-Client lässt sich nicht erstellen: {e}")
    st.stop()


def gemini_client():
    """Gemini-Client für die Namen: der Client des Laufs, bei OpenAI ein eigener (None ohne Gemini API-Key)."""
    return client if provider == PROVIDER_GEMINI else client_for(PROVIDER_GEMINI)


rt = runtime()

tab_new, tab_jobs = st.tabs(TABS, key="view", on_change="rerun")  # .open sagt, welcher Tab offen ist
on_jobs_tab = tab_jobs.open

with tab_new:
    note = st.session_state.pop("reused_note", None)
    if note:
        st.info(note)
    if provider == PROVIDER_OPENAI:
        mode = MODE_BATCH
        st.caption("Mit OpenAI läuft nur der Batch-Modus (50 % Rabatt, Ergebnis innerhalb von 24 Stunden). "
                   "Der Modus „Hintergrund“ ist Gemini vorbehalten.")
    else:
        mode = st.radio("Modus", [MODE_BATCH, MODE_BG], horizontal=True, key="mode")
    bg = mode == MODE_BG
    uploads = st.file_uploader("PDF-Dateien (mehrere möglich)", type="pdf", accept_multiple_files=True)
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
    pdf_order = [f.name for f in uploads] + chosen + [f"Drive-Datei {ref[:6]}" for ref in pasted]
    if pdf_order:
        st.caption("Reihenfolge der PDFs in jeder Anfrage: "
                   + ", ".join(f"{k}. {n}" for k, n in enumerate(pdf_order, 1))
                   + " (hochgeladene Dateien zuerst, dann Drive). Gleiche Dateien werden nur einmal gesendet.")
    else:
        st.caption("Kein PDF angehängt: Die Prompts werden ohne PDF gesendet.")

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
                   "Der Start ist gesperrt, bis dort Text steht.")
    c1, c2, c3 = st.columns(3)
    if provider == PROVIDER_OPENAI:
        st.session_state.setdefault("effort", "Standard")
        think = c1.selectbox("Denktiefe", OPENAI_EFFORTS, key="effort",
                             help="reasoning.effort der Responses API. „Standard“ sendet nichts, dann gilt die "
                                  "Voreinstellung des Modells. Welche Stufen ein Modell kennt, hängt vom Modell ab "
                                  "(z. B. kennt gpt-6-astra kein „none“). Andere Stufen lehnt die API ab, "
                                  "der Fehler steht dann im Ergebnis.")
    else:
        st.session_state.setdefault("think", "high")
        think = c1.selectbox("Denktiefe", THINK_LEVELS, key="think")
    if provider == PROVIDER_OPENAI:
        st.session_state.setdefault("max_openai", 32768)
        max_out = c2.number_input("Max. Ausgabe-Token", min_value=256, max_value=OPENAI_MAX_OUT, step=1024,
                                  key="max_openai",
                                  help="max_output_tokens. Denk-Token zählen zum Limit. Das Maximum hängt vom "
                                       "Modell ab (bei den aktuellen Modellen bis 128.000).")
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
    kind = "openai" if provider == PROVIDER_OPENAI else "background" if bg else "batch"
    naming_on = auto_name and bool(keys[PROVIDER_GEMINI])  # sonst gilt der Standardname
    label = c3.text_input("Name", key="label_" + kind,
                          placeholder="automatisch aus dem Prompt" if naming_on else default_label(kind),
                          help="Leer lassen: Der Name wird aus dem Prompt erzeugt (Seitenleiste „Namen der Einträge“), "
                               "sonst gilt der Standardname. Im Tab „Jobs und Ergebnisse“ lassen sich Name und "
                               "Beschreibung später ändern.")
    if naming_on and provider == PROVIDER_OPENAI and not label.strip():
        st.caption(f"Der Name wird mit Gemini erzeugt: Ein Auszug der Prompts (höchstens {NAME_SOURCE_CHARS} Zeichen, "
                   "ohne PDFs) geht dafür an Google, auch bei einem OpenAI-Lauf. Abschalten: Seitenleiste, "
                   "„Namen der Einträge“.")
    if bg:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Jeder Prompt läuft als Hintergrund-Interaktion bei Google (Interactions "
            "API, background=true), alle gleichzeitig. Long Decode setzt die Antwort über 65.536 Token hinaus fort "
            "(bis 1.048.576 Token minus Eingabe). Die App muss nicht laufen, sie fragt nur den Stand ab. Es gilt der "
            "Standardpreis statt des Batch-Rabatts, und weil alle Prompts gleichzeitig starten, ist ein Cache-Treffer "
            "für das PDF nicht garantiert. Gespräche mit mehreren Prompts gibt es hier nicht (je Prompt eine "
            "Interaktion), eine Fortsetzung steckt im Prompt."
        )
    elif provider == PROVIDER_OPENAI:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Die OpenAI Batch API kostet 50 % des Standardpreises und liefert die "
            "Ergebnisse innerhalb von 24 Stunden. Die PDFs stehen in jeder Anfrage an erster Stelle, damit der "
            "Prefix für das automatische Caching (ab 1.024 Token) identisch ist. Treffer siehst du unter "
            "„Jobs und Ergebnisse“."
        )
    else:
        st.caption(
            f"{len(prompts)} Prompt(s) erkannt. Batch kostet 50 % des Standardpreises. Carbon unterstützt nur "
            "implizites Caching (ab 4.096 Token, ohne Rabattgarantie): Die PDFs stehen in jeder Anfrage an erster "
            "Stelle, damit der Prefix identisch ist. Treffer siehst du unter „Jobs und Ergebnisse“."
        )

    if st.button("Im Hintergrund starten" if bg else "Batch starten", type="primary",
                 disabled=not prompts or bool(unfinished)):
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
                names, pdfs = [n for n, _ in unique], []
                for k, (fname, data) in enumerate(unique, 1):
                    status.update(label=f"Lade PDF {k} von {len(unique)} zu {provider} hoch …" + HINT)
                    pdfs.append((upload_pdf_openai if provider == PROVIDER_OPENAI else upload_pdf)(client, fname, data))
                if naming_on and not label.strip():
                    status.update(label="Erzeuge den Namen …" + HINT)
                title, generated, name_error = choose_label(label, kind, prompts, gemini_client, name_model, name_think,
                                                            auto_name)
                status.update(label="Starte …" + HINT)
                if bg:
                    entry = start_background(client, rt, model, pdfs, names, prompts, system.strip(), think, max_out,
                                             title)
                elif provider == PROVIDER_OPENAI:
                    batch_id, keyed = start_openai_batch(client, model, [f.id for f in pdfs], prompts, system.strip(),
                                                         think, max_out, title)
                    entry = {"name": batch_id, "provider": PROVIDER_OPENAI, "label": title, "model": model,
                             "pdf": ", ".join(names) or None, "pdfs": names, "prompts": keyed, "system": system.strip(),
                             "think": think, "max_out": int(max_out),
                             "created": datetime.now().isoformat(timespec="seconds")}
                    mutate_jobs(rt.lock, lambda jobs: jobs.insert(0, entry))
                else:
                    job, keyed = start_batch(client, model, pdfs, prompts, system.strip(), think, max_out, title)
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
    query = st.text_input("Suche", key="jobs_search", placeholder="Name, Beschreibung, Prompt, PDF oder ID",
                          help="Zeigt nur Einträge, in denen alle Suchwörter vorkommen (Groß- und Kleinschreibung "
                               "egal). Durchsucht werden Name, Beschreibung, ID, PDF-Namen und Prompts."
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
                    else "Batch (OpenAI)" if entry_prov == PROVIDER_OPENAI else "Batch")
        st.caption(f"{j['name']}, {kind_txt}, gesendet: Modell {j['model']}, "
                   f"Denktiefe {j.get('think', 'unbekannt')}, max. {j.get('max_out', '?')} Ausgabe-Token, "
                   f"PDF: {j['pdf'] or 'keins'}, {len(j['prompts'])} Prompt(s)")
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
