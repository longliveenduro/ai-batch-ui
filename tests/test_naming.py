"""Tests der Namen der Einträge: Namensvergabe aus dem Prompt (kleines Gemini-Modell, auch bei OpenAI-Läufen), Standardname,
Name und Beschreibung ändern und Suche im Verlauf.

Gegen die echte Gemini-API laufen diese Tests nicht (Ersatzdienst FakeGemini mit models.generate_content): Wie sie sich
verhält, steht unter „Verifikationsstand“ in der README.
"""
import re
from datetime import datetime

import pytest

from fakes import FakeGemini, FakeOpenAI, install, install_openai
from helpers import (MODE_BG, PROVIDER_OPENAI, TAB_JOBS, button, captions, click, finished_batch, finished_openai_batch,
                     new_app, new_openai_app, read_history, sent_to_browser, set_prompts, write_history)

ui = pytest.mark.ui
PDF = "application/pdf"
DEFAULT_NAME = r"{kind}-\d{{8}}-\d{{4}}"  # Standardname: Art, Datum und Uhrzeit des Starts


def is_default_name(text, kind="gemini"):
    return re.fullmatch(DEFAULT_NAME.format(kind=kind), text) is not None


@pytest.fixture
def use_gemini(monkeypatch):
    """use_gemini(...) installiert einen FakeGemini (Argumente wie dort) und liefert ihn zurück."""
    def make(*args, **kwargs):
        return install(monkeypatch, FakeGemini(*args, **kwargs))
    return make


@pytest.fixture
def use_openai(monkeypatch):
    """use_openai(...) installiert einen FakeOpenAI (Argumente wie dort) und liefert ihn zurück."""
    def make(**kwargs):
        return install_openai(monkeypatch, FakeOpenAI(**kwargs))
    return make


def never_called():
    raise AssertionError("Der Client wird hier nicht gebraucht.")


def three_entries():
    """Drei Einträge für die Suche, der neueste zuerst. Nur der erste hat eine Beschreibung."""
    return [
        finished_batch(name="batches/aaa111aaa111", label="Zusammenfassung Kapitel 3", description="Für Frau Müller",
                       pdf="Lehrbuch.pdf", pdfs=["Lehrbuch.pdf"], prompts={"prompt-1": "Fasse zusammen"},
                       created="2026-11-03T10:00:00"),
        finished_batch(name="batches/bbb222bbb222", label="batch-20261102-1200",
                       prompts={"prompt-1": "Übersetze den Text ins Englische"}, created="2026-11-02T12:00:00"),
        finished_batch(name="batches/ccc333ccc333", label="Tabellen prüfen", pdf="Zahlen.pdf, Anhang.pdf",
                       pdfs=["Zahlen.pdf", "Anhang.pdf"], prompts={"prompt-1": "Prüfe die Tabellen"},
                       created="2026-11-01T09:00:00"),
    ]


def shown_names(at):
    """Die Namen in der Liste „Eintrag“ des Jobs-Tabs (ohne Datum und ID-Ende)."""
    return [o.split(" (")[0] for o in at.selectbox(key="sel").options]


# ---------- Standardname und Text für das Modell ----------
def test_the_default_label_names_the_kind_and_the_start_time(app):
    assert app.default_label("gemini", datetime(2026, 11, 15, 3, 4)) == "gemini-20261115-0304"
    assert app.default_label("background-gemini", datetime(2026, 11, 15, 3, 4)) == "background-gemini-20261115-0304"
    assert is_default_name(app.default_label("openai"), "openai")


def test_the_naming_settings_are_consistent(app):
    assert app.DEFAULT_NAME_THINK in app.NAME_THINK_LEVELS
    assert "Standard" not in app.NAME_THINK_LEVELS  # jedes Modell hat eine eigene Voreinstellung: Die Stufe wird gesendet
    assert {"auto_name", "name_model", "name_think"} <= set(app.FORM_KEYS)


def test_the_model_sees_the_first_three_prompts_with_a_shared_budget(app):
    prompts = [str(n) * 2000 for n in range(1, 6)]
    parts = app.naming_source(prompts).split("\n---\n")
    assert [p[0] for p in parts] == ["1", "2", "3"]  # nur die ersten drei
    assert all(len(p) == app.NAME_SOURCE_CHARS // 3 for p in parts)


def test_a_single_prompt_may_use_the_whole_budget(app):
    assert app.naming_source(["x" * 5000]) == "x" * app.NAME_SOURCE_CHARS
    assert app.naming_source(["  Frage  "]) == "Frage"


def test_a_continued_conversation_is_named_by_the_new_prompt_only(app):
    earlier = [("Alte Frage", "Alte Antwort")]
    assert app.naming_source([app.conversation_text(earlier, "Neue Frage")]) == "Neue Frage"
    assert app.naming_source([app.conversation_text(earlier)]) == ""  # noch kein neuer Prompt: nichts zu benennen


def test_without_prompt_text_there_is_nothing_to_name(app):
    assert app.naming_source([]) == app.naming_source(["", " \n "]) == ""


@pytest.mark.parametrize("answer, expected", [
    ("Kapitel 3 einfach erklärt", "Kapitel 3 einfach erklärt"),
    ("„Kapitel 3 einfach erklärt“.", "Kapitel 3 einfach erklärt"),
    ('"Kapitel 3 einfach erklärt"', "Kapitel 3 einfach erklärt"),
    ("**Kapitel 3 einfach erklärt**", "Kapitel 3 einfach erklärt"),
    ("# Kapitel 3", "Kapitel 3"),
    ("- Kapitel 3", "Kapitel 3"),
    ("\n\n  Kapitel   3 \n die übrigen Zeilen zählen nicht", "Kapitel 3"),
    ("Wie geht das?", "Wie geht das?"),  # ein Fragezeichen gehört zum Namen
    ("", ""), ("   ", ""), ("***", ""), (None, ""),
])
def test_the_answer_of_the_model_is_cleaned_up_to_a_plain_name(app, answer, expected):
    assert app.clean_name(answer) == expected


def test_a_long_name_is_cut_at_a_word_boundary(app):
    name = app.clean_name("Wort " * 30)
    assert name.endswith("…") and len(name) <= app.NAME_MAX_CHARS + 1
    assert name[:-1].split(" ")[-1] == "Wort"  # nicht mitten im Wort
    assert app.clean_name("x" * 100) == "x" * app.NAME_MAX_CHARS + "…"  # ohne Leerzeichen bleibt nur der harte Schnitt


# ---------- Aufruf des Modells ----------
def test_generate_name_asks_the_model_with_the_given_thinking_level(app):
    fake = FakeGemini(name_text="„Kapitel 3 erklärt“.")
    assert app.generate_name(fake, ["Erkläre Kapitel 3."], "gemini-3.5-flash-lite", "low") == "Kapitel 3 erklärt"
    [call] = fake.name_calls  # der Denk-Teil der Antwort zählt nicht zum Namen
    assert call["model"] == "gemini-3.5-flash-lite" and call["contents"] == "Erkläre Kapitel 3."  # nur der Prompt-Text
    assert call["config"] == {"system_instruction": app.NAME_INSTRUCTION, "max_output_tokens": app.NAME_MAX_OUT,
                              "thinking_config": {"thinking_level": "low"},
                              "http_options": {"timeout": app.NAME_TIMEOUT_MS}}


def test_generate_name_makes_no_call_without_prompt_text(app):
    fake = FakeGemini()
    assert app.generate_name(fake, ["", " "], "gemini-3.5-flash-lite", "low") == "" and fake.name_calls == []


def test_generate_name_returns_nothing_when_the_model_only_thought(app):
    fake = FakeGemini(name_text="")  # nur ein Denk-Teil: response.text ist None
    assert app.generate_name(fake, ["Frage"], "gemini-3.5-flash-lite", "low") == ""


def test_generate_name_passes_api_errors_on(app):
    fake = FakeGemini(name_error=RuntimeError("429 Kontingent erschöpft"))
    with pytest.raises(RuntimeError, match="429"):
        app.generate_name(fake, ["Frage"], "gemini-3.5-flash-lite", "low")


# ---------- Welcher Name gilt ----------
def test_a_typed_name_always_wins_and_asks_no_model(app):
    assert app.choose_label("  Mein Lauf ", "gemini", ["Frage"], never_called, "m", "low") == ("Mein Lauf", False, None)


def test_with_the_automatic_name_off_the_default_name_is_used(app):
    name, generated, error = app.choose_label("", "gemini", ["Frage"], never_called, "m", "low", auto=False)
    assert is_default_name(name) and not generated and error is None


def test_without_a_client_the_default_name_is_used_without_a_complaint(app):
    name, generated, error = app.choose_label("", "openai", ["Frage"], lambda: None, "m", "low")
    assert is_default_name(name, "openai") and not generated and error is None


def test_an_empty_field_is_named_from_the_prompts(app):
    fake = FakeGemini(name_text="Kapitel 3 erklärt")
    assert app.choose_label("", "gemini", ["Frage"], lambda: fake, "m", "low") == ("Kapitel 3 erklärt", True, None)


@pytest.mark.parametrize("fake_args, reason", [
    ({"name_error": RuntimeError("Kontingent erschöpft")}, "Kontingent erschöpft"),
    ({"name_text": ""}, "keinen Namen"),
])
def test_a_failed_naming_falls_back_to_the_default_name_and_says_why(app, fake_args, reason):
    fake = FakeGemini(**fake_args)
    name, generated, error = app.choose_label("", "background-gemini", ["Frage"], lambda: fake, "m", "low")
    assert is_default_name(name, "background-gemini") and not generated and reason in error


def test_a_failing_client_does_not_stop_the_start_either(app):
    def broken():
        raise RuntimeError("Client kaputt")
    name, generated, error = app.choose_label("", "gemini", ["Frage"], broken, "m", "low")
    assert is_default_name(name) and not generated and "Client kaputt" in error


# ---------- Suche und Dateiname ----------
@pytest.mark.parametrize("query, expected", [
    ("kapitel", ["Zusammenfassung Kapitel 3"]),  # Name, Groß- und Kleinschreibung egal
    ("MÜLLER", ["Zusammenfassung Kapitel 3"]),  # Beschreibung
    ("englische", ["batch-20261102-1200"]),  # Prompt
    ("anhang", ["Tabellen prüfen"]),  # PDF-Name
    ("bbb222", ["batch-20261102-1200"]),  # ID
    ("frau kapitel", ["Zusammenfassung Kapitel 3"]),  # alle Wörter müssen vorkommen, die Reihenfolge ist egal
    ("kapitel englische", []),
    ("", ["Zusammenfassung Kapitel 3", "batch-20261102-1200", "Tabellen prüfen"]),  # leere Suche: alles, in Reihenfolge
    ("  ", ["Zusammenfassung Kapitel 3", "batch-20261102-1200", "Tabellen prüfen"]),
])
def test_the_search_finds_entries_by_name_description_prompt_pdf_and_id(app, query, expected):
    assert [x["label"] for x in app.search_jobs(three_entries(), query)] == expected


def test_the_search_copes_with_entries_from_older_versions(app):
    assert app.matches({"name": "batches/x1", "label": "alt"}, "alt")  # weder Beschreibung noch PDF noch Prompts
    assert not app.matches({"name": "batches/x1", "label": "alt", "pdf": None, "prompts": {}}, "neu")


@pytest.mark.parametrize("label, expected", [
    ("Kapitel 3 einfach erklärt", "Kapitel 3 einfach erklärt"),
    ("batch-20261115-0304", "batch-20261115-0304"),
    ('Wie geht "A/B": Test?', "Wie geht -A-B- Test"),
    ("  ..Name..  ", "Name"),
    ("///", "ergebnisse"),
])
def test_the_download_file_name_is_safe_for_every_name(app, label, expected):
    assert app.file_stem(label) == expected


# ---------- Oberfläche: Start ----------
@ui
def test_an_empty_name_field_gets_its_name_from_the_prompt(use_gemini, home, app):
    fake = use_gemini(name_text="Kapitel 3 einfach erklärt")
    at = new_app()
    at.run()
    at.file_uploader[0].set_value([("Buch.pdf", b"PDF-1", PDF)])
    set_prompts(at, "Erkläre Kapitel 3 in einfacher Sprache.")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    entry = read_history(home)[0]
    assert entry["label"] == "Kapitel 3 einfach erklärt"
    [call] = fake.name_calls  # Voreinstellung der Seitenleiste: gemini-3.5-flash-lite mit Denktiefe medium
    assert call["model"] == "gemini-3.5-flash-lite" and call["config"]["thinking_config"] == {"thinking_level": "medium"}
    assert call["contents"] == "Erkläre Kapitel 3 in einfacher Sprache."  # nur der Prompt, das PDF bleibt draußen
    assert fake.created_batches[0][2] == {"display_name": "Kapitel 3 einfach erklärt"}  # auch beim Anbieter
    assert any("Kapitel 3 einfach erklärt" in c and "erzeugt" in c for c in captions(at))
    assert at.session_state["sel"] == app.entry_label(entry) and "Kapitel 3 einfach erklärt" in at.session_state["sel"]


@ui
def test_the_name_field_starts_empty_and_says_what_happens_with_an_empty_field(use_gemini):
    use_gemini()
    at = new_app()
    at.run()
    field = at.text_input(key="label_gemini")
    assert field.value == "" and field.placeholder == "automatisch aus dem Prompt"


@ui
def test_a_typed_name_is_used_as_it_is_and_the_model_is_not_asked(use_gemini, home):
    fake = use_gemini()
    at = new_app()
    at.run()
    at.text_input(key="label_gemini").set_value("  Mein Lauf ")
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error
    assert read_history(home)[0]["label"] == "Mein Lauf" and fake.name_calls == []
    assert not any("erzeugt" in c for c in captions(at))


@ui
def test_the_automatic_name_can_be_switched_off(use_gemini, home):
    fake = use_gemini()
    at = new_app()
    at.run()
    at.checkbox(key="auto_name").set_value(False)
    at.run()
    assert is_default_name(at.text_input(key="label_gemini").placeholder)  # der Platzhalter zeigt dann den Standardnamen
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    assert is_default_name(read_history(home)[0]["label"]) and fake.name_calls == []


@ui
def test_the_default_name_of_a_batch_names_the_provider_not_the_mode(use_gemini, use_openai):
    use_gemini()
    use_openai()
    at = new_app()
    at.run()
    at.checkbox(key="auto_name").set_value(False)
    at.run()
    placeholder = at.text_input(key="label_gemini").placeholder  # Gemini-Batch: gemini-… (nicht mehr batch-…)
    assert is_default_name(placeholder, "gemini") and not placeholder.startswith("batch-")
    at.radio(key="provider").set_value(PROVIDER_OPENAI)
    at.run()
    assert not at.exception and is_default_name(at.text_input(key="label_openai").placeholder, "openai")


@ui
def test_the_default_name_of_a_background_run_names_the_mode_and_the_provider(use_gemini, home):
    use_gemini()
    at = new_app()
    at.run()
    at.checkbox(key="auto_name").set_value(False)
    at.radio(key="mode").set_value(MODE_BG)
    at.run()
    placeholder = at.text_input(key="label_background-gemini").placeholder  # background-gemini-… (nicht background-…)
    assert is_default_name(placeholder, "background-gemini") and not re.match(r"background-\d", placeholder)
    set_prompts(at, "Frage")
    click(at, "Im Hintergrund starten")
    assert not at.exception and not at.error
    entry = read_history(home)[0]
    assert entry["mode"] == "background" and is_default_name(entry["label"], "background-gemini")


@ui
def test_model_and_thinking_level_of_the_names_come_from_the_sidebar(use_gemini):
    fake = use_gemini()
    at = new_app()
    at.run()
    assert at.checkbox(key="auto_name").value is True and at.text_input(key="name_model").value == "gemini-3.5-flash-lite"
    assert at.selectbox(key="name_think").value == "medium"
    assert at.selectbox(key="name_think").options == ["minimal", "low", "medium", "high"]
    at.text_input(key="name_model").set_value("gemini-3.8-flash")
    at.selectbox(key="name_think").set_value("minimal")
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    call = fake.name_calls[0]
    assert call["model"] == "gemini-3.8-flash" and call["config"]["thinking_config"] == {"thinking_level": "minimal"}


@ui
def test_the_naming_settings_survive_a_visit_to_the_other_provider(use_gemini, use_openai):
    use_gemini()
    use_openai()
    at = new_app()
    at.run()
    at.checkbox(key="auto_name").set_value(False)
    at.text_input(key="name_model").set_value("mein-eigenes-modell")
    at.selectbox(key="name_think").set_value("high")
    at.run()
    for provider in (PROVIDER_OPENAI, "Gemini"):
        at.radio(key="provider").set_value(provider)
        at.run()
        assert not at.exception
        sent_to_browser(at.checkbox(key="auto_name"), False)
        sent_to_browser(at.text_input(key="name_model"), "mein-eigenes-modell")
        sent_to_browser(at.selectbox(key="name_think"), "high")


@ui
def test_a_failing_naming_never_stops_the_start(use_gemini, home):
    fake = use_gemini(name_error=RuntimeError("Kontingent erschöpft"))
    at = new_app()
    at.run()
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error and "läuft" in at.success[0].value
    entry = read_history(home)[0]
    assert is_default_name(entry["label"]) and len(fake.created_batches) == 1
    assert any("Kontingent erschöpft" in w.value and entry["label"] in w.value for w in at.warning)


@ui
def test_an_answer_without_a_name_falls_back_to_the_default_name(use_gemini, home):
    use_gemini(name_text="")
    at = new_app()
    at.run()
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error
    assert is_default_name(read_history(home)[0]["label"]) and any("keinen Namen" in w.value for w in at.warning)


@ui
def test_background_runs_are_named_too(use_gemini, home):
    fake = use_gemini(name_text="Lange Analyse")
    at = new_app()
    at.run()
    at.radio(key="mode").set_value(MODE_BG)
    at.run()
    assert at.text_input(key="label_background-gemini").placeholder == "automatisch aus dem Prompt"
    set_prompts(at, "Analysiere alles gründlich")
    click(at, "Im Hintergrund starten")
    assert not at.exception and not at.error
    entry = read_history(home)[0]
    assert entry["mode"] == "background" and entry["label"] == "Lange Analyse"
    assert fake.name_calls[0]["contents"] == "Analysiere alles gründlich"


@ui
def test_an_openai_run_is_named_with_gemini_and_the_form_says_so(use_gemini, use_openai, home):
    gemini, openai_fake = use_gemini(name_text="Vertrag auf Fristen prüfen"), use_openai()
    at = new_openai_app(auto_name=True)
    at.run()
    assert any("an Google" in c and "OpenAI-Lauf" in c for c in captions(at))  # der Auszug verlässt OpenAI
    at.text_input(key="label_openai").set_value("Eigener Name")
    at.run()
    assert not any("an Google" in c for c in captions(at))  # mit eigenem Namen geht nichts an Google
    at.text_input(key="label_openai").set_value("")
    set_prompts(at, "Prüfe den Vertrag auf Fristen")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    entry = read_history(home)[0]
    assert entry["provider"] == PROVIDER_OPENAI and entry["label"] == "Vertrag auf Fristen prüfen"
    assert gemini.name_calls[0]["contents"] == "Prüfe den Vertrag auf Fristen"
    assert openai_fake.created_batches[0]["metadata"] == {"description": "Vertrag auf Fristen prüfen"}


@ui
def test_without_a_gemini_key_every_run_gets_the_default_name(use_openai, monkeypatch, home):
    monkeypatch.setenv("GEMINI_API_KEY", "")  # kein Gemini-Client, die Namensvergabe fällt still aus
    use_openai()
    at = new_openai_app(auto_name=True)
    at.run()
    assert not at.exception and any("Ohne Gemini API-Key" in c for c in captions(at))
    assert is_default_name(at.text_input(key="label_openai").placeholder, "openai")
    assert not any("an Google" in c for c in captions(at))
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    assert is_default_name(read_history(home)[0]["label"], "openai")


# ---------- Oberfläche: Jobs-Tab ----------
@ui
def test_the_search_narrows_down_the_list_of_entries(use_gemini, home):
    write_history(home, three_entries())
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and len(shown_names(at)) == 3
    for query, expected in [("kapitel", ["Zusammenfassung Kapitel 3"]), ("müller", ["Zusammenfassung Kapitel 3"]),
                            ("englische", ["batch-20261102-1200"]), ("zahlen anhang", ["Tabellen prüfen"])]:
        at.text_input(key="jobs_search").set_value(query)
        at.run()
        assert not at.exception and shown_names(at) == expected
        assert f"Treffer: {len(expected)} von 3 Einträgen." in captions(at)
    at.text_input(key="jobs_search").set_value("")
    at.run()
    assert len(shown_names(at)) == 3 and not any(c.startswith("Treffer:") for c in captions(at))


@ui
def test_a_search_without_a_match_says_so_and_shows_no_entry(use_gemini, home):
    write_history(home, three_entries())
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    at.text_input(key="jobs_search").set_value("gibt es nicht")
    at.run()
    assert not at.exception and not [s for s in at.selectbox if s.key == "sel"]
    assert any("Kein Eintrag passt zu „gibt es nicht“" in i.value for i in at.info)
    at.text_input(key="jobs_search").set_value("")
    at.run()
    assert len(shown_names(at)) == 3


@ui
def test_without_entries_there_is_nothing_to_search(use_gemini):
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and any("Noch nichts gestartet" in i.value for i in at.info)
    assert not [t for t in at.text_input if t.key == "jobs_search"]


@ui
def test_a_new_entry_is_visible_even_when_a_search_was_active(use_gemini, home, app):
    write_history(home, three_entries())
    use_gemini(name_text="Ganz neuer Lauf")
    at = new_app()
    at.run()
    at.session_state["jobs_search"] = "kapitel"
    set_prompts(at, "Etwas ganz anderes")
    click(at, "Batch starten")
    newest = read_history(home)[0]
    assert newest["label"] == "Ganz neuer Lauf"
    assert at.session_state["jobs_search"] == "" and at.session_state["sel"] == app.entry_label(newest)
    at.session_state["view"] = TAB_JOBS
    at.run()
    assert at.selectbox(key="sel").value == app.entry_label(newest) and len(shown_names(at)) == 4


@ui
def test_name_and_description_can_be_changed(use_gemini, home, app):
    entries = three_entries()
    write_history(home, entries)
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    key = entries[0]["name"]
    assert at.text_input(key="title:" + key).value == "Zusammenfassung Kapitel 3"
    assert at.text_area(key="descr:" + key).value == "Für Frau Müller"
    assert "Für Frau Müller" in captions(at)  # die Beschreibung steht unter der Liste
    at.text_input(key="title:" + key).set_value("  Kapitel 3   für  Frau Müller ")
    at.text_area(key="descr:" + key).set_value("Zweite Fassung, mit Beispielen\n")
    click(at, "Speichern")
    assert not at.exception and not at.warning
    saved = read_history(home)[0]
    assert (saved["label"], saved["description"]) == ("Kapitel 3 für Frau Müller", "Zweite Fassung, mit Beispielen")
    assert saved["name"] == key and saved["prompts"] == entries[0]["prompts"]  # sonst ändert sich nichts
    assert [e["label"] for e in read_history(home)[1:]] == [e["label"] for e in entries[1:]]
    assert at.session_state["sel"] == app.entry_label(saved) == at.selectbox(key="sel").value
    assert "Zweite Fassung, mit Beispielen" in captions(at)


@ui
def test_an_empty_name_keeps_the_old_one_and_the_description_may_be_removed(use_gemini, home):
    entries = three_entries()
    write_history(home, entries)
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    key = entries[0]["name"]
    at.text_input(key="title:" + key).set_value("   ")
    at.text_area(key="descr:" + key).set_value("")
    click(at, "Speichern")
    assert not at.exception
    saved = read_history(home)[0]
    assert saved["label"] == "Zusammenfassung Kapitel 3" and saved["description"] == ""
    assert at.text_input(key="title:" + key).value == "Zusammenfassung Kapitel 3"
    assert "Für Frau Müller" not in captions(at)


@ui
def test_a_renamed_entry_stays_selected_when_it_no_longer_matches_the_search(use_gemini, home):
    entries = three_entries()
    write_history(home, entries)
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    at.text_input(key="jobs_search").set_value("kapitel")
    at.run()
    key = entries[0]["name"]
    at.text_input(key="title:" + key).set_value("Ganz anders")
    at.text_area(key="descr:" + key).set_value("")
    click(at, "Speichern")
    assert not at.exception
    assert at.text_input(key="jobs_search").value == ""  # sonst wäre der Eintrag aus der Liste verschwunden
    assert at.selectbox(key="sel").value.startswith("Ganz anders") and len(shown_names(at)) == 3


@ui
def test_the_name_of_an_old_entry_can_be_generated_from_its_prompt(use_gemini, home, app):
    old = finished_batch(label="batch-20261019-1438", prompts={"prompt-1": "Liste alle Fristen auf"})
    write_history(home, [old])
    fake = use_gemini(name_text="Fristen auflisten")
    at = new_app(TAB_JOBS)
    at.run()
    click(at, "Name aus dem Prompt erzeugen")
    assert not at.exception and not at.warning
    assert fake.name_calls[0]["contents"] == "Liste alle Fristen auf"
    saved = read_history(home)[0]
    assert saved["label"] == "Fristen auflisten" and "description" not in saved
    assert at.selectbox(key="sel").value == app.entry_label(saved)
    assert at.text_input(key="title:" + old["name"]).value == "Fristen auflisten"


@ui
def test_a_failing_name_generation_keeps_the_name_and_says_why_once(use_gemini, home):
    old = finished_batch(label="batch-20261019-1438")
    write_history(home, [old])
    use_gemini(name_error=RuntimeError("Kontingent erschöpft"))
    at = new_app(TAB_JOBS)
    at.run()
    click(at, "Name aus dem Prompt erzeugen")
    assert not at.exception and read_history(home)[0]["label"] == "batch-20261019-1438"
    assert any("Kontingent erschöpft" in w.value for w in at.warning)
    at.run()
    assert not at.warning  # der Hinweis erscheint nur einmal


@ui
def test_generating_a_name_needs_a_gemini_key(use_openai, monkeypatch, home):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    use_openai()
    write_history(home, [finished_openai_batch()])
    at = new_openai_app(TAB_JOBS)
    at.run()
    assert not at.exception and button(at, "Name aus dem Prompt erzeugen").disabled
