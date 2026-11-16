"""Namen der Einträge: aus dem Prompt erzeugen (ein kleines, günstiges Gemini-Modell, ähnlich den Titeln im Verlauf
eines Chatbots), Standardname, Dateiname und Suche im Verlauf. Kein Streamlit-Aufruf in diesem Modul."""
import re
from datetime import datetime

from .config import (NAME_INSTRUCTION, NAME_MAX_CHARS, NAME_MAX_OUT, NAME_SOURCE_CHARS, NAME_SOURCE_PROMPTS,
                     NAME_TIMEOUT_MS)
from .talk import parse_conversation


def default_label(kind, now=None):
    """Standardname eines Eintrags: Art und Zeitpunkt des Starts, z. B. batch-20261115-0304."""
    return f"{kind}-{now or datetime.now():%Y%m%d-%H%M}"


def naming_source(prompts):
    """Text, aus dem das Modell den Namen bildet: der Anfang der ersten NAME_SOURCE_PROMPTS Prompts, zusammen
    höchstens NAME_SOURCE_CHARS Zeichen. Setzt ein Prompt ein früheres Gespräch fort, zählt nur der neue Prompt (der
    Verlauf davor würde den Namen verfälschen). Leer, wenn kein Text da ist."""
    texts = []
    for prompt in list(prompts)[:NAME_SOURCE_PROMPTS]:
        turns, own = parse_conversation(prompt)
        text = (own if turns else prompt).strip()
        if text:
            texts.append(text)
    share = NAME_SOURCE_CHARS // max(len(texts), 1)
    return "\n---\n".join(t[:share] for t in texts)


def clean_name(text):
    """Antwort des Modells als Name: nur die erste nichtleere Zeile, ohne Anführungszeichen, Markdown-Zeichen und
    Schlusspunkt, höchstens NAME_MAX_CHARS Zeichen (gekürzt an einer Wortgrenze, mit …). Leer, wenn nichts bleibt."""
    line = next((ln for ln in (text or "").splitlines() if ln.strip()), "")
    name = " ".join(line.split()).strip("#*_`\"'„“”‚‘’«»-–.:;, ")
    if len(name) > NAME_MAX_CHARS:
        name = name[:NAME_MAX_CHARS].rsplit(" ", 1)[0].rstrip("-–.:;, ") + "…"
    return name


def generate_name(client, prompts, model, think):
    """Name aus den Prompts erzeugen: ein kurzer, normaler Aufruf von generate_content (kein Batch) mit der Denktiefe
    think (sie wird immer gesendet, denn jedes Modell hat eine eigene Voreinstellung). Ohne Prompt-Text gibt es keinen
    Aufruf (Rückgabe ""). Fehler der API gehen nach oben."""
    source = naming_source(prompts)
    if not source:
        return ""
    response = client.models.generate_content(
        model=model, contents=source,
        config={"system_instruction": NAME_INSTRUCTION, "max_output_tokens": NAME_MAX_OUT,
                "thinking_config": {"thinking_level": think}, "http_options": {"timeout": NAME_TIMEOUT_MS}})
    return clean_name(response.text)


def choose_label(typed, kind, prompts, get_client, model, think, auto=True):
    """Name für einen neuen Eintrag als (Name, erzeugt, Fehlertext). Ein eingetippter Name gilt immer. Ist das Feld leer,
    erzeugt bei auto das Modell den Namen aus den Prompts, sonst oder wenn das scheitert gilt der Standardname.
    get_client() liefert den Gemini-Client, oder None ohne API-Key (dann gilt der Standardname ohne Fehlertext). Ein
    Fehler hier verhindert nie den Start: erzeugt ist dann False, der Fehlertext sagt warum."""
    typed = typed.strip()
    if typed:
        return typed, False, None
    fallback = default_label(kind)
    if not auto:
        return fallback, False, None
    try:
        client = get_client()
        if client is None:
            return fallback, False, None
        name = generate_name(client, prompts, model, think)
    except Exception as e:  # jeder Fehler der Namensvergabe: Standardname statt Abbruch
        return fallback, False, f"Der Name ließ sich nicht aus dem Prompt erzeugen ({e})."
    if not name:
        return fallback, False, "Das Modell hat keinen Namen geliefert."
    return name, True, None


def entry_text(x):
    """Alles, was die Suche durchsucht, klein geschrieben: Name, Beschreibung, ID, PDFs und Prompts eines Eintrags.
    Ältere Einträge ohne Beschreibung oder PDFs sind erlaubt."""
    parts = [x.get("label"), x.get("description"), x.get("name"), x.get("pdf"), *(x.get("prompts") or {}).values()]
    return "\n".join(str(p) for p in parts if p).casefold()


def matches(x, query):
    """Passt der Eintrag zur Suche? Jedes Wort der Suche muss vorkommen (Groß- und Kleinschreibung und Reihenfolge sind
    egal). Eine leere Suche passt auf jeden Eintrag."""
    text = entry_text(x)
    return all(word in text for word in query.casefold().split())


def search_jobs(jobs, query):
    """Die Einträge, die zur Suche passen, in der Reihenfolge des Verlaufs."""
    return [x for x in jobs if matches(x, query)]


def file_stem(label):
    """Dateiname (ohne Endung) zum Namen eines Eintrags: Zeichen, die Dateisysteme nicht erlauben, werden zu
    Bindestrichen. Erzeugte Namen können beliebige Zeichen enthalten."""
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", label).strip(" .-") or "ergebnisse"
