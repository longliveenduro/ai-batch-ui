"""Tests der Claude-Anbindung (nur Batch, Message Batches API): Anfrageaufbau, Datei-Upload, Ergebniszeilen, Statusabfrage
und Oberfläche.

Die Antworten der Fakes sind echte SDK-Objekte und nach dem Schema des SDK gültig (siehe
test_the_sample_messages_match_the_sdk_schema). Vier Tests lassen außerdem den echten Code des SDK laufen und fangen nur
die HTTP-Anfragen ab (real_claude_client). Gegen die echte Anthropic-API laufen diese Tests nicht: Wie sie sich verhält,
steht unter „Verifikationsstand“ in der README.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from anthropic.types import Message
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages import MessageBatchIndividualResponse
from pydantic import TypeAdapter, ValidationError

import helpers
from fakes import (ClaudeError, FakeClaude, FakeGemini, FakeOpenAI, batch_json, claude_errored, file_json, install,
                   install_claude, install_openai, json_response, jsonl_response, make_claude_message, real_claude_client)
from helpers import (MODE_BATCH, PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, TAB_JOBS, TAB_NEW, batch_entry,
                     button, captions, claude_entry, click, finished_batch, finished_claude_batch, markdown,
                     model_field, new_app, new_claude_app, openai_entry, read_history, sent_to_browser, set_prompts,
                     write_history)

ui = pytest.mark.ui
PDF = "application/pdf"
FILES = [SimpleNamespace(id="file_A", mime_type=PDF), SimpleNamespace(id="file_B", mime_type="text/plain")]
CACHE = {"type": "ephemeral", "ttl": "1h"}


@pytest.fixture
def use_claude(monkeypatch):
    """use_claude(...) installiert einen FakeClaude (Argumente wie dort) und liefert ihn zurück."""
    def make(**kwargs):
        return install_claude(monkeypatch, FakeClaude(**kwargs))
    return make


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


def result_line(key="prompt-1", **message_args):
    """Ein Ergebnis einer erfolgreichen Anfrage, so wie es die App aus dem SDK-Objekt macht (dict)."""
    return {"custom_id": key, "result": {"type": "succeeded", "message": make_claude_message(**message_args)}}


def requests(*keys):
    return [{"custom_id": k, "params": {}} for k in keys]


def started(fake, *keys):
    """Legt im Fake einen Batch zu den Schlüsseln an und liefert dessen ID."""
    return fake.messages.batches.create(requests=requests(*keys)).id


# ---------- Anbieter und Clients ----------
def test_ui_texts_used_by_the_claude_tests_match_the_app(app):
    assert app.PROVIDER_CLAUDE == PROVIDER_CLAUDE and app.PROVIDERS[-1] == PROVIDER_CLAUDE


def test_entry_provider_reads_claude_entries_and_keeps_the_others(app):
    assert app.entry_provider(claude_entry()) == PROVIDER_CLAUDE
    assert app.entry_provider(openai_entry()) == PROVIDER_OPENAI
    assert app.entry_provider(batch_entry()) == PROVIDER_GEMINI
    assert app.entry_provider({"provider": "etwas Unbekanntes"}) == PROVIDER_GEMINI


def test_make_client_builds_the_claude_client(app, monkeypatch):
    fake = install_claude(monkeypatch, FakeClaude())
    assert app.make_client(PROVIDER_CLAUDE, "sk-ant-1") is fake and fake.client_kwargs == [{"api_key": "sk-ant-1"}]


def test_claude_client_explains_a_missing_package(app, monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # der Import schlägt dann mit ImportError fehl
    with pytest.raises(RuntimeError, match="pip install"):
        app.claude_client("sk-ant-1")


# ---------- Dateiname und MIME-Typ ----------
@pytest.mark.parametrize("name, expected", [
    ("Bericht.pdf", "Bericht.pdf"),
    ("Buch: Teil 1?.pdf", "Buch- Teil 1-.pdf"),
    ('a/b\\c|d*e"f<g>h.txt', "a-b-c-d-e-f-g-h.txt"),
    ("Zeile\nUmbruch.md", "Zeile-Umbruch.md"),
    ("<>.pdf", "-.pdf"),
    ("Größe überprüfen.pdf", "Größe überprüfen.pdf"),  # Umlaute sind erlaubt
])
def test_claude_filename_replaces_the_characters_the_files_api_rejects(app, name, expected):
    assert app.claude_filename(name) == expected


def test_claude_filename_cuts_a_too_long_name_before_the_extension(app):
    name = app.claude_filename("x" * 400 + ".pdf")
    assert len(name) == 255 and name.endswith("xxx.pdf")


@pytest.mark.parametrize("name, mime", [
    ("buch.pdf", "application/pdf"), ("foto.png", "image/png"), ("foto.JPG", "image/jpeg"),
    ("foto.webp", "image/webp"), ("notiz.txt", "text/plain"), ("README.md", "text/plain"),
    ("tabelle.csv", "text/plain"),  # CSV geht als Text: Claude liest als Dokument nur PDF und text/plain
    ("skript.py", "text/plain"),
])
def test_claude_mime_sends_pdf_and_images_as_they_are_and_all_text_as_text_plain(app, name, mime):
    assert app.claude_mime(name) == mime


@pytest.mark.parametrize("name, part", [
    ("bericht.docx", "nimmt Claude nicht an"), ("folien.pptx", "nimmt Claude nicht an"),
    ("zahlen.xlsx", "nimmt Claude nicht an"), ("ton.mp3", "Audio nimmt Claude nicht an"),
    ("film.mp4", "Video nimmt Claude nicht an"), ("archiv.zip", "wird nicht unterstützt"),
    ("LIESMICH", "Ohne Endung"),
])
def test_claude_mime_rejects_what_claude_does_not_take(app, name, part):
    with pytest.raises(ValueError, match=part):
        app.claude_mime(name)


# ---------- Anfrageaufbau und Batch ----------
def test_claude_request_puts_the_files_first_and_sets_all_options(app):
    params = app.claude_request("claude-opus-5-5", FILES, "Frage", "Sei kurz.", "high", 4096)
    assert params == {
        "model": "claude-opus-5-5", "max_tokens": 4096, "system": "Sei kurz.", "output_config": {"effort": "high"},
        "messages": [{"role": "user", "content": [
            {"type": "document", "source": {"type": "file", "file_id": "file_A"}},
            {"type": "document", "source": {"type": "file", "file_id": "file_B"}},
            {"type": "text", "text": "Frage"}]}]}


def test_claude_request_sends_images_as_image_blocks_and_keeps_the_order(app):
    files = [SimpleNamespace(id="file_1", mime_type="image/png"), SimpleNamespace(id="file_2", mime_type=PDF),
             SimpleNamespace(id="file_3", mime_type="image/jpeg")]
    content = app.claude_request("m", files, "Frage", "", "Standard", 100)["messages"][0]["content"]
    assert [(b["type"], b.get("source", {}).get("file_id")) for b in content] == [
        ("image", "file_1"), ("document", "file_2"), ("image", "file_3"), ("text", None)]


def test_claude_request_with_standard_effort_and_no_system_sends_neither(app):
    params = app.claude_request("m", [], "Frage", "", "Standard", 32768)
    assert params == {"model": "m", "max_tokens": 32768,
                      "messages": [{"role": "user", "content": [{"type": "text", "text": "Frage"}]}]}


def test_every_effort_except_standard_is_sent_as_output_config_effort(app):
    assert app.CLAUDE_EFFORTS == ["Standard", "low", "medium", "high", "xhigh", "max"]
    for effort in app.CLAUDE_EFFORTS[1:]:
        assert app.claude_request("m", [], "F", "", effort, 100)["output_config"] == {"effort": effort}


def test_max_out_is_sent_as_a_whole_number(app):
    assert app.claude_request("m", [], "F", "", "Standard", 4096.0)["max_tokens"] == 4096


def test_claude_request_marks_only_the_last_file_for_the_prompt_cache(app):
    content = app.claude_request("m", FILES, "Frage", "Sei kurz.", "Standard", 100, cache=True)["messages"][0]["content"]
    assert [b.get("cache_control") for b in content] == [None, CACHE, None]  # die Datei trägt die Marke, nicht der Prompt
    plain = app.claude_request("m", FILES, "Frage", "Sei kurz.", "Standard", 100)["messages"][0]["content"]
    assert not any("cache_control" in b for b in plain)  # Voreinstellung: kein Cache


def test_the_cache_marker_needs_a_file_and_otherwise_nothing_is_marked(app):
    params = app.claude_request("m", [], "Frage", "Sei kurz.", "Standard", 100, cache=True)
    assert "cache_control" not in json.dumps(params)


def test_the_claude_requests_are_valid_for_the_sdk_schema(app):
    files = FILES + [SimpleNamespace(id="file_C", mime_type="image/png")]
    schema = TypeAdapter(MessageCreateParamsNonStreaming)
    for effort in app.CLAUDE_EFFORTS:
        for cache in (False, True):
            params = app.claude_request("claude-sonnet-5-5", files, "Frage", "Sei kurz.", effort, 4096, cache)
            schema.validate_python(params)
    schema.validate_python(app.claude_request("claude-sonnet-5-5", [], "Frage", "", "Standard", 4096))
    broken = app.claude_request("claude-sonnet-5-5", files, "Frage", "", "Standard", 4096)
    broken["output_config"] = {"effort": "ultra"}  # der Test beißt: Das Schema kennt diese Stufe nicht
    with pytest.raises(ValidationError):
        schema.validate_python(broken)


def test_start_claude_batch_writes_one_jsonl_line_per_prompt_and_creates_the_batch(app, home):
    fake = FakeClaude()
    batch_id, keyed = app.start_claude_batch(fake, "claude-opus-5-5", FILES, ["Eins", "Zwei"], "Sei kurz.", "high", 4096)
    assert batch_id == "msgbatch_fake000001" and keyed == {"prompt-1": "Eins", "prompt-2": "Zwei"}
    assert fake.created_batches == [{"count": 2}]
    assert [r["custom_id"] for r in fake.batch_requests] == ["prompt-1", "prompt-2"]
    assert fake.batch_requests[1]["params"] == app.claude_request(
        "claude-opus-5-5", FILES, "Zwei", "Sei kurz.", "high", 4096)
    [path] = list((home / "data").glob("requests_claude_*.jsonl"))  # zur Kontrolle liegt dieselbe Anfrage im Ordner data
    assert [json.loads(line) for line in path.read_text("utf-8").splitlines()] == fake.batch_requests


def test_the_claude_requests_stay_in_the_data_folder_with_readable_umlauts(app, home):
    app.start_claude_batch(FakeClaude(), "m", [], ["Größe überprüfen"], "", "Standard", 100)
    [path] = list((home / "data").glob("requests_claude_*.jsonl"))
    assert "Größe überprüfen" in path.read_text("utf-8")  # kein \u00f6 im Text


def test_start_claude_batch_passes_the_cache_option_on_to_every_request(app):
    fake = FakeClaude()
    app.start_claude_batch(fake, "m", FILES, ["Eins", "Zwei"], "", "Standard", 100, cache=True)
    for request in fake.batch_requests:
        assert [b.get("cache_control") for b in request["params"]["messages"][0]["content"]] == [None, CACHE, None]
    other = FakeClaude()
    app.start_claude_batch(other, "m", FILES, ["Eins"], "", "Standard", 100)  # ohne Angabe: kein Cache
    assert "cache_control" not in json.dumps(other.batch_requests)


def test_a_failing_batch_creation_raises_and_leaves_no_batch(app):
    fake = FakeClaude(create_error=ClaudeError(400, "Ungültige Anfrage"))
    with pytest.raises(ClaudeError):
        app.start_claude_batch(fake, "m", [], ["Eins"], "", "Standard", 100)
    assert fake.created_batches == []


# ---------- Datei-Upload ----------
def test_upload_file_claude_uploads_once_and_remembers_the_file_by_content(app, home):
    fake = FakeClaude()
    first = app.upload_file_claude(fake, "buch.pdf", b"PDF-INHALT")
    again = app.upload_file_claude(fake, "kopie.pdf", b"PDF-INHALT")  # gleicher Inhalt, anderer Name
    assert first.id == again.id == "file_fake000001" and fake.uploads == [b"PDF-INHALT"]
    assert fake.metadata_calls == ["file_fake000001"]  # die zweite Anfrage prüfte nur, ob die Datei noch lebt
    db = json.loads((home / "data" / "claude_files.json").read_text("utf-8"))
    assert db == {hashlib.sha256(b"PDF-INHALT").hexdigest(): "file_fake000001"}


def test_upload_file_claude_sends_the_pdf_with_a_safe_name_the_pdf_type_and_a_lifetime(app):
    fake = FakeClaude()
    f = app.upload_file_claude(fake, "Buch: Teil 1.pdf", b"PDF")
    assert fake.upload_names == ["Buch- Teil 1.pdf"] and fake.upload_mimes == [PDF]
    assert fake.file_calls == [{"expires_in_seconds": 3 * 24 * 3600}]
    assert f.expires_at is not None and f.expires_at - datetime.now(timezone.utc) > timedelta(days=2)


@pytest.mark.parametrize("name", ["notiz.txt", "daten.csv", "README.md", "skript.py", "log.JSON"])
def test_upload_file_claude_sends_text_and_csv_as_text_plain_and_they_become_documents(app, name):
    fake = FakeClaude()
    f = app.upload_file_claude(fake, name, b"Text")
    assert fake.upload_mimes == ["text/plain"] and app.claude_file_part(f) == {
        "type": "document", "source": {"type": "file", "file_id": f.id}}


@pytest.mark.parametrize("name, mime", [("foto.png", "image/png"), ("foto.JPG", "image/jpeg"),
                                        ("foto.webp", "image/webp")])
def test_upload_file_claude_sends_images_with_their_type_and_they_become_image_blocks(app, name, mime):
    fake = FakeClaude()
    f = app.upload_file_claude(fake, name, b"BILD")
    assert fake.upload_mimes == [mime] and app.claude_file_part(f) == {
        "type": "image", "source": {"type": "file", "file_id": f.id}}


def test_a_remembered_image_stays_an_image_block_after_a_restart(app):
    fake = FakeClaude()
    app.upload_file_claude(fake, "foto.png", b"BILD")
    again = app.upload_file_claude(fake, "foto.png", b"BILD")  # später: Die Datei kommt aus der Merkliste
    assert fake.uploads == [b"BILD"] and app.claude_file_part(again)["type"] == "image"


@pytest.mark.parametrize("name", ["bericht.docx", "folien.pptx", "zahlen.xlsx", "ton.mp3", "film.mp4", "archiv.zip",
                                  "LIESMICH"])
def test_upload_file_claude_rejects_what_claude_does_not_take_before_uploading(app, home, name):
    fake = FakeClaude()
    with pytest.raises(ValueError):
        app.upload_file_claude(fake, name, b"X")
    assert fake.uploads == [] and not (home / "data" / "claude_files.json").exists()


def test_upload_file_claude_different_content_gets_its_own_file(app):
    fake = FakeClaude()
    a, b = app.upload_file_claude(fake, "a.pdf", b"EINS"), app.upload_file_claude(fake, "a.pdf", b"ZWEI")
    assert a.id != b.id and fake.uploads == [b"EINS", b"ZWEI"]


def test_upload_file_claude_uploads_again_when_the_file_is_gone(app, home):
    fake = FakeClaude()
    first = app.upload_file_claude(fake, "a.pdf", b"PDF")
    fake.gone.add(first.id)  # abgelaufen, gelöscht oder aus einem anderen Workspace
    second = app.upload_file_claude(fake, "a.pdf", b"PDF")
    assert second.id != first.id and fake.uploads == [b"PDF", b"PDF"]
    assert list(json.loads((home / "data" / "claude_files.json").read_text("utf-8")).values()) == [second.id]


def test_upload_file_claude_uploads_again_when_the_file_would_expire_during_a_batch(app):
    """Ein Batch läuft bis zu 24 Stunden: Eine Datei, die früher verfällt, würde ihn mit Fehlern enden lassen."""
    fake = FakeClaude()
    first = app.upload_file_claude(fake, "a.pdf", b"PDF")
    now = datetime.now(timezone.utc)
    fake.expiry[first.id] = now + timedelta(hours=40)  # lebt lange genug: wiederverwenden
    assert app.upload_file_claude(fake, "a.pdf", b"PDF").id == first.id and len(fake.uploads) == 1
    fake.expiry[first.id] = now + timedelta(hours=20)  # zu kurz: neu hochladen
    assert app.upload_file_claude(fake, "a.pdf", b"PDF").id != first.id and len(fake.uploads) == 2


def test_upload_file_claude_uploads_again_when_the_metadata_of_an_expired_file_is_still_readable(app):
    fake = FakeClaude()
    first = app.upload_file_claude(fake, "a.pdf", b"PDF")
    fake.expiry[first.id] = datetime.now(timezone.utc) - timedelta(days=1)  # die API liefert die Metadaten noch eine Weile
    assert app.upload_file_claude(fake, "a.pdf", b"PDF").id != first.id and len(fake.uploads) == 2


def test_file_alive_needs_the_minimum_lifetime_and_accepts_files_without_expiry(app):
    now = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)
    assert app.file_alive(SimpleNamespace(expires_at=None), now)
    assert app.file_alive(SimpleNamespace(), now)  # ohne das Feld ebenfalls
    assert app.file_alive(SimpleNamespace(expires_at=now + timedelta(seconds=app.CLAUDE_FILE_MIN_LEFT)), now)
    assert not app.file_alive(SimpleNamespace(expires_at=now + timedelta(seconds=app.CLAUDE_FILE_MIN_LEFT - 1)), now)
    assert app.file_alive(SimpleNamespace(expires_at=datetime(2026, 11, 20, 12, 0)), now)  # ohne Zeitzone gilt UTC
    assert not app.file_alive(SimpleNamespace(expires_at=datetime(2026, 11, 19, 12, 0)), now)


def test_the_minimum_lifetime_covers_a_whole_batch_and_stays_below_the_upload_lifetime(app):
    assert 24 * 3600 < app.CLAUDE_FILE_MIN_LEFT < app.CLAUDE_FILE_TTL
    assert 3600 <= app.CLAUDE_FILE_TTL <= 90 * 24 * 3600  # erlaubt laut Files API: 1 Stunde bis 90 Tage


# ---------- Ergebniszeilen ----------
def test_parse_claude_line_reads_text_tokens_and_model(app):
    line = result_line(text="Hallo Welt", input_tokens=10, cache_read=80, cache_creation=5, thinking=12, output=30)
    row = app.parse_claude_line(line, {"prompt-1": "Gruß?"})
    assert (row["key"], row["prompt"], row["text"], row["model"]) == (
        "prompt-1", "Gruß?", "Hallo Welt", "claude-sonnet-5-5")
    assert (row["finish"], row["error"]) == ("STOP", None)
    # Eingabe zählt alles (ohne Cache, aus dem Cache gelesen, in den Cache geschrieben), „aus dem Cache“ nur
    # das Gelesene
    assert (row["in"], row["cached"], row["think"], row["out"]) == (95, 80, 12, 18)
    assert row["usage"]["cache_creation_input_tokens"] == 5 and row["usage"]["output_tokens"] == 30


def test_parse_claude_line_ignores_thinking_blocks_and_joins_text_blocks(app):
    message = make_claude_message("Teil eins. ")
    message["content"] += [{"type": "redacted_thinking", "data": "xyz"}, {"type": "text", "text": "Teil zwei."}]
    row = app.parse_claude_line({"custom_id": "prompt-1", "result": {"type": "succeeded", "message": message}}, {})
    assert row["text"] == "Teil eins. Teil zwei." and row["error"] is None


def test_parse_claude_line_never_reports_more_thinking_than_output(app):
    row = app.parse_claude_line(result_line(thinking=50, output=30), {})
    assert (row["think"], row["out"]) == (50, 0)


def test_parse_claude_line_without_thinking_details_counts_everything_as_output(app):
    line = result_line(output=30)
    del line["result"]["message"]["usage"]["output_tokens_details"]
    row = app.parse_claude_line(line, {})
    assert (row["think"], row["out"]) == (0, 30)


def test_parse_claude_line_without_cache_fields_counts_only_the_plain_input(app):
    line = result_line(input_tokens=42)
    for field in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        del line["result"]["message"]["usage"][field]
    row = app.parse_claude_line(line, {})
    assert (row["in"], row["cached"]) == (42, 0)


@pytest.mark.parametrize("stop, finish", [
    ("end_turn", "STOP"), ("max_tokens", "MAX_TOKENS"), ("stop_sequence", "STOP_SEQUENCE"),
    ("model_context_window_exceeded", "MODEL_CONTEXT_WINDOW_EXCEEDED"), ("pause_turn", "PAUSE_TURN")])
def test_parse_claude_line_maps_the_stop_reasons(app, stop, finish):
    row = app.parse_claude_line(result_line(stop_reason=stop), {})
    assert row["finish"] == finish and row["error"] is None  # ein Text da: kein Fehler, auch bei MAX_TOKENS


def test_parse_claude_line_without_a_stop_reason_says_unknown(app):
    line = result_line()
    line["result"]["message"]["stop_reason"] = None
    assert app.parse_claude_line(line, {})["finish"] == "unbekannt"


def test_parse_claude_line_reports_errors_with_type_message_and_request_id(app):
    line = {"custom_id": "prompt-2", "result": claude_errored("invalid_request_error", "Stufe xhigh unbekannt", "req_9")}
    row = app.parse_claude_line(line, {"prompt-2": "B"})
    assert row["error"] == "invalid_request_error: Stufe xhigh unbekannt (request_id: req_9)"
    assert (row["text"], row["finish"], row["model"], row["in"], row["out"]) == ("", "unbekannt", "unbekannt", 0, 0)
    assert row["prompt"] == "B"


def test_claude_error_text_handles_odd_shapes(app):
    assert app.claude_error_text({"type": "error", "error": {"type": "overloaded_error", "message": "Zu voll"}}) == \
        "overloaded_error: Zu voll"
    assert app.claude_error_text({"type": "api_error", "message": "Kaputt"}) == "api_error: Kaputt"
    assert app.claude_error_text({"foo": "bär"}) == '{"foo": "bär"}'
    assert app.claude_error_text("nur Text") == "nur Text" and app.claude_error_text(None) == "None"


def test_parse_claude_line_reports_canceled_and_expired_requests_as_not_billed(app):
    canceled = app.parse_claude_line({"custom_id": "prompt-1", "result": {"type": "canceled"}}, {})
    expired = app.parse_claude_line({"custom_id": "prompt-2", "result": {"type": "expired"}}, {})
    assert canceled["error"].startswith("Abgebrochen") and "nicht berechnet" in canceled["error"]
    assert expired["error"].startswith("Abgelaufen") and "24-Stunden-Limit" in expired["error"]
    assert canceled["finish"] == expired["finish"] == "unbekannt" and canceled["text"] == expired["text"] == ""


def test_parse_claude_line_shows_a_refusal_as_the_reason_for_the_missing_text(app):
    refusal = {"category": "cyber", "explanation": "Dabei helfe ich nicht."}
    row = app.parse_claude_line(result_line(refusal=refusal), {})
    assert row["finish"] == "REFUSAL"
    assert row["error"] == "Das Modell hat abgelehnt (Kategorie: cyber): Dabei helfe ich nicht."
    bare = app.parse_claude_line(result_line(refusal={}), {})  # ohne Kategorie und Erklärung
    assert bare["error"] == "Das Modell hat abgelehnt."


def test_parse_claude_line_without_text_reports_the_finish_reason(app):
    row = app.parse_claude_line(result_line(text="", stop_reason="max_tokens"), {})
    assert row["finish"] == "MAX_TOKENS" and row["error"] == "Keine Antwort (Abschlussgrund: MAX_TOKENS)"


def test_parse_claude_line_of_an_unknown_result_type(app):
    assert app.parse_claude_line({"custom_id": "prompt-1", "result": {"type": "seltsam"}}, {})["error"] == \
        "Unbekanntes Ergebnis (seltsam)"
    assert app.parse_claude_line({"custom_id": "prompt-1"}, {})["error"] == "Unbekanntes Ergebnis (ohne Art)"
    assert app.parse_claude_line({}, {})["key"] == "?"


def test_sort_rows_orders_numerically_and_parse_results_still_does(app):
    keys = ["prompt-10", "prompt-2", "prompt-1"]
    assert [r["key"] for r in app.sort_rows([{"key": k} for k in keys])] == ["prompt-1", "prompt-2", "prompt-10"]
    raw = "\n".join(json.dumps({"key": k, "response": {}}) for k in keys).encode()
    assert [r["key"] for r in app.parse_results(raw, {})] == ["prompt-1", "prompt-2", "prompt-10"]


def test_the_sample_messages_match_the_sdk_schema():
    for args in ({}, {"cache_read": 50, "cache_creation": 7}, {"text": "", "stop_reason": "max_tokens"},
                 {"refusal": {"category": "bio", "explanation": "Nein"}}, {"refusal": {}}):
        Message.model_validate(make_claude_message(**args))
    for result in ({"type": "succeeded", "message": make_claude_message()}, claude_errored(), {"type": "expired"},
                   {"type": "canceled"}):
        MessageBatchIndividualResponse.model_validate({"custom_id": "prompt-1", "result": result})


# ---------- Status und Ergebnisse ----------
def test_fetch_claude_batch_while_running_loads_no_results(app):
    fake = FakeClaude(batch_status="in_progress")
    batch_id = started(fake, "prompt-1")
    assert app.fetch_claude_batch(fake, {"name": batch_id, "prompts": {}}) == ("in_progress", None, None, None)
    assert fake.results_calls == [] and fake.get_calls == 1


def test_fetch_claude_batch_canceling_is_not_final_and_loads_no_results(app):
    fake = FakeClaude(batch_status="canceling")
    batch_id = started(fake, "prompt-1")
    assert app.fetch_claude_batch(fake, {"name": batch_id, "prompts": {}})[:2] == ("canceling", None)
    assert fake.results_calls == []


def test_fetch_claude_batch_ended_reads_the_results_in_numeric_order(app):
    fake = FakeClaude(batch_text="Antwort", batch_cached=64)
    batch_id = started(fake, "prompt-10", "prompt-2", "prompt-1")  # der Dienst ordnet die Ergebnisse beliebig
    prompts = {"prompt-1": "A", "prompt-2": "B", "prompt-10": "C"}
    state, rows, error, model = app.fetch_claude_batch(fake, {"name": batch_id, "prompts": prompts})
    assert (state, error, model) == ("ended", None, "claude-sonnet-5-5")
    assert [(r["key"], r["prompt"]) for r in rows] == [("prompt-1", "A"), ("prompt-2", "B"), ("prompt-10", "C")]
    assert all(r["text"] == "Antwort" and r["cached"] == 64 for r in rows) and fake.results_calls == [batch_id]


def test_fetch_claude_batch_mixes_answers_errors_and_expired_requests(app):
    fake = FakeClaude(failing={"prompt-2": claude_errored("overloaded_error", "Zu voll"), "prompt-3": {"type": "expired"}})
    batch_id = started(fake, "prompt-1", "prompt-2", "prompt-3")
    state, rows, error, model = app.fetch_claude_batch(fake, {"name": batch_id, "prompts": {}})
    assert state == "ended" and error is None and model == "claude-sonnet-5-5"
    assert [bool(r["text"]) for r in rows] == [True, False, False]
    assert rows[1]["error"].startswith("overloaded_error: Zu voll") and rows[2]["error"].startswith("Abgelaufen")


def test_fetch_claude_batch_without_a_single_answer_has_no_model(app):
    fake = FakeClaude(failing={"prompt-1": claude_errored(), "prompt-2": {"type": "canceled"}})
    batch_id = started(fake, "prompt-1", "prompt-2")
    state, rows, error, model = app.fetch_claude_batch(fake, {"name": batch_id, "prompts": {}})
    assert state == "ended" and model is None and len(rows) == 2 and all(r["error"] for r in rows)


def test_fetch_claude_batch_of_an_empty_result_list_gives_no_rows(app):
    fake = FakeClaude()
    batch_id = started(fake)  # keine Anfragen, also keine Ergebnisse
    assert app.fetch_claude_batch(fake, {"name": batch_id, "prompts": {}}) == ("ended", None, None, None)


def test_only_ended_counts_as_done_for_claude(app):
    assert "ended" in app.DONE
    assert not {"in_progress", "canceling"} & app.DONE


def test_cancel_batch_calls_the_messages_batches_api_for_claude_entries(app):
    fake = FakeClaude(batch_status="in_progress")
    app.cancel_batch(fake, claude_entry())
    assert fake.cancelled == ["msgbatch_01abc123def456"]


# ---------- Echter SDK-Code, nur das HTTP ist abgefangen ----------
def http_log(responder):
    """Handler für real_claude_client(): zeichnet jede Anfrage auf, responder(request) liefert die Antwort."""
    seen = []

    def handler(request):
        seen.append(SimpleNamespace(method=request.method, path=request.url.path, headers=request.headers,
                                    body=request.read()))
        return responder(request)
    return seen, handler


def test_the_real_sdk_sends_the_expected_http_requests_for_the_upload_and_the_batch(app):
    def responder(request):
        return json_response(file_json("file_abc") if request.url.path == "/v1/files" else batch_json("msgbatch_x"))

    seen, handler = http_log(responder)
    client = real_claude_client(handler)
    f = app.upload_file_claude(client, "Buch: Teil 1.pdf", b"%PDF-1.7")
    batch_id, keyed = app.start_claude_batch(client, "claude-sonnet-5-5", [f], ["Frage 1", "Frage 2"], "Sei kurz.",
                                             "xhigh", 2048, cache=True)
    assert batch_id == "msgbatch_x" and keyed == {"prompt-1": "Frage 1", "prompt-2": "Frage 2"}
    upload, create = seen
    assert (upload.method, upload.path) == ("POST", "/v1/files")
    assert b'name="expires_in_seconds"' in upload.body and b"259200" in upload.body  # 3 Tage
    assert b'filename="Buch- Teil 1.pdf"' in upload.body and b"Content-Type: application/pdf" in upload.body
    assert b"%PDF-1.7" in upload.body
    assert (create.method, create.path) == ("POST", "/v1/messages/batches")
    body = json.loads(create.body)
    assert [r["custom_id"] for r in body["requests"]] == ["prompt-1", "prompt-2"]
    assert body["requests"][1]["params"] == {
        "model": "claude-sonnet-5-5", "max_tokens": 2048, "system": "Sei kurz.", "output_config": {"effort": "xhigh"},
        "messages": [{"role": "user", "content": [
            {"type": "document", "source": {"type": "file", "file_id": "file_abc"}, "cache_control": CACHE},
            {"type": "text", "text": "Frage 2"}]}]}
    # Files API und Message Batches API brauchen laut Doku keinen Beta-Header: Der Test hält diese Annahme fest
    assert not any("anthropic-beta" in r.headers for r in seen)


def test_the_real_sdk_checks_a_remembered_file_with_one_get_and_uploads_again_after_a_404(app, home):
    (home / "data").mkdir(parents=True, exist_ok=True)
    (home / "data" / "claude_files.json").write_text(
        json.dumps({hashlib.sha256(b"PDF").hexdigest(): "file_old"}), "utf-8")
    state = {"old_exists": True}

    def responder(request):
        if request.method == "POST":
            return json_response(file_json("file_new"))
        if request.url.path == "/v1/files/file_old" and state["old_exists"]:
            return json_response(file_json("file_old"))
        return json_response({"type": "error", "error": {"type": "not_found_error", "message": "File not found"}}, 404)

    seen, handler = http_log(responder)
    client = real_claude_client(handler)
    assert app.upload_file_claude(client, "a.pdf", b"PDF").id == "file_old"
    assert [(r.method, r.path) for r in seen] == [("GET", "/v1/files/file_old")]  # nur geprüft, nicht hochgeladen
    state["old_exists"] = False
    assert app.upload_file_claude(client, "a.pdf", b"PDF").id == "file_new"
    assert [(r.method, r.path) for r in seen[1:]] == [("GET", "/v1/files/file_old"), ("POST", "/v1/files")]
    assert json.loads((home / "data" / "claude_files.json").read_text("utf-8")) == {
        hashlib.sha256(b"PDF").hexdigest(): "file_new"}


def test_the_real_sdk_reads_status_results_and_cancel_over_http(app):
    lines = [result_line("prompt-1", text="Hallo", input_tokens=10, cache_read=90, thinking=12, output=30),
             {"custom_id": "prompt-2", "result": claude_errored("invalid_request_error", "xhigh unbekannt", "req_7")},
             {"custom_id": "prompt-3", "result": {"type": "expired"}}]
    state = {"status": "in_progress"}

    def responder(request):
        if request.url.path.endswith("/results"):
            return jsonl_response(lines)
        if request.url.path.endswith("/cancel"):
            return json_response(batch_json("msgbatch_x", "canceling", processing=3))
        return json_response(batch_json("msgbatch_x", state["status"], succeeded=1, errored=1, expired=1)
                             if state["status"] == "ended" else batch_json("msgbatch_x", "in_progress", processing=3))

    seen, handler = http_log(responder)
    client = real_claude_client(handler)
    j = {"name": "msgbatch_x", "prompts": {"prompt-1": "A", "prompt-2": "B", "prompt-3": "C"}}
    assert app.fetch_claude_batch(client, j) == ("in_progress", None, None, None)
    assert [(r.method, r.path) for r in seen] == [("GET", "/v1/messages/batches/msgbatch_x")]  # noch keine Ergebnisse
    state["status"] = "ended"
    status, rows, error, model = app.fetch_claude_batch(client, j)
    assert (status, error, model) == ("ended", None, "claude-sonnet-5-5") and len(rows) == 3
    assert (rows[0]["text"], rows[0]["prompt"], rows[0]["in"], rows[0]["cached"], rows[0]["think"], rows[0]["out"]) == (
        "Hallo", "A", 100, 90, 12, 18)
    assert rows[1]["error"] == "invalid_request_error: xhigh unbekannt (request_id: req_7)"
    assert rows[2]["error"].startswith("Abgelaufen")
    assert (seen[-1].method, seen[-1].path) == ("GET", "/v1/messages/batches/msgbatch_x/results")
    app.cancel_batch(client, claude_entry(name="msgbatch_x"))
    assert (seen[-1].method, seen[-1].path) == ("POST", "/v1/messages/batches/msgbatch_x/cancel")


def test_a_missing_batch_raises_an_error_that_carries_the_http_status_the_app_checks(app):
    def responder(request):
        return json_response({"type": "error", "error": {"type": "not_found_error", "message": "Batch not found"}}, 404)

    client = real_claude_client(http_log(responder)[1])
    with pytest.raises(Exception) as caught:
        app.fetch_claude_batch(client, {"name": "msgbatch_gone", "prompts": {}})
    assert caught.value.status_code == 404 and "Batch not found" in str(caught.value)  # daran erkennt views.job_panel es


# ---------- Oberfläche: Anbieter und Formular ----------
@ui
def test_claude_shows_its_own_defaults_and_no_mode_switch(use_claude):
    use_claude()
    at = new_claude_app()
    at.run()
    assert not at.exception and not at.error
    assert model_field(at).value == "claude-fable-5-2"  # vorausgewählt ist das teuerste Modell (Issue #11)
    assert not [r for r in at.radio if r.key == "mode"]  # mit Claude gibt es nur Batch
    effort = at.selectbox(key="effort_claude")
    assert effort.value == "Standard" and effort.options == ["Standard", "low", "medium", "high", "xhigh", "max"]
    assert at.number_input(key="max_claude").value == 32768 and at.number_input(key="max_claude").max == 128000
    assert at.checkbox(key="cache_claude").value is False  # der Prompt-Cache ist eine bewusste Entscheidung
    assert not [s for s in at.selectbox if s.key in ("think", "effort")]
    assert not [n for n in at.number_input if n.key in ("max_batch", "max_bg", "max_openai")]
    assert any("Mit Claude läuft nur der Batch-Modus" in c and "innerhalb einer Stunde" in c
               and "„Hintergrund“ ist Gemini vorbehalten" in c for c in captions(at))
    assert not button(at, "Batch starten").disabled and not [b for b in at.button if b.label == "Im Hintergrund starten"]
    name_field = at.text_input(key="label_claude")  # ohne Namensvergabe zeigt der Platzhalter den Standardnamen
    assert name_field.value == "" and name_field.placeholder.startswith("claude-")


@ui
def test_only_the_claude_form_shows_the_prompt_cache_option(use_gemini, use_openai, use_claude):
    use_gemini(), use_openai(), use_claude()
    at = new_app()
    at.run()
    assert not [c for c in at.checkbox if c.key == "cache_claude"]
    at.radio(key="provider").set_value(PROVIDER_OPENAI)
    at.run()
    assert not [c for c in at.checkbox if c.key == "cache_claude"]
    at.radio(key="provider").set_value(PROVIDER_CLAUDE)
    at.run()
    assert not at.exception and [c.label for c in at.checkbox if c.key == "cache_claude"] == [
        "Dateien im Prompt-Cache halten (1 Stunde)"]


@ui
def test_the_provider_radio_offers_all_three_providers_in_order(use_gemini):
    use_gemini()
    at = new_app()
    at.run()
    assert at.radio(key="provider").options == [PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE]


@ui
def test_switching_the_provider_in_the_sidebar_swaps_the_form_to_claude_and_back(use_gemini, use_claude):
    use_gemini()
    use_claude()
    at = new_app()
    at.run()
    at.radio(key="provider").set_value(PROVIDER_CLAUDE)
    at.run()
    assert not at.exception and at.selectbox(key="effort_claude").value == "Standard"
    assert not [r for r in at.radio if r.key == "mode"] and not [s for s in at.selectbox if s.key == "think"]
    assert model_field(at).value == "claude-fable-5-2"
    at.radio(key="provider").set_value(PROVIDER_GEMINI)
    at.run()
    assert not at.exception and at.selectbox(key="think").value == "high" and at.radio(key="mode").value == MODE_BATCH
    assert model_field(at).value == "gemini-4-carbon"
    assert not [s for s in at.selectbox if s.key == "effort_claude"]


@ui
def test_claude_without_its_key_asks_for_it(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    at = new_claude_app()
    at.run()
    assert not at.exception and not at.button
    assert any("Claude API-Key" in i.value and "ANTHROPIC_API_KEY" in i.value for i in at.info)


@ui
def test_a_missing_claude_key_does_not_block_the_other_providers(monkeypatch, use_gemini, use_openai):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    use_gemini(), use_openai()
    at = new_app()
    at.run()
    assert not at.exception and not any("API-Key" in i.value for i in at.info) and button(at, "Batch starten")
    at.radio(key="provider").set_value(PROVIDER_OPENAI)
    at.run()
    assert not at.exception and not any("API-Key" in i.value for i in at.info) and button(at, "Batch starten")


@ui
def test_the_claude_key_from_the_environment_is_prefilled_and_can_be_replaced(use_claude):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    field = [t for t in at.text_input if t.label == "Claude API-Key"][0]
    assert field.value == "test-claude-key" and fake.client_kwargs[-1] == {"api_key": "test-claude-key"}
    field.set_value("sk-ant-neu")
    at.run()
    assert fake.client_kwargs[-1] == {"api_key": "sk-ant-neu"}


@ui
def test_a_missing_claude_package_is_reported_instead_of_crashing(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    at = new_claude_app()
    at.run()
    assert not at.exception and any("pip install" in e.value for e in at.error) and not at.button


# ---------- Oberfläche: Formularwerte beim Anbieterwechsel ----------
# Wie bei OpenAI (siehe test_openai.py): Streamlit vergisst den Wert eines Widgets, das einen Lauf lang fehlt. Diese Tests
# prüfen, was die App dem Browser schickt (set_value samt Wert), nicht nur den Wert im Backend.
@ui
def test_the_default_model_is_shown_again_after_a_visit_to_claude_without_its_key(use_gemini, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # mit leerem Key endet der Claude-Lauf hinter der Seitenleiste
    use_gemini()
    at = new_app()
    at.run()
    at.radio(key="provider").set_value(PROVIDER_CLAUDE)
    at.run()
    assert any("ANTHROPIC_API_KEY" in i.value for i in at.info) and not at.button
    at.radio(key="provider").set_value(PROVIDER_GEMINI)
    at.run()
    assert not at.exception
    sent_to_browser(at.selectbox(key="model_gemini"), "gemini-4-carbon")
    assert at.number_input(key="max_batch").proto.value == 32768
    sent_to_browser(at.selectbox(key="think"), "high")


@ui
def test_each_provider_keeps_its_own_settings_when_claude_joins_the_switching(use_gemini, use_openai, use_claude):
    use_gemini(), use_openai(), use_claude()
    at = new_app()
    at.run()
    at.selectbox(key="think").set_value("low")
    at.number_input(key="max_batch").set_value(4096)
    at.run()
    at.radio(key="provider").set_value(PROVIDER_OPENAI)
    at.run()
    at.selectbox(key="model_openai").set_value("gpt-6-luna")
    at.selectbox(key="effort").set_value("high")
    at.run()
    at.radio(key="provider").set_value(PROVIDER_CLAUDE)
    at.run()
    at.selectbox(key="model_claude").set_value("claude-opus-5-5")
    at.selectbox(key="effort_claude").set_value("xhigh")
    at.number_input(key="max_claude").set_value(65536)
    at.checkbox(key="cache_claude").set_value(True)
    at.run()
    for _ in range(2):  # zweimal rund durch alle drei: Jeder behält seine eigenen Werte
        for provider in (PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE):
            at.radio(key="provider").set_value(provider)
            at.run()
            assert not at.exception
            if provider == PROVIDER_GEMINI:
                sent_to_browser(at.selectbox(key="think"), "low")
                sent_to_browser(at.number_input(key="max_batch"), 4096)
            elif provider == PROVIDER_OPENAI:
                sent_to_browser(at.selectbox(key="model_openai"), "gpt-6-luna")
                sent_to_browser(at.selectbox(key="effort"), "high")
            else:
                sent_to_browser(at.selectbox(key="model_claude"), "claude-opus-5-5")
                sent_to_browser(at.selectbox(key="effort_claude"), "xhigh")
                sent_to_browser(at.number_input(key="max_claude"), 65536)
                sent_to_browser(at.checkbox(key="cache_claude"), True)


@ui
def test_the_claude_settings_survive_a_run_without_the_claude_key(use_claude, monkeypatch):
    use_claude()
    at = new_claude_app()
    at.run()
    at.selectbox(key="effort_claude").set_value("max")
    at.checkbox(key="cache_claude").set_value(True)
    at.run()
    [t for t in at.text_input if t.label == "Claude API-Key"][0].set_value("")  # Formular fehlt einen Lauf lang
    at.run()
    assert not at.button
    [t for t in at.text_input if t.label == "Claude API-Key"][0].set_value("sk-ant-neu")
    at.run()
    assert not at.exception
    sent_to_browser(at.selectbox(key="effort_claude"), "max")
    sent_to_browser(at.checkbox(key="cache_claude"), True)
    assert at.number_input(key="max_claude").proto.value == 32768


# ---------- Oberfläche: Start ----------
@ui
def test_claude_batch_start_uploads_the_files_and_stores_the_entry(use_claude, home, app):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("Buch 1.pdf", b"PDF-1", PDF), ("Buch 2.pdf", b"PDF-2", PDF)])
    at.text_area(key="system").set_value("Sei kurz.")
    at.selectbox(key="effort_claude").set_value("high")
    at.number_input(key="max_claude").set_value(4096)
    set_prompts(at, "Erster Prompt\n---\nZweiter Prompt")
    click(at, "Batch starten")
    assert not at.exception and not at.error and "läuft" in at.success[0].value
    assert fake.uploads == [b"PDF-1", b"PDF-2"] and fake.upload_names == ["Buch 1.pdf", "Buch 2.pdf"]
    assert fake.upload_mimes == [PDF, PDF] and fake.created_batches == [{"count": 2}]
    first, second = fake.batch_requests
    assert (first["custom_id"], second["custom_id"]) == ("prompt-1", "prompt-2")
    params = first["params"]
    assert params["model"] == "claude-fable-5-2" and params["system"] == "Sei kurz."  # die Voreinstellung
    assert params["output_config"] == {"effort": "high"} and params["max_tokens"] == 4096
    assert [b.get("source", {}).get("file_id") or b["text"] for b in params["messages"][0]["content"]] == [
        "file_fake000001", "file_fake000002", "Erster Prompt"]
    assert second["params"]["messages"][0]["content"][-1]["text"] == "Zweiter Prompt"
    entry = read_history(home)[0]
    assert entry["provider"] == PROVIDER_CLAUDE and entry["name"] == "msgbatch_fake000001" and "state" not in entry
    assert (entry["model"], entry["think"], entry["max_out"], entry["cache"]) == (
        "claude-fable-5-2", "high", 4096, False)
    assert entry["pdf"] == "Buch 1.pdf, Buch 2.pdf" and entry["pdfs"] == ["Buch 1.pdf", "Buch 2.pdf"]
    assert entry["system"] == "Sei kurz."
    assert entry["prompts"] == {"prompt-1": "Erster Prompt", "prompt-2": "Zweiter Prompt"}
    assert at.session_state["sel"] == app.entry_label(entry)
    assert (home / "data" / "claude_files.json").exists() and list((home / "data").glob("requests_claude_*.jsonl"))
    assert not (home / "data" / "pdf_files.json").exists() and not (home / "data" / "openai_files.json").exists()


@ui
def test_claude_standard_effort_and_an_empty_system_prompt_send_neither(use_claude):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    params = fake.batch_requests[0]["params"]
    assert "output_config" not in params and "system" not in params and params["max_tokens"] == 32768
    assert params["messages"][0]["content"] == [{"type": "text", "text": "Frage"}]  # ohne Datei: nur der Prompt


@ui
def test_the_model_field_decides_which_claude_model_is_used(use_claude, home):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    model_field(at).set_value("claude-haiku-5-5")  # aus der Liste gewählt
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert fake.batch_requests[0]["params"]["model"] == "claude-haiku-5-5"
    assert read_history(home)[0]["model"] == "claude-haiku-5-5"


@ui
def test_identical_files_are_uploaded_to_claude_only_once(use_claude):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("Original.pdf", b"GLEICH", PDF), ("Kopie.pdf", b"GLEICH", PDF)])
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert fake.uploads == [b"GLEICH"]
    assert len(fake.batch_requests[0]["params"]["messages"][0]["content"]) == 2  # ein Dokument und der Prompt


@ui
def test_a_failing_claude_start_shows_the_error_and_stores_nothing(use_claude, home):
    use_claude(create_error=ClaudeError(400, "Ungültige Anfrage"))
    at = new_claude_app()
    at.run()
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and any("Start fehlgeschlagen" in e.value and "Ungültige Anfrage" in e.value for e in at.error)
    assert read_history(home) == []


@ui
def test_a_failing_file_upload_to_claude_shows_the_error_and_stores_nothing(use_claude, home):
    fake = use_claude(upload_error=ClaudeError(413, "Datei zu groß"))
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("a.pdf", b"X", PDF)])
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert any("Start fehlgeschlagen" in e.value and "Datei zu groß" in e.value for e in at.error)
    assert read_history(home) == [] and fake.created_batches == []


@ui
def test_claude_batch_start_sends_pdf_text_csv_and_images_in_the_order_shown(use_claude, home):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("Bericht.pdf", b"PDF", PDF), ("Foto.png", b"PNG", "image/png"),
                                   ("Notiz.md", b"# Hallo", "text/markdown"), ("Zahlen.csv", b"a,b", "text/csv")])
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error and "läuft" in at.success[0].value
    assert fake.upload_names == ["Bericht.pdf", "Foto.png", "Notiz.md", "Zahlen.csv"]
    assert fake.upload_mimes == [PDF, "image/png", "text/plain", "text/plain"]  # Text und CSV gehen als text/plain
    content = fake.batch_requests[0]["params"]["messages"][0]["content"]
    assert [(b["type"], b.get("source", {}).get("file_id")) for b in content] == [
        ("document", "file_fake000001"), ("image", "file_fake000002"), ("document", "file_fake000003"),
        ("document", "file_fake000004"), ("text", None)]
    assert read_history(home)[0]["pdf"] == "Bericht.pdf, Foto.png, Notiz.md, Zahlen.csv"  # alle Dateinamen


@ui
def test_claude_blocks_the_start_for_office_files_audio_and_video_and_names_the_files(use_claude):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    at.file_uploader[0].set_value([("Bericht.docx", b"DOCX", docx), ("Buch.pdf", b"PDF", PDF),
                                   ("Ton.mp3", b"MP3", "audio/mpeg")])
    set_prompts(at, "Frage")
    assert len(at.error) == 1
    message = at.error[0].value
    assert "Bericht.docx" in message and "Ton.mp3" in message and "Buch.pdf" not in message
    assert ".docx-Dateien nimmt Claude nicht an" in message and "Exportiere sie als PDF" in message
    assert "Audio nimmt Claude nicht an, nur Gemini" in message and "Der Start ist gesperrt" in message
    assert button(at, "Batch starten").disabled
    at.file_uploader[0].set_value([("Buch.pdf", b"PDF", PDF)])  # die Dateien weg, die Claude nicht annimmt
    at.run()
    assert not at.error and not button(at, "Batch starten").disabled
    assert fake.uploads == []  # bis hierher wurde nichts hochgeladen


@ui
def test_the_same_word_file_is_fine_for_gemini_and_openai_and_blocked_only_while_claude_is_selected(
        use_gemini, use_openai, use_claude):
    use_gemini(), use_openai(), use_claude()
    at = new_app()
    at.session_state["auto_name"] = False
    at.run()
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    at.file_uploader[0].set_value([("Bericht.docx", b"DOCX", docx)])
    set_prompts(at, "Frage")
    assert not at.error and not button(at, "Batch starten").disabled  # Gemini nimmt Word an
    at.radio(key="provider").set_value(PROVIDER_OPENAI)
    at.run()
    assert not at.error and not button(at, "Batch starten").disabled  # OpenAI auch
    at.radio(key="provider").set_value(PROVIDER_CLAUDE)
    at.run()
    assert len(at.error) == 1 and button(at, "Batch starten").disabled
    assert [f.name for f in at.file_uploader[0].value] == ["Bericht.docx"]  # der Anbieterwechsel verwirft die Datei nicht
    at.radio(key="provider").set_value(PROVIDER_GEMINI)
    at.run()
    assert not at.error and not button(at, "Batch starten").disabled


@ui
def test_the_hint_without_a_file_names_what_claude_takes(use_claude, use_gemini):
    use_claude(), use_gemini()
    at = new_claude_app()
    at.run()
    [hint] = [c for c in captions(at) if c.startswith("Keine Datei angehängt")]
    assert "PDF, Text (auch CSV) und Bilder" in hint and "Word" not in hint and "Audio" not in hint
    at.radio(key="provider").set_value(PROVIDER_GEMINI)
    at.run()
    [hint] = [c for c in captions(at) if c.startswith("Keine Datei angehängt")]
    assert "Word" in hint and "Audio und Video" in hint


@ui
def test_the_file_uploader_help_lists_the_extensions_claude_does_not_take(use_claude):
    use_claude()
    at = new_claude_app()
    at.run()
    assert "Nicht bei Claude: .docx" in at.file_uploader[0].proto.help


# ---------- Oberfläche: Prompt-Cache ----------
@ui
def test_the_prompt_cache_option_marks_the_last_file_and_is_stored_in_the_entry(use_claude, home):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("Buch 1.pdf", b"PDF-1", PDF), ("Buch 2.pdf", b"PDF-2", PDF)])
    at.checkbox(key="cache_claude").set_value(True)
    set_prompts(at, "Erster Prompt\n---\nZweiter Prompt")
    click(at, "Batch starten")
    assert not at.exception and not at.error
    for request in fake.batch_requests:  # jede Anfrage trägt dieselbe Marke an derselben Stelle
        assert [b.get("cache_control") for b in request["params"]["messages"][0]["content"]] == [None, CACHE, None]
    assert read_history(home)[0]["cache"] is True
    at.run()
    assert any("Batch (Claude)" in c and "Prompt-Cache (1 Stunde)" in c for c in captions(at))


@ui
def test_without_the_prompt_cache_option_no_request_carries_a_marker(use_claude, home):
    fake = use_claude()
    at = new_claude_app()
    at.run()
    at.file_uploader[0].set_value([("Buch.pdf", b"PDF", PDF)])
    set_prompts(at, "Erster Prompt\n---\nZweiter Prompt")
    click(at, "Batch starten")
    assert "cache_control" not in json.dumps(fake.batch_requests)
    assert read_history(home)[0]["cache"] is False
    at.run()  # beide Tabs werden gezeichnet: Die Zeile des Eintrags im Jobs-Tab nennt den Cache nur, wenn er an war
    assert any("Batch (Claude)" in c for c in captions(at))
    assert not any("Batch (Claude)" in c and "Prompt-Cache" in c for c in captions(at))


# ---------- Oberfläche: Namensvergabe ----------
@ui
def test_a_claude_run_is_named_with_gemini_and_the_form_says_so(use_gemini, use_claude, home):
    gemini, claude_fake = use_gemini(name_text="Vertrag auf Fristen prüfen"), use_claude()
    at = new_claude_app(auto_name=True)
    at.run()
    assert any("an Google" in c and "Claude-Lauf" in c for c in captions(at))  # der Auszug verlässt Claude
    at.text_input(key="label_claude").set_value("Eigener Name")
    at.run()
    assert not any("an Google" in c for c in captions(at))  # mit eigenem Namen geht nichts an Google
    at.text_input(key="label_claude").set_value("")
    set_prompts(at, "Prüfe den Vertrag auf Fristen")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    entry = read_history(home)[0]
    assert entry["provider"] == PROVIDER_CLAUDE and entry["label"] == "Vertrag auf Fristen prüfen"
    assert gemini.name_calls[0]["contents"] == "Prüfe den Vertrag auf Fristen"
    assert len(claude_fake.created_batches) == 1
    assert "Vertrag auf Fristen prüfen" not in json.dumps(claude_fake.batch_requests, ensure_ascii=False)  # nur lokal


@ui
def test_without_a_gemini_key_a_claude_run_gets_the_default_name(use_claude, monkeypatch, home):
    monkeypatch.setenv("GEMINI_API_KEY", "")  # kein Gemini-Client, die Namensvergabe fällt still aus
    use_claude()
    at = new_claude_app(auto_name=True)
    at.run()
    assert not at.exception and any("Ohne Gemini API-Key" in c for c in captions(at))
    assert at.text_input(key="label_claude").placeholder.startswith("claude-")
    assert not any("an Google" in c for c in captions(at))
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and not at.error and not at.warning
    assert re.fullmatch(r"claude-\d{8}-\d{4}(-\d+)?", read_history(home)[0]["label"])


# ---------- Oberfläche: Jobs-Tab ----------
@ui
def test_the_jobs_tab_names_the_provider_of_a_claude_entry(use_claude, home):
    write_history(home, [finished_claude_batch(think="xhigh", max_out=65536)])
    use_claude()
    at = new_claude_app(TAB_JOBS)
    at.run()
    assert not at.exception
    assert any("Batch (Claude)" in c and "Modell claude-sonnet-5-5, Denktiefe xhigh, max. 65536 Ausgabe-Token" in c
               for c in captions(at))


@ui
def test_a_finished_claude_batch_is_saved_locally_and_reopens_without_the_api(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(batch_cached=64)
    fake.batch_requests = requests("prompt-1")  # der Fake liefert Ergebnisse zu den „gesendeten“ Anfragen
    at = new_claude_app(TAB_JOBS)
    at.run()
    at.run()
    saved = read_history(home)[0]
    assert saved["state"] == "ended" and saved["api_model"] == "claude-sonnet-5-5"
    assert saved["rows"][0]["cached"] == 64 and saved["rows"][0]["text"] == "Claude-Antwort prompt-1"
    assert saved["rows"][0]["in"] == 164 and saved["rows"][0]["think"] == 10 and saved["rows"][0]["out"] == 15

    broken = use_claude(get_error=ClaudeError(500))  # neue Sitzung, API unbrauchbar: darf nicht gefragt werden
    again = new_claude_app(TAB_JOBS)
    again.run()
    assert broken.get_calls == 0 and not again.error and not again.exception
    assert any("Gesichertes Endergebnis" in c for c in captions(again))
    assert "Claude-Antwort prompt-1" in markdown(again)
    assert fake.get_calls >= 1


@ui
def test_a_running_claude_batch_is_polled_and_shows_its_claude_status(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(batch_status="in_progress")
    at = new_claude_app(TAB_JOBS)
    at.run()
    assert not at.exception and fake.get_calls >= 1 and fake.results_calls == []
    assert any("Automatische Prüfung" in c for c in captions(at))
    assert any("in_progress" in m for m in markdown(at))
    assert "state" not in read_history(home)[0]  # kein Endzustand: nichts gesichert


@ui
def test_a_batch_that_is_being_canceled_keeps_polling_until_it_ends(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(batch_status="canceling")
    at = new_claude_app(TAB_JOBS)
    at.run()
    assert not at.exception and any("canceling" in m for m in markdown(at))
    assert any("Automatische Prüfung" in c for c in captions(at)) and "state" not in read_history(home)[0]


@ui
def test_an_ended_claude_batch_keeps_answers_errors_and_expired_requests(use_claude, home):
    write_history(home, [claude_entry(prompts={"prompt-1": "A", "prompt-2": "B", "prompt-3": "C"})])
    fake = use_claude(failing={"prompt-2": claude_errored("overloaded_error", "Zu voll"),
                               "prompt-3": {"type": "expired"}})
    fake.batch_requests = requests("prompt-1", "prompt-2", "prompt-3")
    at = new_claude_app(TAB_JOBS)
    at.run()
    at.run()
    saved = read_history(home)[0]
    assert saved["state"] == "ended" and [bool(r["text"]) for r in saved["rows"]] == [True, False, False]
    assert saved["rows"][1]["error"].startswith("overloaded_error: Zu voll")
    assert saved["rows"][2]["error"].startswith("Abgelaufen")
    assert not at.exception and any("Zu voll" in e.value for e in at.error)


@ui
def test_a_truncated_claude_answer_gets_the_usual_warning(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(answers={"prompt-1": {"stop_reason": "max_tokens"}})
    fake.batch_requests = requests("prompt-1")
    at = new_claude_app(TAB_JOBS)
    at.run()
    at.run()
    assert read_history(home)[0]["rows"][0]["finish"] == "MAX_TOKENS"
    assert any(w.value == "Abgeschnitten: Denk- und Ausgabe-Token haben das Limit erreicht." for w in at.warning)
    assert not any("Ein Gemini-Batch ist auf" in c for c in captions(at))  # der Gemini-Hinweis gehört nicht hierher


@ui
def test_a_refused_claude_answer_shows_the_reason_and_the_finish_warning(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(answers={"prompt-1": {"refusal": {"category": "cyber", "explanation": "Dabei helfe ich nicht."}}})
    fake.batch_requests = requests("prompt-1")
    at = new_claude_app(TAB_JOBS)
    at.run()
    at.run()
    row = read_history(home)[0]["rows"][0]
    assert row["finish"] == "REFUSAL" and row["text"] == ""
    assert any(e.value == "Das Modell hat abgelehnt (Kategorie: cyber): Dabei helfe ich nicht." for e in at.error)
    assert any("„REFUSAL“" in w.value for w in at.warning)


@ui
def test_a_vanished_claude_batch_stops_the_polling(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(get_error=ClaudeError(404, "No such batch"))
    at = new_claude_app(TAB_JOBS)
    at.run()
    assert any("Abruf fehlgeschlagen" in e.value and "gestoppt" in e.value for e in at.error)
    at.run()
    assert fake.get_calls == 1  # 404 ist endgültig: kein weiterer Versuch


@ui
def test_the_cancel_button_calls_the_claude_api(use_claude, home):
    write_history(home, [claude_entry()])
    fake = use_claude(batch_status="in_progress")
    at = new_claude_app(TAB_JOBS)
    at.run()
    click(at, "Batch abbrechen")
    assert fake.cancelled == ["msgbatch_01abc123def456"] and any("Abbruch angefordert" in w.value for w in at.warning)


@ui
def test_each_entry_is_queried_with_the_client_of_its_own_provider_among_three(use_claude, use_openai, use_gemini, home):
    write_history(home, [claude_entry()])
    claude_fake = use_claude(batch_status="in_progress")
    openai_fake, gemini_fake = use_openai(), use_gemini()
    at = new_app(TAB_JOBS)  # als Anbieter für neue Anfragen ist Gemini gewählt
    at.run()
    assert not at.exception and claude_fake.get_calls >= 1 and gemini_fake.get_calls == 0
    assert openai_fake.get_calls == 0 and claude_fake.client_kwargs[-1] == {"api_key": "test-claude-key"}

    write_history(home, [batch_entry()])
    claude_fake.get_calls = 0
    other = new_claude_app(TAB_JOBS)  # umgekehrt: Claude gewählt, der Eintrag stammt von Gemini
    other.run()
    assert not other.exception and gemini_fake.get_calls >= 1 and claude_fake.get_calls == 0


@ui
def test_a_missing_key_of_the_entrys_provider_locks_status_check_and_cancel_for_claude(use_gemini, monkeypatch, home):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    write_history(home, [claude_entry()])
    use_gemini()  # ein Claude-Client darf nicht gebaut werden: Der Schutz in conftest.py würde anschlagen
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    assert any("Claude API-Key fehlt" in w.value for w in at.warning)
    assert button(at, "Status prüfen / Ergebnisse laden").disabled and button(at, "Batch abbrechen").disabled
    assert not any("Automatische Prüfung" in c for c in captions(at))


@ui
def test_saved_results_of_a_claude_entry_stay_visible_without_its_key(use_gemini, monkeypatch, home):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    write_history(home, [finished_claude_batch()])
    use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and "Gesicherte Antwort" in markdown(at)
    assert any("Gesichertes Endergebnis" in c for c in captions(at))


# ---------- Oberfläche: Eingaben übernehmen und Gespräch fortsetzen ----------
@ui
def test_reuse_inputs_of_a_claude_entry_switches_to_claude_and_restores_the_settings(use_claude, use_gemini, home):
    entry = claude_entry(think="xhigh", system="Kurz.", max_out=65536, model="claude-opus-5-5", cache=True,
                         prompts={"prompt-1": "Eins"})
    write_history(home, [entry])
    use_claude()
    use_gemini()
    at = new_app(TAB_JOBS)  # Gemini ist gewählt: Das Übernehmen muss den Anbieter umschalten
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.session_state["view"] == TAB_NEW
    assert at.radio(key="provider").value == PROVIDER_CLAUDE
    assert model_field(at).value == "claude-opus-5-5"
    assert at.selectbox(key="effort_claude").value == "xhigh" and at.number_input(key="max_claude").value == 65536
    assert at.checkbox(key="cache_claude").value is True
    assert at.text_area(key="raw").value == "Eins" and at.text_area(key="system").value == "Kurz."
    assert not [r for r in at.radio if r.key == "mode"]


@ui
def test_reuse_inputs_of_a_claude_entry_without_the_cache_field_turns_the_option_off(use_claude, use_gemini, home):
    entry = claude_entry()  # Einträge ohne das Feld cache (und solche mit cache False) schalten die Option aus
    write_history(home, [entry])
    use_claude(), use_gemini()
    at = new_claude_app(TAB_NEW)
    at.session_state["cache_claude"] = True
    at.run()
    at.session_state["view"] = TAB_JOBS
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.checkbox(key="cache_claude").value is False


@ui
def test_reuse_inputs_of_a_gemini_entry_switches_back_from_claude(use_claude, use_gemini, home):
    entry = batch_entry(think="medium", model="gemini-anderes-modell")
    write_history(home, [entry])
    use_claude(), use_gemini()
    at = new_claude_app(TAB_JOBS)
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.radio(key="provider").value == PROVIDER_GEMINI
    assert at.radio(key="mode").value == MODE_BATCH and at.selectbox(key="think").value == "medium"
    assert model_field(at).value == "gemini-anderes-modell"  # ein eigener Name aus dem Verlauf bleibt wählbar


@ui
@pytest.mark.parametrize("stored, expected", [(999_999_999, 128000), (10, 256), (65536, 65536)])
def test_reuse_inputs_clamps_the_stored_output_limit_to_the_claude_range(use_claude, use_gemini, home, stored, expected):
    entry = claude_entry(max_out=stored)
    write_history(home, [entry])
    use_claude(), use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.number_input(key="max_claude").value == expected


@ui
def test_reuse_inputs_ignores_a_stored_effort_claude_does_not_know(use_claude, use_gemini, home):
    entry = claude_entry(think="minimal")  # eine Stufe aus einem anderen Anbieter (kein Claude-Wert)
    write_history(home, [entry])
    use_claude(), use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.selectbox(key="effort_claude").value == "Standard"


@ui
def test_continuing_a_claude_answer_stays_with_claude(use_claude, use_gemini, home):
    entry = finished_claude_batch(think="medium")
    write_history(home, [entry])
    use_claude(), use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    at.button(key=f"talk:{entry['name']}:prompt-1").click()
    at.run()
    assert not at.exception and at.session_state["view"] == TAB_NEW
    assert at.radio(key="provider").value == PROVIDER_CLAUDE and at.selectbox(key="effort_claude").value == "medium"
    assert not [r for r in at.radio if r.key == "mode"]


@ui
def test_entries_of_all_three_providers_open_next_to_each_other(use_claude, use_openai, use_gemini, home):
    old = finished_batch()
    old.pop("api_model")  # ältere Einträge kennen weder provider noch manche anderen Felder
    entries = [finished_claude_batch(), helpers.finished_openai_batch(), old]
    write_history(home, entries)
    use_claude(), use_openai(), use_gemini()
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and not at.error
    options = at.selectbox(key="sel").options
    assert any(o.startswith("altbatch") for o in options) and any(o.startswith("openai-batch") for o in options)
    assert any(o.startswith("claude-batch") for o in options)
    assert read_history(home) == entries  # der Start ergänzt das Feld provider nicht
