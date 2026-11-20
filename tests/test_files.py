"""Tests der erlaubten Dateitypen (Issue #16): Art und MIME-Typ je Endung, Prüfung je Anbieter, Hilfetext. Reine Logik,
ohne Oberfläche und ohne Ersatzdienste. Wie Upload und Anfragen die Typen nutzen, steht in test_logic, test_openai und
test_background, die Oberfläche in test_ui."""
import typing
from types import SimpleNamespace

import pytest

from helpers import PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI


# ---------- Typ einer Datei ----------
@pytest.mark.parametrize("name, kind, mime", [
    ("buch.pdf", "document", "application/pdf"),
    ("bericht.docx", "document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("alt.doc", "document", "application/msword"),
    ("folien.pptx", "document", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ("zahlen.xlsx", "document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("tabelle.csv", "document", "text/csv"),
    ("notiz.txt", "document", "text/plain"),
    ("README.md", "document", "text/plain"),
    ("daten.json", "document", "text/plain"),
    ("skript.py", "document", "text/plain"),
    ("foto.png", "image", "image/png"),
    ("foto.jpg", "image", "image/jpeg"),
    ("foto.jpeg", "image", "image/jpeg"),
    ("foto.webp", "image", "image/webp"),
    ("ton.mp3", "audio", "audio/mp3"),
    ("ton.wav", "audio", "audio/wav"),
    ("film.mp4", "video", "video/mp4"),
    ("film.mov", "video", "video/mov"),
    ("film.mpg", "video", "video/mpeg"),
    ("film.3gp", "video", "video/3gpp"),
])
def test_file_info_reads_kind_and_mime_type_from_the_extension(app, name, kind, mime):
    assert app.file_info(name) == (kind, mime)


def test_file_info_ignores_the_case_and_looks_only_at_the_last_extension(app):
    assert app.file_info("Scan.PDF") == app.file_info("scan.pdf") == ("document", "application/pdf")
    assert app.file_info("Bericht.Final.v2.DOCX")[0] == "document"
    assert app.file_info("archiv.zip.png") == ("image", "image/png")  # maßgeblich ist die letzte Endung


@pytest.mark.parametrize("name, message", [
    ("archiv.zip", "„archiv.zip“: Der Dateityp .zip wird nicht unterstützt."),
    ("programm.EXE", "„programm.EXE“: Der Dateityp .exe wird nicht unterstützt."),
    ("LIESMICH", "„LIESMICH“: Ohne Endung lässt sich der Dateityp nicht erkennen."),
    (".gitignore", "„.gitignore“: Ohne Endung lässt sich der Dateityp nicht erkennen."),
    ("foto.png.zip", "„foto.png.zip“: Der Dateityp .zip wird nicht unterstützt."),
])
def test_file_info_names_the_file_and_the_problem_for_an_unknown_type(app, name, message):
    with pytest.raises(ValueError) as e:
        app.file_info(name)
    assert str(e.value) == message


def test_every_entry_of_the_table_is_well_formed(app):
    for ext, (kind, mime) in app.FILE_TYPES.items():
        assert ext.startswith(".") and ext == ext.lower() and ext.count(".") == 1, ext
        assert kind in app.KIND_LABELS, f"{ext}: unbekannte Art {kind}"
        # Die Art folgt aus dem MIME-Typ: So wird sie in der Interactions API zum Inhaltstyp (siehe input_part)
        assert app.mime_kind(mime) == kind, f"{ext}: {mime} passt nicht zur Art {kind}"
    assert {kind for kind, _ in app.FILE_TYPES.values()} == set(app.KIND_LABELS)  # jede Art hat Endungen


def test_text_files_are_documents_with_a_plain_text_mime_type(app):
    for ext in app.TEXT_EXTENSIONS:
        assert app.FILE_TYPES[ext] == ("document", "text/plain"), ext
    assert {".txt", ".md", ".json", ".html", ".xml", ".py"} <= set(app.TEXT_EXTENSIONS)


def test_the_mime_types_are_ones_the_sdk_of_the_interactions_api_knows(app):
    """Gleicht die MIME-Typen mit den Aufzählungen im SDK ab, damit ein Tippfehler (etwa image/jpg) auffällt. Bei
    Dokumenten kennt das SDK text/plain nicht, es nimmt aber auch andere Werte an (offene Aufzählung)."""
    from google.genai import interactions
    names = {"document": "DocumentContentMimeType", "image": "ImageContentMimeType", "audio": "AudioContentMimeType",
             "video": "VideoContentMimeType"}
    known = {}
    for kind, name in names.items():
        if not hasattr(interactions, name):
            pytest.skip(f"Dieses SDK kennt {name} nicht")
        known[kind] = set(typing.get_args(typing.get_args(getattr(interactions, name))[0]))
    known["document"] |= {"text/plain"}
    unknown = sorted(f"{ext}: {mime}" for ext, (kind, mime) in app.FILE_TYPES.items() if mime not in known[kind])
    assert not unknown, f"Diese MIME-Typen stehen nicht in den Aufzählungen des SDK: {unknown}"


# ---------- Arten je Anbieter ----------
def test_all_providers_take_documents_and_images_but_only_gemini_takes_audio_and_video(app):
    assert set(app.PROVIDER_KINDS) == {PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE} == set(app.PROVIDERS)
    assert set(app.PROVIDER_KINDS[PROVIDER_GEMINI]) == {"document", "image", "audio", "video"}
    assert set(app.PROVIDER_KINDS[PROVIDER_OPENAI]) == {"document", "image"}
    assert set(app.PROVIDER_KINDS[PROVIDER_CLAUDE]) == {"document", "image"}


def test_check_files_accepts_everything_the_provider_knows(app):
    names = ["a.pdf", "b.DOCX", "c.xlsx", "d.md", "e.PNG", "f.webp"]
    assert app.check_files(PROVIDER_GEMINI, names) == [] and app.check_files(PROVIDER_OPENAI, names) == []
    assert app.check_files(PROVIDER_GEMINI, ["g.mp3", "h.mp4"]) == []  # Gemini nimmt Audio und Video an
    assert app.check_files(PROVIDER_OPENAI, []) == []


def test_check_files_reports_audio_and_video_for_openai_and_names_who_takes_them(app):
    assert app.check_files(PROVIDER_OPENAI, ["ton.mp3", "film.MP4"]) == [
        "„ton.mp3“: Audio nimmt OpenAI nicht an, nur Gemini.",
        "„film.MP4“: Video nimmt OpenAI nicht an, nur Gemini."]


@pytest.mark.parametrize("provider", [PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE])
def test_check_files_reports_unknown_types_for_every_provider_in_the_order_of_the_files(app, provider):
    problems = app.check_files(provider, ["a.pdf", "b.zip", "c.png", "LIESMICH"])
    assert problems == ["„b.zip“: Der Dateityp .zip wird nicht unterstützt.",
                        "„LIESMICH“: Ohne Endung lässt sich der Dateityp nicht erkennen."]


# ---------- Claude: nur PDF, Text und Bilder ----------
def test_check_files_accepts_pdf_text_csv_and_images_for_claude(app):
    assert app.check_files(PROVIDER_CLAUDE, ["a.pdf", "b.TXT", "c.md", "d.csv", "e.json", "f.PNG", "g.jpg", "h.webp"]) == []
    assert app.check_files(PROVIDER_CLAUDE, []) == []


def test_check_files_rejects_office_files_for_claude_with_a_hint_to_export_them(app):
    names = ["bericht.docx", "alt.DOC", "text.odt", "folien.pptx", "alt.ppt", "zahlen.xlsx", "alt.xls"]
    problems = app.check_files(PROVIDER_CLAUDE, names)
    assert len(problems) == 7 and all("nimmt Claude nicht an" in p and "PDF" in p for p in problems)
    assert problems[0] == ("„bericht.docx“: .docx-Dateien nimmt Claude nicht an, nur PDF, Text (auch CSV) und Bilder. "
                           "Exportiere sie als PDF (Tabellen als CSV).")
    assert problems[1].startswith("„alt.DOC“: .doc-Dateien")  # Groß- und Kleinschreibung egal, Endung klein genannt


def test_the_same_office_files_stay_fine_for_gemini_and_openai(app):
    names = ["bericht.docx", "alt.doc", "text.odt", "folien.pptx", "alt.ppt", "zahlen.xlsx", "alt.xls"]
    assert app.check_files(PROVIDER_GEMINI, names) == [] and app.check_files(PROVIDER_OPENAI, names) == []


def test_check_files_reports_audio_and_video_for_claude_and_names_who_takes_them(app):
    assert app.check_files(PROVIDER_CLAUDE, ["ton.mp3", "film.MP4"]) == [
        "„ton.mp3“: Audio nimmt Claude nicht an, nur Gemini.",
        "„film.MP4“: Video nimmt Claude nicht an, nur Gemini."]


def test_check_files_for_claude_keeps_the_order_of_all_kinds_of_problems(app):
    assert [p.split("“")[0] for p in app.check_files(
        PROVIDER_CLAUDE, ["a.pdf", "b.xlsx", "c.zip", "d.mp3", "e.png"])] == ["„b.xlsx", "„c.zip", "„d.mp3"]


def test_excluded_extensions_are_documents_the_app_knows_otherwise(app):
    assert app.PROVIDER_EXCLUDED == {PROVIDER_CLAUDE: app.OFFICE_EXTENSIONS}
    assert all(app.file_info("x" + ext)[0] == "document" for ext in app.OFFICE_EXTENSIONS)
    assert app.excluded_problem(PROVIDER_CLAUDE, "x.pdf") is None
    assert app.excluded_problem(PROVIDER_OPENAI, "x.docx") is None


# ---------- Hilfetext ----------
def test_the_overview_lists_every_extension_and_names_the_provider_of_limited_kinds(app):
    text = app.types_overview()
    assert all(ext in text for ext in app.FILE_TYPES)
    assert "Audio (nur Gemini): .mp3" in text and "Video (nur Gemini): .mp4" in text
    assert "Dokumente: .pdf" in text and "Bilder: .png" in text  # alle Anbieter: ohne Zusatz
    assert text.index("Dokumente") < text.index("Bilder") < text.index("Audio") < text.index("Video")


def test_the_overview_ends_with_the_extensions_claude_does_not_take(app):
    text = app.types_overview()
    assert text.endswith("Nicht bei Claude: .docx, .doc, .odt, .pptx, .ppt, .xlsx, .xls")
    assert text.index("Video") < text.index("Nicht bei Claude")


# ---------- Art und MIME-Typ einer hochgeladenen Datei ----------
@pytest.mark.parametrize("mime, kind", [
    ("application/pdf", "document"), ("text/plain", "document"), ("text/csv", "document"),
    ("application/msword", "document"), ("image/png", "image"), ("image/jpeg", "image"),
    ("audio/mp3", "audio"), ("video/mp4", "video"), ("", "document"), (None, "document"),
])
def test_mime_kind_follows_the_start_of_the_mime_type(app, mime, kind):
    assert app.mime_kind(mime) == kind


def test_file_mime_uses_the_type_of_the_file_and_falls_back_to_pdf(app):
    assert app.file_mime(SimpleNamespace(uri="u", mime_type="image/png")) == "image/png"
    assert app.file_mime(SimpleNamespace(uri="u", mime_type=None)) == "application/pdf"
    assert app.file_mime(SimpleNamespace(uri="u")) == "application/pdf"  # vor Issue #16 war jede Datei ein PDF
