"""Dateien als Eingabe (Issue #16): Welche Typen die App annimmt, mit welchem MIME-Typ jede Datei zum Anbieter geht und
welche Arten von Dateien welcher Anbieter kennt. Kein Streamlit-Aufruf und kein SDK in diesem Modul.

Der Typ einer Datei folgt aus ihrer Endung (FILE_TYPES), nicht aus dem, was der Browser meldet: Das ist auf jedem Rechner
gleich und ohne Zufall prüfbar. Die Art der Datei (document, image, audio, video) entscheidet, als welcher Teil sie in der
Anfrage steht. Textdateien (TEXT_EXTENSIONS) sind Dokumente mit dem MIME-Typ text/plain.
"""
from pathlib import PurePath

from .config import PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDERS

PDF_MIME = "application/pdf"
TEXT_EXTENSIONS = (".txt", ".text", ".md", ".markdown", ".rst", ".log", ".json", ".html", ".htm", ".xml", ".css", ".js",
                   ".py", ".sql", ".c", ".cpp", ".h", ".tsv", ".srt", ".vtt")
# Endung -> (Art, MIME-Typ). Die Dokumente und Bilder nehmen beide Anbieter an, Audio und Video nur Gemini
# (siehe PROVIDER_KINDS). Die MIME-Typen sind die, die Googles Files API und das SDK der Interactions API nennen.
FILE_TYPES = {
    ".pdf": ("document", PDF_MIME),
    ".docx": ("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".doc": ("document", "application/msword"),
    ".odt": ("document", "application/vnd.oasis.opendocument.text"),
    ".pptx": ("document", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ".ppt": ("document", "application/vnd.ms-powerpoint"),
    ".xlsx": ("document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".xls": ("document", "application/vnd.ms-excel"),
    ".csv": ("document", "text/csv"),
    **{ext: ("document", "text/plain") for ext in TEXT_EXTENSIONS},
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".mp3": ("audio", "audio/mp3"),
    ".wav": ("audio", "audio/wav"),
    ".m4a": ("audio", "audio/m4a"),
    ".aac": ("audio", "audio/aac"),
    ".ogg": ("audio", "audio/ogg"),
    ".flac": ("audio", "audio/flac"),
    ".aiff": ("audio", "audio/aiff"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/mov"),
    ".avi": ("video", "video/avi"),
    ".webm": ("video", "video/webm"),
    ".wmv": ("video", "video/wmv"),
    ".mpeg": ("video", "video/mpeg"),
    ".mpg": ("video", "video/mpeg"),
    ".3gp": ("video", "video/3gpp"),
}
# Welche Arten ein Anbieter annimmt. OpenAI nennt in der Doku zu Dateieingaben (Responses API) Dokumente, Text und Tabellen
# als input_file, Bilder gehen als input_image. Audio und Video kennt es dort nicht.
PROVIDER_KINDS = {
    PROVIDER_GEMINI: ("document", "image", "audio", "video"),
    PROVIDER_OPENAI: ("document", "image"),
}
KIND_LABELS = {"document": "Dokumente", "image": "Bilder", "audio": "Audio", "video": "Video"}


def file_info(name):
    """(Art, MIME-Typ) einer Datei nach ihrer Endung, Groß- und Kleinschreibung egal. ValueError, wenn die App den Typ
    nicht kennt (auch ohne Endung)."""
    ext = PurePath(name).suffix.lower()
    if ext in FILE_TYPES:
        return FILE_TYPES[ext]
    if not ext:
        raise ValueError(f"„{name}“: Ohne Endung lässt sich der Dateityp nicht erkennen.")
    raise ValueError(f"„{name}“: Der Dateityp {ext} wird nicht unterstützt.")


def check_files(provider, names):
    """Meldungen zu Dateien, die der Anbieter nicht annimmt, in der Reihenfolge der Namen. Eine leere Liste heißt: alles
    in Ordnung. Geprüft wird nur die Endung."""
    problems = []
    for name in names:
        try:
            kind, _ = file_info(name)
        except ValueError as e:
            problems.append(str(e))
            continue
        if kind not in PROVIDER_KINDS[provider]:
            accepted = ", ".join(p for p in PROVIDERS if kind in PROVIDER_KINDS[p])
            problems.append(f"„{name}“: {KIND_LABELS[kind]} nimmt {provider} nicht an, nur {accepted}.")
    return problems


def types_overview():
    """Alle Endungen nach Art, als Text für die Hilfe am Datei-Feld. Eine Art, die nicht jeder Anbieter annimmt, nennt
    die Anbieter, die sie annehmen."""
    parts = []
    for kind, label in KIND_LABELS.items():
        extensions = ", ".join(ext for ext, (k, _) in FILE_TYPES.items() if k == kind)
        accepted = [p for p in PROVIDERS if kind in PROVIDER_KINDS[p]]
        only = "" if len(accepted) == len(PROVIDERS) else f" (nur {', '.join(accepted)})"
        parts.append(f"{label}{only}: {extensions}")
    return "\n\n".join(parts)


def mime_kind(mime):
    """Art zu einem MIME-Typ: image, audio und video nach dem Anfang des Typs, alles andere ist ein document. Die Namen
    der Arten sind zugleich die Inhaltstypen der Interactions API."""
    major = (mime or "").split("/", 1)[0]
    return major if major in ("image", "audio", "video") else "document"


def file_mime(f):
    """MIME-Typ einer hochgeladenen Datei der Gemini Files API, so wie die API ihn führt. Fehlt er, gilt PDF: Bis Issue
    #16 war jede Datei eines."""
    return getattr(f, "mime_type", None) or PDF_MIME
