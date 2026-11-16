"""Hilfsfunktionen für die Tests (keine Tests hier)."""
import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
APP_PATH = SRC_DIR / "ai_batch_ui.py"  # Hauptskript: nur die Oberfläche
PACKAGE = "aibui"  # die Logik ohne Oberfläche, nach Thema in Module geteilt
PACKAGE_DIR = SRC_DIR / PACKAGE
SOURCE_FILES = [APP_PATH, *sorted(PACKAGE_DIR.glob("*.py"))]  # aller Quelltext der App

# Texte der Oberfläche, auf die sich Tests stützen. test_logic prüft, dass sie mit der App übereinstimmen.
PROVIDER_GEMINI, PROVIDER_OPENAI = "Gemini", "OpenAI"
MODE_BATCH = "Batch (50 % Rabatt, Ergebnis nach Minuten bis Stunden)"
MODE_BG = "Hintergrund (Long Decode, läuft bei Google, Standardpreis)"
TAB_NEW, TAB_JOBS = "Neue Anfrage", "Jobs und Ergebnisse"


# ---------- Verlauf ----------
def history_path(home):
    return Path(home) / "data" / "batch_jobs.json"


def read_history(home):
    path = history_path(home)
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def write_history(home, entries):
    path = history_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False), "utf-8")


def row(**over):
    r = {"key": "prompt-1", "prompt": "Eins", "text": "Gesicherte Antwort", "model": "gemini-4-carbon",
         "finish": "STOP", "usage": {}, "error": None, "in": 10, "cached": 0, "think": 1, "out": 1}
    r.update(over)
    return r


def batch_entry(**over):
    """Frisch gestarteter Batch (noch ohne Endzustand), im Format von vor Issue #8: ohne das Pflichtfeld provider, das
    die App beim Start ergänzt (migrate_history). Ein neuer Eintrag: batch_entry(provider=PROVIDER_GEMINI)."""
    e = {"name": "batches/abc123def456", "label": "altbatch", "model": "gemini-4-carbon", "pdf": "a.pdf",
         "pdfs": ["a.pdf"], "prompts": {"prompt-1": "Eins"}, "system": "", "think": "high", "max_out": 32768,
         "created": "2026-10-19T14:38:00"}
    e.update(over)
    return e


def finished_batch(**over):
    """Batch mit lokal gesichertem Endergebnis."""
    return batch_entry(state="JOB_STATE_SUCCEEDED", rows=[row()], error=None, api_model="models/gemini-4-carbon",
                       **over)


def openai_entry(**over):
    """Frisch gestarteter OpenAI-Batch (noch ohne Endzustand)."""
    e = batch_entry(name="batch_abc123def456", provider=PROVIDER_OPENAI, label="openai-batch", model="gpt-6-astra")
    e.update(over)
    return e


def finished_openai_batch(**over):
    """OpenAI-Batch mit lokal gesichertem Endergebnis."""
    return openai_entry(state="completed", rows=[row(model="gpt-6-astra-2026-09-01")], error=None,
                        api_model="gpt-6-astra-2026-09-01", **over)


def sync_entry(**over):
    """Älterer synchroner Eintrag. Den Modus gibt es nicht mehr, der Eintrag bleibt aber lesbar."""
    e = {"name": "sync-20261002-120000-bbbb", "mode": "sync", "state": "DONE", "label": "paar-lauf",
         "model": "gemini-4-carbon", "pdf": "a.pdf, b.pdf", "pdfs": ["a.pdf", "b.pdf"],
         "prompts": {"prompt-1": "P1", "prompt-2": "P2"}, "system": "Sei kurz.", "think": "low", "max_out": 4096,
         "group": 2, "rows": [], "created": "2026-10-02T12:00:00"}
    e.update(over)
    return e


def background_entry(**over):
    """Frisch gestarteter Hintergrund-Eintrag (noch ohne Endzustand). Die IDs folgen dem Muster des Fake-Dienstes."""
    e = {"name": "bg-20261112-230000-cccc", "mode": "background", "label": "lang-lauf", "model": "gemini-4-carbon",
         "pdf": "a.pdf", "pdfs": ["a.pdf"], "prompts": {"prompt-1": "Eins", "prompt-2": "Zwei"}, "system": "",
         "think": "high", "max_out": 262144,
         "interactions": {"prompt-1": "v1_fake000001", "prompt-2": "v1_fake000002"},
         "created": "2026-11-12T23:00:00"}
    e.update(over)
    return e


def finished_background(**over):
    """Hintergrund-Eintrag mit lokal gesichertem Endergebnis (jedes Feld lässt sich überschreiben)."""
    e = {"state": "completed", "rows": [row(), row(key="prompt-2", prompt="Zwei")], "error": None,
         "api_model": "gemini-4-carbon"}
    e.update(over)
    return background_entry(**e)


# ---------- AppTest ----------
def new_app(tab=None):
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    if tab:
        at.session_state["view"] = tab
    return at


def new_openai_app(tab=None, auto_name=False):
    """Wie new_app(), aber mit OpenAI als Anbieter für neue Anfragen. Ein Gemini-Client wird dabei nie gebaut: Die
    Namensvergabe (sie nutzt immer Gemini) ist aus, außer ein Test schaltet sie mit auto_name=True ein."""
    at = new_app(tab)
    at.session_state["provider"] = PROVIDER_OPENAI
    at.session_state["auto_name"] = auto_name
    return at


def sent_to_browser(widget, expected):
    """Der Wert steht im Backend und geht beim Zeichnen mit set_value an den Browser."""
    assert widget.value == expected
    assert widget.proto.set_value is True, f"{widget.key}: Der Browser würde das Feld mit dem Standardwert aufbauen"


def captions(at):
    return [c.value for c in at.caption]


def markdown(at):
    return [m.value for m in at.markdown]


def button(at, label):
    found = [b for b in at.button if b.label == label]
    assert found, f"Button „{label}“ nicht gefunden. Vorhanden: {[b.label for b in at.button]}"
    return found[0]


def click(at, label):
    button(at, label).click()
    at.run()


def set_prompts(at, text):
    at.text_area(key="raw").set_value(text)
    at.run()
