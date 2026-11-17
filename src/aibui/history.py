"""Verlauf der Läufe (data/batch_jobs.json). Batches und Hintergrund-Läufe laufen bis zu 24 h bei Google: daher
lokal gespeichert. Geschrieben wird nur über mutate_jobs(). Dazu gehört auch das Anpassen älterer Einträge beim Start:
das Ergänzen des Pflichtfelds provider (migrate_history()) und das Umbenennen der alten Standardnamen von
Hintergrund-Läufen (migrate_background_labels())."""
import json
import os
import re
import threading
import time
from types import SimpleNamespace

import streamlit as st

from .config import DATA_DIR, HISTORY, PROVIDER_GEMINI

# Standardname eines Hintergrund-Laufs bis Issue #32: background-<Datum>-<Uhrzeit> (seither background-gemini-…)
OLD_BACKGROUND_LABEL = re.compile(r"background-(?P<stamp>\d{8}-\d{4})")


@st.cache_resource(show_spinner=False)
def runtime():
    """Prozessweit geteilt: Sperre für den Verlauf (mehrere Sitzungen laufen in eigenen Threads)."""
    return SimpleNamespace(lock=threading.Lock())


def load_jobs():
    if not HISTORY.exists():
        return []
    try:
        return json.loads(HISTORY.read_text("utf-8"))
    except json.JSONDecodeError:  # beschädigte Datei sichern, statt die App abstürzen zu lassen
        HISTORY.rename(HISTORY.with_name(f"batch_jobs.defekt-{int(time.time())}.json"))
        return []


def mutate_jobs(lock, change):
    """Verlauf unter Sperre lesen, mit change(jobs) ändern und atomar zurückschreiben (auch aus Threads nutzbar)."""
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        jobs = load_jobs()
        change(jobs)
        tmp = HISTORY.with_suffix(".tmp")
        tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, HISTORY)


def lacks_provider(j):
    """Fehlt dem Eintrag das Pflichtfeld provider (leer zählt als fehlend)? Das betrifft nur Einträge von vor Issue #8,
    und die stammen alle von Gemini: Bei OpenAI-Einträgen gab es das Feld von Anfang an."""
    return isinstance(j, dict) and not j.get("provider")


def migrate_history(lock):
    """Beim Start: ältere Einträge ohne provider bekommen provider = Gemini. Geschrieben wird nur, wenn so ein Eintrag
    da ist (über mutate_jobs, unter der Sperre). Andere Werte bleiben unberührt. Gibt zurück, wie viele Einträge
    ergänzt wurden."""
    jobs = load_jobs()
    if not isinstance(jobs, list) or not any(lacks_provider(j) for j in jobs):
        return 0
    added = []

    def change(fresh):
        for j in fresh:
            if lacks_provider(j):
                j["provider"] = PROVIDER_GEMINI
                added.append(j)

    mutate_jobs(lock, change)
    return len(added)


def new_background_label(j):
    """Neuer Name eines Hintergrund-Eintrags, der noch den alten Standardnamen background-<Datum>-<Uhrzeit> trägt:
    background-gemini-<Datum>-<Uhrzeit> (Issue #32). Sonst None. Eingetippte und aus dem Prompt erzeugte Namen passen
    nicht zum Muster und bleiben, ebenso Einträge anderer Betriebsarten."""
    if not isinstance(j, dict) or j.get("mode") != "background" or not isinstance(j.get("label"), str):
        return None
    match = OLD_BACKGROUND_LABEL.fullmatch(j["label"])
    return f"background-gemini-{match['stamp']}" if match else None


def migrate_background_labels(lock):
    """Beim Start: Hintergrund-Einträge mit dem alten Standardnamen background-<Datum>-<Uhrzeit> heißen danach
    background-gemini-<Datum>-<Uhrzeit>. Geschrieben wird nur, wenn so ein Eintrag da ist (über mutate_jobs, unter der
    Sperre), und nur das Feld label ändert sich. Der Name bleibt lokal: Bei einem Hintergrund-Lauf geht er nicht an
    Google. Gibt zurück, wie viele Einträge umbenannt wurden."""
    jobs = load_jobs()
    if not isinstance(jobs, list) or not any(new_background_label(j) for j in jobs):
        return 0
    renamed = []

    def change(fresh):
        for j in fresh:
            label = new_background_label(j)
            if label:
                j["label"] = label
                renamed.append(j)

    mutate_jobs(lock, change)
    return len(renamed)
