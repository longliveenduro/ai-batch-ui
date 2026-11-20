"""Anbieter (Gemini, OpenAI, Claude): Client bauen, Anbieter und Betriebsart eines Eintrags, Status holen und sichern,
Batch abbrechen. Hier kommt ein weiterer Anbieter dazu (siehe README, Abschnitt 9.2)."""
import streamlit as st
from google import genai

from .background import cancel_background, fetch_background
from .claude_batch import claude_client, fetch_claude_batch
from .config import DONE, PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI
from .history import mutate_jobs, runtime
from .openai_batch import fetch_openai_batch, openai_client
from .rows import parse_results


def make_client(provider, api_key):
    if provider == PROVIDER_OPENAI:
        return openai_client(api_key)
    if provider == PROVIDER_CLAUDE:
        return claude_client(api_key)
    return genai.Client(api_key=api_key)


def entry_provider(j):
    """Anbieter eines Eintrags. Das Feld provider ist Pflicht: Neue Einträge schreiben es immer. Einträge von vor
    Issue #8 haben es nicht (sie stammen alle von Gemini) und werden nicht nachträglich ergänzt. Fehlt es oder ist der
    Wert unbekannt, gilt der Eintrag als Gemini-Eintrag."""
    return j["provider"] if j.get("provider") in (PROVIDER_OPENAI, PROVIDER_CLAUDE) else PROVIDER_GEMINI


def entry_mode(j):
    """Betriebsart eines Eintrags: "background", "batch" oder "sync". Den synchronen Modus gibt es nicht mehr, ältere
    Einträge davon bleiben aber lesbar. Ältere Einträge haben kein Feld mode (Batch)."""
    return j["mode"] if j.get("mode") in ("sync", "background") else "batch"


def refresh(client, j):
    if entry_mode(j) == "background":  # Hintergrund-Interaktionen: beendete Zeilen der letzten Abfrage bleiben stehen
        known = (st.session_state.get("res:" + j["name"]) or {}).get("rows") or j.get("rows")
        state, rows, err, api_model = fetch_background(client, j, known)
    elif entry_provider(j) == PROVIDER_OPENAI:
        state, rows, err, api_model = fetch_openai_batch(client, j)
    elif entry_provider(j) == PROVIDER_CLAUDE:
        state, rows, err, api_model = fetch_claude_batch(client, j)
    else:
        job = client.batches.get(name=j["name"])
        state, rows = job.state.name, None
        if state == "JOB_STATE_SUCCEEDED" and job.dest and job.dest.file_name:
            rows = parse_results(client.files.download(file=job.dest.file_name), j["prompts"])
        err, api_model = (str(job.error) if job.error else None), job.model
    st.session_state["res:" + j["name"]] = {"state": state, "rows": rows, "error": err, "model": api_model}
    if state in DONE:  # Endergebnis lokal sichern: bleibt nach Ablauf beim Anbieter erhalten und lädt ohne Abruf
        def save(jobs):
            for x in jobs:
                if x["name"] == j["name"]:
                    x.update(state=state, rows=rows, error=err, api_model=api_model)
        mutate_jobs(runtime().lock, save)


def batch_info(j):
    """Stand eines Batches: aus der laufenden Sitzung, sonst aus der lokalen Sicherung des Endergebnisses."""
    info = st.session_state.get("res:" + j["name"])
    if info is None and j.get("state") in DONE:
        info = {"state": j["state"], "rows": j.get("rows"), "error": j.get("error"), "model": j.get("api_model")}
    return info


def cancel_batch(client, j):
    if entry_mode(j) == "background":
        cancel_background(client, j)
    elif entry_provider(j) == PROVIDER_OPENAI:
        client.batches.cancel(j["name"])
    elif entry_provider(j) == PROVIDER_CLAUDE:
        client.messages.batches.cancel(j["name"])
    else:
        client.batches.cancel(name=j["name"])
