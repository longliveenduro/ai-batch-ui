"""Formular „Neue Anfrage“ und Verlaufseinträge: Beschriftung und Callbacks (Eingaben übernehmen, Gespräch
fortsetzen, Name und Beschreibung ändern, Eintrag löschen). Callbacks setzen Widget-Werte, bevor das Widget im Lauf
erzeugt wird."""
import streamlit as st

from .config import (BATCH_MAX_OUT, BG_MAX_OUT, MODE_BATCH, MODE_BG, OPENAI_EFFORTS, OPENAI_MAX_OUT, PROVIDER_OPENAI,
                     TABS, TALK_NEW, THINK_LEVELS)
from .history import mutate_jobs, runtime
from .naming import generate_name, matches
from .providers import entry_mode, entry_provider
from .talk import conversation_text


def entry_label(x):
    return f"{x['label']} ({x['created'][:16].replace('T', ' ')}) {x['name'][-6:]}"


def fill_form(j, raw, text):
    """Callback-Hilfe: Formular „Neue Anfrage“ mit dem Prompt-Text raw und den Einstellungen eines Eintrags füllen
    und zu dem Tab wechseln. text beginnt den einmaligen Hinweis. Nur aus Callbacks aufrufen (Widget-Werte lassen
    sich nur setzen, bevor das Widget im Lauf erzeugt wurde). Einträge des entfernten synchronen Modus landen im
    Modus „Hintergrund“: Er läuft wie sie zum Standardpreis und kennt Long Decode."""
    ss, mode, prov = st.session_state, entry_mode(j), entry_provider(j)
    background = mode in ("background", "sync")
    ss["provider"] = prov
    if j.get("model"):
        ss["model_openai" if prov == PROVIDER_OPENAI else "model_gemini"] = j["model"]
    ss["mode"] = MODE_BG if background else MODE_BATCH
    ss["raw"] = raw
    ss["system"] = j.get("system", "")
    if prov == PROVIDER_OPENAI:
        if j.get("think") in OPENAI_EFFORTS:
            ss["effort"] = j["think"]
        if j.get("max_out"):
            ss["max_openai"] = max(256, min(int(j["max_out"]), OPENAI_MAX_OUT))
    else:
        if j.get("think") in THINK_LEVELS:
            ss["think"] = j["think"]
        if j.get("max_out"):
            cap, field = (BG_MAX_OUT, "max_bg") if background else (BATCH_MAX_OUT, "max_batch")
            ss[field] = max(256, min(int(j["max_out"]), cap))
    pdfs = j.get("pdf")
    note = text
    if mode == "sync":
        note += (" Den synchronen Modus gibt es nicht mehr: Die Eingaben stehen im Modus „Hintergrund“ bereit, "
                 "jeder Prompt läuft dort für sich.")
    if pdfs:
        note += f" Bitte die PDFs erneut anhängen: {pdfs}. Schon hochgeladene Dateien werden wiederverwendet."
    ss["reused_note"] = note
    ss["view"] = TABS[0]  # wechselt zum Tab „Neue Anfrage“


def reuse_inputs(j):
    """Callback: Prompts und Einstellungen eines Eintrags ins Formular „Neue Anfrage“ übernehmen."""
    fill_form(j, "\n---\n".join(j["prompts"].values()), f"Eingaben aus „{j['label']}“ übernommen.")


def continue_conversation(j, turns):
    """Callback: Gesprächsverlauf (turns, siehe history_turns) als Text ins Formular übernehmen. Darunter schreibt man
    den neuen Prompt. Der Verlauf steckt im Prompt selbst."""
    fill_form(j, conversation_text(turns),
              f"Gespräch aus „{j['label']}“ fortgesetzt: {len(turns)} Runde(n) Verlauf stehen im Prompt. "
              f"Schreibe deinen neuen Prompt unter „{TALK_NEW}“.")


def delete_entry(name):
    """Callback: Eintrag samt lokal gesicherter Ergebnisse aus dem Verlauf entfernen (beim Anbieter bleibt alles)."""
    def change(jobs):
        jobs[:] = [x for x in jobs if x["name"] != name]
    mutate_jobs(runtime().lock, change)
    for prefix in ("res:", "err:", "errn:"):
        st.session_state.pop(prefix + name, None)
    st.session_state.pop("sel", None)


def keep_visible(entry):
    """Callback-Hilfe: den Eintrag (mit seinem neuen Namen) im Jobs-Tab auswählen. Passt er nicht mehr zur Suche, wird
    die Suche geleert, damit er sichtbar bleibt und nicht ein anderer Eintrag an seine Stelle rückt."""
    ss = st.session_state
    ss["sel"] = entry_label(entry)
    if not matches(entry, ss.get("jobs_search") or ""):
        ss["jobs_search"] = ""


def update_entry(name, **fields):
    """Felder eines Eintrags im Verlauf ändern (unter Sperre, auf dem frischen Stand der Datei)."""
    def change(jobs):
        for x in jobs:
            if x["name"] == name:
                x.update(fields)
    mutate_jobs(runtime().lock, change)


def save_details(j):
    """Callback: Name und Beschreibung aus den Feldern im Popover „Name und Beschreibung“ im Eintrag speichern. Ein
    leerer Name behält den bisherigen, die Beschreibung darf leer sein."""
    ss = st.session_state
    title = " ".join((ss.get("title:" + j["name"]) or "").split()) or j["label"]
    description = (ss.get("descr:" + j["name"]) or "").strip()
    update_entry(j["name"], label=title, description=description)
    ss["title:" + j["name"]] = title
    keep_visible({**j, "label": title, "description": description})


def generate_title(j, get_client, model, think):
    """Callback: Name des Eintrags aus seinen Prompts erzeugen (wie beim Start) und speichern. get_client() liefert den
    Gemini-Client. Scheitert es, steht der Grund als einmaliger Hinweis (name_note) im Jobs-Tab, der Name bleibt."""
    ss = st.session_state
    try:
        client = get_client()
        if client is None:
            raise RuntimeError("Der Gemini API-Key fehlt (Seitenleiste).")
        title = generate_name(client, list(j["prompts"].values()), model, think)
        if not title:
            raise RuntimeError("Das Modell hat keinen Namen geliefert.")
    except Exception as e:  # jeder Fehler wird gemeldet, nichts bricht ab
        ss["name_note"] = f"Der Name ließ sich nicht aus dem Prompt erzeugen: {e}"
        return
    update_entry(j["name"], label=title)
    ss["title:" + j["name"]] = title
    keep_visible({**j, "label": title})
