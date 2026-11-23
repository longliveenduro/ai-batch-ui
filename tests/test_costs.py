"""Tests der geschätzten Kosten eines Laufs (Issue #39): die Preisdatei conf/prices.toml, die Rechnung aus Token und
Preisen, die Texte und die Anzeige im Tab „Jobs und Ergebnisse“.

Die Preise sind die der Tabelle der App (Stand PRICES_AS_OF). Die erwarteten Beträge sind von Hand nachgerechnet, nicht
mit dem Code der App: Gemini Carbon kostet vor dem 01.12.2026 im Standardtarif 2 USD Eingabe, 10 USD Ausgabe und 0,10
USD Cache je 1 Mio. Token, danach das Doppelte. Ein Beispiel mit 1 Mio. Eingabe-Token (400.000 davon aus dem Cache) und
300.000 Ausgabe-Token (Denken und Antwort): 600.000 × 2 + 400.000 × 0,10 + 300.000 × 10 = 4,24 USD, als Batch die
Hälfte.
"""
import re
import textwrap
from datetime import date
from decimal import Decimal as D

import pytest

from fakes import make_claude_message
from helpers import (PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, ROOT, TAB_JOBS, background_entry, batch_entry,
                     captions, finished_background, finished_batch, finished_claude_batch, finished_openai_batch,
                     model_field, new_app, row, sync_entry, type_model, write_history)

ui = pytest.mark.ui
BEFORE, CHANGE = date(2026, 11, 20), date(2026, 12, 1)  # Tag vor dem Preiswechsel bei Gemini 4 und sein erster Tag
CREATED_BEFORE = "2026-10-19T14:38:00"  # Start vor dem Preiswechsel (das Datum der Beispiel-Einträge in helpers)
CREATED_AFTER = "2026-12-02T09:00:00"
TOKENS = {"in": 1_000_000, "cached": 400_000, "think": 100_000, "out": 200_000}  # siehe oben: 4,24 USD, Batch 2,12 USD
NO_TOKENS = {"in": 0, "cached": 0, "think": 0, "out": 0}
PRICES_TEXT = "Eigene Preise aus conf/prices.toml"
GOOD = 'provider = "Claude"\nmodel = "claude-x"\ninput = 1\noutput = 5\ncache = 0.1'  # ein gültiger Eintrag ohne Kopf


def write_prices(home, text):
    """Schreibt conf/prices.toml im Ordner der Fixture home (eingerückte Beispiele werden gerade gerückt)."""
    path = home / "conf" / "prices.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), "utf-8")
    return path


def entry_block(body):
    """Ein Eintrag [[price]] aus den Zeilen in body."""
    return "[[price]]\n" + textwrap.dedent(body).strip() + "\n"


def with_rows(entry, *rows):
    entry["rows"] = list(rows)
    return entry


@pytest.fixture
def claude_row(app):
    """claude_row(input_tokens=…, …) liefert die Zeile, die der Parser der App aus einer Claude-Antwort baut, mit den
    rohen Nutzungsdaten (die Argumente sind die von fakes.make_claude_message)."""
    def make(**message):
        line = {"custom_id": "prompt-1", "result": {"type": "succeeded", "message": make_claude_message(**message)}}
        return app.parse_claude_line(line, {"prompt-1": "Eins"})
    return make


def box(at):
    """Text der Infobox mit den Kosten in der Seitenleiste, None wenn es sie nicht gibt."""
    found = [i.value for i in at.sidebar.info if i.value.startswith("**Kosten in USD")]
    assert len(found) <= 1
    return found[0] if found else None


def cost_captions(at):
    """Die Zeilen zu den Kosten eines Laufs im Tab „Jobs und Ergebnisse“ (die Summe oder der Hinweis ohne Preis)."""
    return [c for c in at.caption if c.value.startswith(("Geschätzte Kosten", "Kosten: "))]


# ---------- Preisdatei: lesen ----------
def test_without_a_price_file_the_built_in_table_applies(pricing):
    book = pricing.current_prices()
    assert book.table == pricing.PRICES and book.own == {} and book.problems == []
    assert pricing.read_price_file() == ({}, [])


def test_a_price_file_changes_prices_and_adds_models(home, pricing):
    write_prices(home, """
        # Kommentare sind erlaubt
        [[price]]
        provider = "Gemini"
        model = "gemini-4-neon"
        input = 3.5
        output = 16
        cache = 0.2

        [[price]]
        provider = "Claude"
        model = "claude-sonnet-5-6"
        input = 2.5
        output = 12
        cache = 0.25
    """)
    book = pricing.current_prices()
    assert book.problems == []
    assert book.table["Gemini"]["gemini-4-neon"] == [(None, [(None, D("3.5"), D("16"), D("0.2"))])]
    assert book.table["Claude"]["claude-sonnet-5-6"] == [(None, [(None, D("2.5"), D("12"), D("0.25"))])]
    assert book.own == {"Gemini": {"gemini-4-neon"}, "Claude": {"claude-sonnet-5-6"}}
    assert book.table["Gemini"]["gemini-4-carbon"] is pricing.PRICES["Gemini"]["gemini-4-carbon"]  # der Rest bleibt
    assert pricing.PRICES["Gemini"]["gemini-4-neon"] == [(None, [(None, D("3"), D("15"), D("0.15"))])]  # unverändert
    assert "claude-sonnet-5-6" not in pricing.PRICES["Claude"]
    assert list(book.table["Claude"])[-1] == "claude-sonnet-5-6"  # neue Modelle stehen hinter den eingebauten


def test_the_file_knows_price_tiers_and_prices_from_a_day_on(home, pricing):
    write_prices(home, """
        [[price]]
        provider = "OpenAI"
        model = "gpt-9-nova"
        input = 16
        output = 60
        cache = 0.8

        [[price]]
        provider = "OpenAI"
        model = "gpt-9-nova"
        up_to = 272_000
        input = 8
        output = 40
        cache = 0.4

        [[price]]
        provider = "Claude"
        model = "claude-new-1"
        from = 2027-01-01
        input = 2
        output = 10
        cache = 0.2

        [[price]]
        provider = "Claude"
        model = "claude-new-1"
        input = 1
        output = 5
        cache = 0.1
    """)
    book = pricing.current_prices()
    assert book.problems == []
    # die Reihenfolge in der Datei spielt keine Rolle: Stufen nach der Grenze (die ohne Grenze zuletzt), Preisstände
    # nach dem Tag
    assert book.table["OpenAI"]["gpt-9-nova"] == [(None, [(272_000, D("8"), D("40"), D("0.4")),
                                                          (None, D("16"), D("60"), D("0.8"))])]
    assert book.table["Claude"]["claude-new-1"] == [(None, [(None, D("1"), D("5"), D("0.1"))]),
                                                    (date(2027, 1, 1), [(None, D("2"), D("10"), D("0.2"))])]


def test_names_and_dates_are_read_leniently(home, pricing):
    write_prices(home, """
        [[price]]
        provider = " claude "
        model = "Models/Claude-Y"
        input = 1
        output = 5
        cache = 0.1

        [[price]]
        provider = "CLAUDE"
        model = "claude-y"
        from = "2027-02-01"
        input = 2
        output = 6
        cache = 0.2

        [[price]]
        provider = "claude"
        model = "claude-y"
        from = 2027-03-01T10:00:00
        input = 3
        output = 7
        cache = 0.3

        [[price]]
        provider = "claude"
        model = "claude-y"
        from = 2027-04-01T00:00:00Z
        input = 4
        output = 8
        cache = 0.4
    """)
    book = pricing.current_prices()
    assert book.problems == []
    assert [since for since, _ in book.table["Claude"]["claude-y"]] == [
        None, date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]


def test_a_model_from_the_file_replaces_the_whole_entry_of_the_model(home, pricing):
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-carbon", BEFORE)["later"]  # eingebaut: Preiswechsel am 01.12.
    write_prices(home, entry_block("""
        provider = "Gemini"
        model = "gemini-4-carbon"
        input = 10
        output = 20
        cache = 1
    """))
    costs = pricing.model_costs(PROVIDER_GEMINI, "gemini-4-carbon", BEFORE)
    assert costs["later"] == [] and costs["custom"] is True  # der Preiswechsel gehört zum alten Eintrag und ist weg
    assert costs["rows"][0] == ("Batch", D("5"), D("10"), D("0.5"))
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-argon", BEFORE)["custom"] is False
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-argon", BEFORE)["later"]  # der Nachbar behält seinen


def test_an_edit_of_the_file_applies_without_a_restart(home, pricing):
    path = write_prices(home, entry_block("""
        provider = "Gemini"
        model = "gemini-4-neon"
        input = 4
        output = 20
        cache = 0.2
    """))
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-neon", BEFORE)["rows"][0][2] == D("10")
    path.write_text(path.read_text("utf-8").replace("output = 20", "output = 30"), "utf-8")
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-neon", BEFORE)["rows"][0][2] == D("15")
    path.unlink()
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-neon", BEFORE)["rows"][0][2] == D("7.5")  # eingebaut
    assert pricing.current_prices().own == {}


# ---------- Preisdatei: Fehler ----------
BAD_ENTRIES = [
    ("input fehlt", 'provider = "Claude"\nmodel = "claude-x"\noutput = 5\ncache = 0.1'),
    ("input, cache fehlen", 'provider = "Claude"\nmodel = "claude-x"\noutput = 5'),
    ("unbekannter Schlüssel: upto", GOOD + "\nupto = 100"),
    ("output muss eine Zahl ab 0 sein", GOOD.replace("output = 5", 'output = "viel"')),
    ("input muss eine Zahl ab 0 sein", GOOD.replace("input = 1", "input = -1")),
    ("input muss eine Zahl ab 0 sein", GOOD.replace("input = 1", "input = true")),
    ("input muss eine Zahl ab 0 sein", GOOD.replace("input = 1", "input = nan")),
    ("input muss eine Zahl ab 0 sein", GOOD.replace("input = 1", "input = inf")),
    ("cache muss eine Zahl ab 0 sein", GOOD.replace("cache = 0.1", "cache = 2027-01-01")),
    ("up_to muss eine ganze Zahl über 0 sein", GOOD + "\nup_to = 0"),
    ("up_to muss eine ganze Zahl über 0 sein", GOOD + "\nup_to = 1.5"),
    ("up_to muss eine ganze Zahl über 0 sein", GOOD + "\nup_to = true"),
    ("from muss ein Datum sein", GOOD + '\nfrom = "morgen"'),
    ("from muss ein Datum sein", GOOD + "\nfrom = 7"),
    ("der erste Preisstand muss ohne from stehen", GOOD + "\nfrom = 2027-01-01"),
    ("die letzte Stufe braucht einen Eintrag ohne up_to", GOOD + "\nup_to = 1000"),
]


@pytest.mark.parametrize("reason, body", BAD_ENTRIES)
def test_a_faulty_entry_invalidates_only_its_model(home, pricing, reason, body):
    write_prices(home, entry_block(body) + "\n" + entry_block("""
        provider = "Claude"
        model = "claude-ok"
        input = 1
        output = 5
        cache = 0.1
    """))
    book = pricing.current_prices()
    [problem] = book.problems
    assert reason in problem and problem.startswith("conf/prices.toml, Claude „claude-x“")
    assert "Die Preise dieses Modells aus der Datei gelten nicht" in problem
    assert "claude-x" not in book.table["Claude"] and "claude-ok" in book.table["Claude"]  # das andere Modell gilt
    assert book.own == {"Claude": {"claude-ok"}}


@pytest.mark.parametrize("reason, body", [
    ("provider muss Gemini, OpenAI oder Claude sein", GOOD.replace('"Claude"', '"Mistral"')),
    ("provider muss Gemini, OpenAI oder Claude sein", GOOD.replace('provider = "Claude"', "provider = 5")),
    ("model muss ein Modellname ohne Leerzeichen sein", GOOD.replace("claude-x", "zwei worte")),
    ("model muss ein Modellname ohne Leerzeichen sein", GOOD.replace('"claude-x"', '""')),
    ("model muss ein Modellname ohne Leerzeichen sein", GOOD.replace('"claude-x"', "5")),
    ("provider, model fehlen", "input = 1\noutput = 5\ncache = 0.1"),
])
def test_an_entry_without_a_usable_model_is_skipped_on_its_own(home, pricing, reason, body):
    write_prices(home, entry_block(body))
    book = pricing.current_prices()
    [problem] = book.problems
    assert problem.startswith("conf/prices.toml, Eintrag 1: ") and reason in problem
    assert problem.endswith("Der Eintrag gilt nicht.")
    assert book.table == pricing.PRICES and book.own == {}


def test_two_entries_with_the_same_day_and_limit_are_an_error(home, pricing):
    write_prices(home, entry_block(GOOD) + "\n" + entry_block(GOOD.replace("input = 1", "input = 2")))
    [problem] = pricing.current_prices().problems
    assert "Eintrag 2: zwei Einträge mit demselben from und up_to" in problem
    assert "claude-x" not in pricing.current_prices().table["Claude"]


def test_the_error_names_the_day_of_a_period_without_a_last_tier(home, pricing):
    write_prices(home, entry_block(GOOD) + "\n" + entry_block(GOOD + "\nfrom = 2027-01-01\nup_to = 5"))
    [problem] = pricing.current_prices().problems
    assert "die letzte Stufe braucht einen Eintrag ohne up_to (Preisstand ab 01.01.2027)" in problem


def test_a_file_that_is_not_valid_toml_leaves_the_built_in_table(home, pricing):
    path = write_prices(home, "[[price]\nprovider = ")
    book = pricing.current_prices()
    [problem] = book.problems
    assert problem.startswith("conf/prices.toml lässt sich nicht lesen")
    assert "Es gelten die eingebauten Preise" in problem
    assert book.table == pricing.PRICES and book.own == {}
    path.write_bytes(b"\xff\xfe[[price]]")  # kein UTF-8
    [problem] = pricing.current_prices().problems
    assert "lässt sich nicht lesen" in problem
    path.unlink()
    path.mkdir()  # ein Ordner statt einer Datei
    [problem] = pricing.current_prices().problems
    assert "lässt sich nicht lesen" in problem and pricing.current_prices().table == pricing.PRICES


def test_a_file_that_may_not_be_read_is_reported_and_does_not_stop_the_app(home, pricing, monkeypatch):
    path = write_prices(home, entry_block(GOOD))

    def denied(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr(type(path), "open", denied)
    book = pricing.current_prices()
    [problem] = book.problems
    assert problem.startswith("conf/prices.toml lässt sich nicht lesen") and "Permission denied" in problem
    assert book.table == pricing.PRICES and book.own == {}


def test_unknown_sections_are_reported_but_the_valid_prices_still_apply(home, pricing):
    write_prices(home, entry_block(GOOD) + "\n[settings]\nx = 1\n")
    book = pricing.current_prices()
    assert book.problems == ["conf/prices.toml: Unbekannter Abschnitt „settings“, erlaubt sind nur Einträge [[price]]."]
    assert "claude-x" in book.table["Claude"]


@pytest.mark.parametrize("text", ["price = 5", "[price]\nprovider = 'Claude'"])
def test_a_price_section_of_the_wrong_shape_is_reported(home, pricing, text):
    write_prices(home, text)
    book = pricing.current_prices()
    assert len(book.problems) == 1 and "[[price]]" in book.problems[0]
    assert book.table == pricing.PRICES


def test_entries_that_are_no_tables_are_reported_one_by_one(home, pricing):
    write_prices(home, "price = [1, 'zwei']")
    book = pricing.current_prices()
    assert book.problems == ["conf/prices.toml, Eintrag 1: kein Eintrag [[price]]. Der Eintrag gilt nicht.",
                             "conf/prices.toml, Eintrag 2: kein Eintrag [[price]]. Der Eintrag gilt nicht."]
    assert book.table == pricing.PRICES


def test_an_empty_file_is_fine(home, pricing):
    write_prices(home, "")
    assert pricing.current_prices().problems == [] and pricing.current_prices().table == pricing.PRICES


# ---------- Preisdatei: die Auswahl der Modelle ----------
def test_models_from_the_file_are_found_like_the_built_in_ones(home, pricing):
    write_prices(home, entry_block(GOOD))
    assert pricing.find_model(PROVIDER_CLAUDE, "Claude-X") == "claude-x"
    assert pricing.find_model(PROVIDER_CLAUDE, "claude-x-2027-01-01") == "claude-x"  # ein angehängter Stand ändert nichts
    assert pricing.find_model(PROVIDER_CLAUDE, "claude-x-pro") is None  # eine andere Fassung ist ein anderes Modell
    assert pricing.find_model(PROVIDER_GEMINI, "claude-x") is None  # und gilt nur beim eigenen Anbieter
    table = {PROVIDER_CLAUDE: {"claude-q": []}}
    assert pricing.find_model(PROVIDER_CLAUDE, "claude-q", table) == "claude-q"  # mit einer fertigen Tabelle


def test_added_models_join_the_selection_sorted_by_price_and_may_exceed_the_limit(home, pricing):
    write_prices(home, "\n".join(entry_block(f"""
        provider = "Gemini"
        model = "gemini-4-{name}"
        input = 1
        output = {output}
        cache = 0.1
    """) for name, output in [("xenon", 10), ("radon", 30), ("argon-pro", 1)]))
    names = pricing.model_choices(PROVIDER_GEMINI, BEFORE)
    # Radon mit 30 steht vorn, dann Neon mit 15. Bei gleichem Preis (10) gilt die Reihenfolge der Tabelle: Carbon und
    # Argon (eingebaut) vor Xenon (aus der Datei). Dann Hydrogen mit 7,50 und das billigste neue Modell.
    assert names == ["gemini-4-radon", "gemini-4-neon", "gemini-4-carbon", "gemini-4-argon", "gemini-4-xenon",
                     "gemini-4-hydrogen", "gemini-4-argon-pro"]
    assert len(names) > pricing.MAX_MODELS  # die Grenze gilt für PRICES, nicht für die Datei
    assert len(pricing.PRICES[PROVIDER_GEMINI]) <= pricing.MAX_MODELS
    assert pricing.default_model(PROVIDER_GEMINI, BEFORE) == "gemini-4-radon"


def test_the_caption_says_where_own_prices_come_from(pricing):
    assert "Stand der Preise" in pricing.costs_caption() and "conf/prices.toml" not in pricing.costs_caption()
    custom = pricing.costs_caption(custom=True)
    assert PRICES_TEXT in custom and "Stand der Preise" not in custom and "Denk-Token" in custom
    for provider in (PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE):
        assert "conf/prices.toml" in pricing.costs_help(provider)


# ---------- Preis einer Stufe, Preistag ----------
def test_the_tier_follows_the_length_of_the_prompt_and_the_day(pricing):
    table = pricing.current_prices().table

    def tier(provider, key, day, tokens):
        return pricing.price_tier(table, provider, key, day, tokens)

    assert tier(PROVIDER_OPENAI, "gpt-6-astra", BEFORE, 0) == (D("10"), D("50"), D("1"))
    assert tier(PROVIDER_OPENAI, "gpt-6-astra", BEFORE, 272_000) == (D("10"), D("50"), D("1"))  # die Grenze gehört dazu
    assert tier(PROVIDER_OPENAI, "gpt-6-astra", BEFORE, 272_001) == (D("20"), D("75"), D("2"))
    assert tier(PROVIDER_CLAUDE, "claude-haiku-5-5", BEFORE, 100_001) == (D("0.50"), D("2.50"), D("0.05"))
    assert tier(PROVIDER_GEMINI, "gemini-4-carbon", BEFORE, 5_000_000) == (D("2"), D("10"), D("0.10"))  # keine Stufen
    assert tier(PROVIDER_GEMINI, "gemini-4-carbon", CHANGE, 10) == (D("4"), D("20"), D("0.20"))


@pytest.mark.parametrize("created, expected", [
    ("2026-10-19T14:38:00", date(2026, 10, 19)), ("2026-11-30T23:59:59", date(2026, 11, 30)),
    ("2026-10-19", date(2026, 10, 19)), (None, date(2026, 12, 15)), ("", date(2026, 12, 15)),
    ("gestern", date(2026, 12, 15)), (5, date(2026, 12, 15)),
])
def test_the_prices_of_the_start_day_apply(pricing, created, expected):
    assert pricing.run_day(created) == expected  # ohne lesbaren Start gilt heute (in den Tests der 15.12.2026)


# ---------- Rechnung ----------
def test_a_gemini_batch_costs_half_the_standard_price_and_is_compared_with_the_background_mode(app):
    costs = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert costs["model"] == "gemini-4-carbon" and costs["day"] == date(2026, 10, 19) and costs["custom"] is False
    assert costs["rows"] == {"prompt-1": D("2.12")} and costs["total"] == D("2.12")
    assert costs["phrase"] == "als Batch" and costs["other"] == ("Im Hintergrund-Modus", D("4.24"))


def test_a_background_run_costs_the_standard_price_and_is_compared_with_the_batch(app):
    costs = app.run_costs(PROVIDER_GEMINI, "background", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert costs["total"] == D("4.24") and costs["phrase"] == "im Hintergrund-Modus (Standardpreis)"
    assert costs["other"] == ("Als Batch", D("2.12"))


def test_the_older_synchronous_mode_costs_the_standard_price_without_a_comparison(app):
    costs = app.run_costs(PROVIDER_GEMINI, "sync", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert costs["total"] == D("4.24") and costs["phrase"] == "zum Standardpreis (älterer synchroner Lauf)"
    assert costs["other"] is None
    unknown = app.run_costs(PROVIDER_GEMINI, "gibt-es-nicht", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert unknown["total"] == D("2.12") and unknown["other"] is None  # eine unbekannte Betriebsart: wie ein Batch


def test_the_price_of_the_start_day_applies_also_after_a_price_change(app):
    rows = [row(**TOKENS)]

    def run(created):
        return app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-carbon", created, rows)

    assert run("2026-11-30T23:59:59")["total"] == D("2.12")  # der letzte Tag des alten Preises: auch heute (15.12.)
    assert run("2026-12-01T00:00:00")["total"] == D("4.24") and run("2026-12-01T00:00:00")["other"][1] == D("8.48")
    assert run(CREATED_AFTER)["total"] == D("4.24")
    assert run(None)["total"] == D("4.24") and run("kaputt")["total"] == D("4.24")  # ohne Start gilt heute: neuer Preis


def test_an_openai_batch_has_tiers_and_no_comparison(app):
    short = row(**{"in": 100_000, "cached": 40_000, "think": 10_000, "out": 5_000})
    # 60.000 × 10 + 40.000 × 1 + 15.000 × 50 = 1,39 USD, als Batch 0,695
    costs = app.run_costs(PROVIDER_OPENAI, "batch", "gpt-6-astra", CREATED_BEFORE, [short])
    assert costs["total"] == D("0.695") and costs["other"] is None and costs["phrase"] == "als Batch"
    for tokens, expected in [(272_000, D("1.36")), (272_001, D("2.72001"))]:  # 272.000 × 10 / 2, 272.001 × 20 / 2
        long = row(**{"in": tokens, "cached": 0, "think": 0, "out": 0})
        assert app.run_costs(PROVIDER_OPENAI, "batch", "gpt-6-astra", CREATED_BEFORE, [long])["total"] == expected


def test_a_claude_batch_includes_writing_to_the_cache(app, claude_row):
    # 10.000 neu, 80.000 aus dem Cache, 5.000 in den Cache geschrieben, 30.000 Ausgabe (12.000 davon Denken).
    # Das Schreiben mit einer Stunde Lebensdauer kostet das Doppelte der Eingabe: 10.000 × 2 + 5.000 × 2 × 2
    # + 80.000 × 0,10 + 30.000 × 10 = 0,348 USD, als Batch 0,174
    r = claude_row(input_tokens=10_000, cache_read=80_000, cache_creation=5_000, thinking=12_000, output=30_000)
    assert (r["in"], r["cached"], r["think"], r["out"]) == (95_000, 80_000, 12_000, 18_000)
    costs = app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [r])
    assert costs["total"] == D("0.174") and costs["other"] is None
    # ohne das Schreiben in den Cache: 10.000 × 2 + 80.000 × 0,10 + 30.000 × 10 = 0,328, als Batch 0,164
    plain = claude_row(input_tokens=10_000, cache_read=80_000, cache_creation=0, thinking=12_000, output=30_000)
    assert app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [plain])["total"] == D("0.164")


def test_claude_splits_the_cache_writes_by_their_lifetime(app, claude_row):
    r = claude_row(input_tokens=10_000, cache_read=80_000, cache_creation=5_000, thinking=12_000, output=30_000)

    def total():
        return app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [r])["total"]

    # fünf Minuten kosten das 1,25-fache, eine Stunde das Doppelte der Eingabe:
    # 10.000 × 2 + (2.000 × 1,25 + 3.000 × 2) × 2 + 80.000 × 0,10 + 300.000 = 0,345, als Batch 0,1725
    r["usage"]["cache_creation"] = {"ephemeral_5m_input_tokens": 2_000, "ephemeral_1h_input_tokens": 3_000}
    assert total() == D("0.1725")
    r["usage"]["cache_creation"] = {"ephemeral_5m_input_tokens": 2_000}  # der Rest zählt mit CLAUDE_CACHE_TTL (1 Stunde)
    assert total() == D("0.1725")
    r["usage"]["cache_creation"] = {"ephemeral_5m_input_tokens": 5_000}  # alles mit fünf Minuten: 6.250 × 2 = 12.500
    assert total() == D("0.17025")  # (20.000 + 12.500 + 8.000 + 300.000) / 1 Mio. / 2


def test_only_claude_has_a_price_for_writing_to_the_cache(app):
    # Bei Gemini und OpenAI steht das Schreiben nicht in den Nutzungsdaten und zählt dort nicht.
    tokens = {"in": 95_000, "cached": 80_000, "think": 0, "out": 0}
    with_usage = row(usage={"cache_creation_input_tokens": 5_000}, **tokens)
    without_usage = row(usage={}, **tokens)
    for provider, model in [(PROVIDER_GEMINI, "gemini-4-carbon"), (PROVIDER_OPENAI, "gpt-6-astra")]:
        assert (app.run_costs(provider, "batch", model, CREATED_BEFORE, [with_usage])["total"]
                == app.run_costs(provider, "batch", model, CREATED_BEFORE, [without_usage])["total"])
    assert (app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [with_usage])["total"]
            != app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [without_usage])["total"])


def test_a_claude_model_with_tiers_uses_the_tier_of_the_prompt(app):
    # Haiku über 100.000 Token: 150.000 × 0,50 + 10.000 × 2,50 = 0,10 USD, als Batch 0,05
    r = row(**{"in": 150_000, "cached": 0, "think": 0, "out": 10_000})
    assert app.run_costs(PROVIDER_CLAUDE, "batch", "claude-haiku-5-5", CREATED_BEFORE, [r])["total"] == D("0.05")


def test_the_total_is_the_sum_of_the_rows_and_rows_without_tokens_are_left_out(app):
    rows = [row(**TOKENS),
            row(key="prompt-2", text="", error="Blockiert", **NO_TOKENS),
            row(key="prompt-3", **{"in": 1_000_000, "cached": 0, "think": 0, "out": 0})]
    costs = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-carbon", CREATED_BEFORE, rows)
    assert costs["rows"] == {"prompt-1": D("2.12"), "prompt-3": D("1")}  # der Fehler hat keine Token, also keine Kosten
    assert costs["total"] == sum(costs["rows"].values()) == D("3.12")
    assert costs["other"] == ("Im Hintergrund-Modus", D("6.24"))


def test_rows_of_older_runs_and_odd_values_do_not_break_the_calculation(app):
    minimal = {"key": "prompt-1", "prompt": "Eins", "text": "Alt", "error": None, "in": 1_000_000, "cached": 0,
               "think": 0, "out": 0}  # ohne model, finish, usage
    odd = {"key": "prompt-2", "in": None, "cached": True, "think": -5, "out": "viel", "usage": "kaputt"}
    costs = app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [minimal, odd])
    assert costs["rows"] == {"prompt-1": D("1")}  # 1 Mio. × 2 USD / 2; die Zeile mit Unsinn zählt nichts
    wrong_usage = {**minimal, "usage": ["kein", "dict"]}
    assert app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [wrong_usage])["total"] == D("1")
    assert app.run_costs(PROVIDER_CLAUDE, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [])["total"] == D("0")


def test_the_model_is_taken_from_the_entry_then_from_what_the_api_reported(app):
    r = row(model="claude-sonnet-5-5", **TOKENS)

    def find(model, api_model=None, rows=(r,)):
        return app.run_costs(PROVIDER_CLAUDE, "batch", model, CREATED_BEFORE, list(rows), api_model)

    assert find("claude-sonnet-5-5")["model"] == "claude-sonnet-5-5"
    assert find("Claude-Sonnet-5-5-2026-09-01")["model"] == "claude-sonnet-5-5"  # Schreibweise und Stand
    assert find("claude-sonnet-latest", "claude-sonnet-5-5")["model"] == "claude-sonnet-5-5"  # Alias: Name der API
    assert find("claude-sonnet-latest", None)["model"] == "claude-sonnet-5-5"  # und sonst der Name in der Zeile
    assert find("claude-sonnet-latest", rows=[row(model="unbekannt", **TOKENS)]) is None
    assert find("", None, rows=[]) is None and find(None, None, rows=[]) is None
    assert app.run_costs(PROVIDER_GEMINI, "batch", "claude-sonnet-5-5", CREATED_BEFORE, [r]) is None  # anderer Anbieter


def test_prices_from_the_file_are_used_and_flagged(home, app):
    write_prices(home, entry_block("""
        provider = "Gemini"
        model = "gemini-4-carbon"
        input = 10
        output = 20
        cache = 1
    """))
    # 600.000 × 10 + 400.000 × 1 + 300.000 × 20 = 12,40 USD, als Batch 6,20
    costs = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert costs["total"] == D("6.2") and costs["custom"] is True and costs["other"][1] == D("12.4")
    other = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-argon", CREATED_BEFORE, [row(**TOKENS)])
    assert other["total"] == D("2.12") and other["custom"] is False


def test_the_constants_fit_together(app, pricing):
    assert app.CLAUDE_CACHE_TTL in pricing.CLAUDE_CACHE_WRITE  # ändert sich die Lebensdauer, braucht sie einen Faktor
    assert set(app.KINDS) == {"batch", "background", "sync"}  # die Betriebsarten von providers.entry_mode()
    assert {app.entry_mode(e) for e in (batch_entry(), background_entry(), sync_entry())} == set(app.KINDS)
    assert app.KINDS["batch"][1] == pricing.BATCH_FACTOR and app.KINDS["background"][1] == D(1)
    assert set(app.COMPARISON) == {"batch", "background"} and app.MILLION == 1_000_000


# ---------- Texte ----------
@pytest.mark.parametrize("value, expected", [
    (D("0"), "0,00"), (D("2.12"), "2,12"), (D("0.1725"), "0,1725"), (D("0.0001"), "0,0001"),
    (D("0.00004"), "< 0,0001"), (D("12.34567"), "12,3457"), (D("1000"), "1000,00"), (D("0.695"), "0,695"),
])
def test_amounts_are_written_in_the_german_format(app, value, expected):
    assert app.cost_text(value) == expected


def test_the_sentences_name_the_kind_and_the_comparison(app):
    def run(provider, mode, model, rows=None):
        return app.run_costs(provider, mode, model, CREATED_BEFORE, rows or [row(**TOKENS)])

    short = row(**{"in": 100_000, "cached": 40_000, "think": 10_000, "out": 5_000})
    texts = [
        app.run_cost_text(run(PROVIDER_GEMINI, "batch", "gemini-4-carbon"), 1, 1),
        app.run_cost_text(run(PROVIDER_GEMINI, "background", "gemini-4-carbon"), 1, 1),
        app.run_cost_text(run(PROVIDER_GEMINI, "sync", "gemini-4-carbon"), 1, 1),
        app.run_cost_text(run(PROVIDER_OPENAI, "batch", "gpt-6-astra", [short]), 1, 1),
        app.run_cost_text(run(PROVIDER_GEMINI, "batch", "gemini-4-carbon"), 1, 3),
    ]
    assert texts == [
        "Geschätzte Kosten: 2,12 USD als Batch. Im Hintergrund-Modus wären es bei gleichen Token 4,24 USD.",
        "Geschätzte Kosten: 4,24 USD im Hintergrund-Modus (Standardpreis). "
        "Als Batch wären es bei gleichen Token 2,12 USD.",
        "Geschätzte Kosten: 4,24 USD zum Standardpreis (älterer synchroner Lauf).",
        "Geschätzte Kosten: 0,695 USD als Batch.",
        "Geschätzte Kosten der bisher fertigen Prompts (1 von 3): 2,12 USD als Batch. "
        "Im Hintergrund-Modus wären es bei gleichen Token 4,24 USD.",
    ]
    assert not any("$" in t for t in texts)  # ein $ würde Streamlit als Formel lesen


def test_a_row_shows_its_cost_only_when_there_is_one(app):
    costs = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-carbon", CREATED_BEFORE, [row(**TOKENS)])
    assert app.row_cost_text(costs, "prompt-1") == "Kosten ca. 2,12 USD"
    assert app.row_cost_text(costs, "prompt-9") is None and app.row_cost_text(None, "prompt-1") is None
    one_token = row(**{"in": 1, "cached": 0, "think": 0, "out": 0})
    tiny = app.run_costs(PROVIDER_GEMINI, "batch", "gemini-4-hydrogen", CREATED_BEFORE, [one_token])
    assert app.row_cost_text(tiny, "prompt-1") == "Kosten ca. < 0,0001 USD"  # nicht „0,00“: das sähe kostenlos aus


def test_the_hint_without_a_price_names_the_model_and_the_file(app):
    text = app.no_price_text("gemini-9-`xenon`")
    assert text.startswith("Kosten: Für `gemini-9-xenon` ist kein Preis hinterlegt") and "conf/prices.toml" in text
    assert "`unbekannt`" in app.no_price_text(None) and "`unbekannt`" in app.no_price_text("")
    assert "$" not in text


def test_the_note_explains_what_is_in_and_what_is_not_per_provider(app):
    note = app.costs_note
    for provider in (PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE):
        text = note(provider, "batch")
        assert "Eine Schätzung, keine Abrechnung" in text
        assert "Preisstand des Tages, an dem der Lauf gestartet wurde" in text
        assert "conf/prices.toml" not in text and "$" not in text
    assert "Vergleich nimmt dieselben Token an" in note(PROVIDER_GEMINI, "batch")
    assert "Vergleich nimmt dieselben Token an" in note(PROVIDER_GEMINI, "background")
    assert "Vergleich" not in note(PROVIDER_GEMINI, "sync")  # der ältere synchrone Modus hat keinen
    assert "Vergleich" not in note(PROVIDER_OPENAI, "batch") and "Vergleich" not in note(PROVIDER_CLAUDE, "batch")
    assert "das 2-fache des Eingabepreises bei einer Stunde" in note(PROVIDER_CLAUDE, "batch")  # aus CLAUDE_CACHE_WRITE
    assert "das 1,25-fache bei fünf Minuten" in note(PROVIDER_CLAUDE, "batch")
    assert "nicht eingerechnet" in note(PROVIDER_OPENAI, "batch") and "eingerechnet:" not in note(PROVIDER_OPENAI, "batch")
    assert "Schreiben in den Cache" not in note(PROVIDER_GEMINI, "batch")
    assert "Für dieses Modell gelten die Preise aus conf/prices.toml" in note(PROVIDER_CLAUDE, "batch", custom=True)


# ---------- Oberfläche ----------
@ui
def test_a_gemini_batch_shows_its_costs_per_prompt_and_in_total_with_the_comparison(use_all, home):
    write_history(home, [with_rows(finished_batch(), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and not at.warning
    [total] = cost_captions(at)
    assert total.value == ("Geschätzte Kosten: 2,12 USD als Batch. "
                           "Im Hintergrund-Modus wären es bei gleichen Token 4,24 USD.")
    assert "Eine Schätzung, keine Abrechnung" in total.help and "Vergleich nimmt dieselben Token an" in total.help
    shown = captions(at)
    assert any(c.startswith("Modell gemini-4-carbon, Ende: STOP") and "Ausgabe 200,000 Token, Kosten ca. 2,12 USD" in c
               for c in shown)
    tokens_line = [c for c in shown if c.startswith("Eingabe-Token gesamt")][0]
    assert shown.index(total.value) == shown.index(tokens_line) + 1  # die Kosten stehen unter der Summe der Token


@ui
def test_a_background_run_shows_the_standard_price_and_the_batch_as_comparison(use_all, home):
    write_history(home, [finished_background(rows=[row(**TOKENS), row(key="prompt-2", prompt="Zwei", **TOKENS)])])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [total] = cost_captions(at)
    assert total.value == ("Geschätzte Kosten: 8,48 USD im Hintergrund-Modus (Standardpreis). "
                           "Als Batch wären es bei gleichen Token 4,24 USD.")
    assert sum("Kosten ca. 4,24 USD" in c for c in captions(at)) == 2


@ui
def test_a_run_that_is_not_complete_says_that_the_sum_covers_only_the_finished_prompts(use_all, home):
    write_history(home, [finished_background(rows=[row(**TOKENS)])])  # zwei Prompts, eine Zeile
    at = new_app(TAB_JOBS)
    at.run()
    [total] = cost_captions(at)
    assert total.value.startswith("Geschätzte Kosten der bisher fertigen Prompts (1 von 2): 4,24 USD im Hintergrund")


@ui
def test_an_openai_batch_shows_the_batch_cost_without_a_comparison(use_all, home):
    short = row(model="gpt-6-astra-2026-09-01", **{"in": 100_000, "cached": 40_000, "think": 10_000, "out": 5_000})
    write_history(home, [with_rows(finished_openai_batch(), short)])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [total] = cost_captions(at)
    assert total.value == "Geschätzte Kosten: 0,695 USD als Batch." and "nicht eingerechnet" in total.help
    assert "Hintergrund" not in total.value and any("Kosten ca. 0,695 USD" in c for c in captions(at))


@ui
def test_a_claude_batch_includes_the_cache_writes_in_its_costs(use_all, home, claude_row):
    r = claude_row(input_tokens=10_000, cache_read=80_000, cache_creation=5_000, thinking=12_000, output=30_000)
    write_history(home, [with_rows(finished_claude_batch(), r)])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [total] = cost_captions(at)
    assert total.value == "Geschätzte Kosten: 0,174 USD als Batch."
    assert "Schreiben in den Cache ist eingerechnet" in total.help


@ui
def test_a_model_without_a_price_gets_a_hint_instead_of_costs(use_all, home):
    entry = with_rows(finished_batch(model="gemini-3-pro"), row(model="gemini-3-pro", **TOKENS))
    entry["api_model"] = "models/gemini-3-pro"  # auch der Name, den die API gemeldet hat, steht nicht in der Tabelle
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [hint] = cost_captions(at)
    assert hint.value.startswith("Kosten: Für `gemini-3-pro` ist kein Preis hinterlegt")
    assert not any("Kosten ca." in c for c in captions(at))


@ui
def test_an_older_synchronous_entry_shows_costs_at_the_standard_price(use_all, home):
    write_history(home, [sync_entry(rows=[row(**TOKENS), row(key="prompt-2", prompt="P2", **TOKENS)])])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [total] = cost_captions(at)
    assert total.value == "Geschätzte Kosten: 8,48 USD zum Standardpreis (älterer synchroner Lauf)."


@ui
def test_the_costs_of_an_entry_use_the_prices_of_its_start_day(use_all, home):
    write_history(home, [with_rows(finished_batch(created=CREATED_AFTER), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    [total] = cost_captions(at)
    assert total.value.startswith("Geschätzte Kosten: 4,24 USD als Batch") and "8,48 USD" in total.value


@ui
def test_own_prices_change_the_costs_the_infobox_and_the_selection(use_all, home):
    write_prices(home, entry_block("""
        provider = "Gemini"
        model = "gemini-4-carbon"
        input = 10
        output = 20
        cache = 1
    """) + "\n" + entry_block("""
        provider = "Gemini"
        model = "gemini-4-xenon"
        input = 50
        output = 100
        cache = 5
    """))
    write_history(home, [with_rows(finished_batch(), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and not at.warning and not at.sidebar.warning
    [total] = cost_captions(at)
    assert total.value.startswith("Geschätzte Kosten: 6,20 USD als Batch") and "12,40 USD" in total.value
    assert "Für dieses Modell gelten die Preise aus conf/prices.toml" in total.help
    # das neue Modell ist das teuerste: ganz vorn und vorausgewählt, mit den Preisen aus der Datei in der Infobox
    assert model_field(at).options[0] == "gemini-4-xenon" and model_field(at).value == "gemini-4-xenon"
    text = box(at)
    assert "`gemini-4-xenon`" in text and "| Batch | 25,00 | 50,00 | 2,50 |" in text
    assert "| Hintergrund (Long Decode) | 50,00 | 100,00 | 5,00 |" in text
    assert len([c for c in at.sidebar.caption if PRICES_TEXT in c.value]) == 1
    assert not [c for c in at.sidebar.caption if "Stand der Preise" in c.value]
    type_model(at, "model_gemini", "gemini-4-neon")  # ein eingebautes Modell: der Stand der Preise wie immer
    assert [c for c in at.sidebar.caption if "Stand der Preise" in c.value]
    assert not [c for c in at.sidebar.caption if PRICES_TEXT in c.value]


@ui
def test_errors_in_the_price_file_are_shown_in_the_sidebar_and_the_app_keeps_working(use_all, home):
    write_prices(home, entry_block(GOOD.replace("input = 1", "input = -1")) + "\n" + entry_block("""
        provider = "Gemini"
        model = "gemini-4-carbon"
        input = 10
        output = 20
        cache = 1
    """))
    write_history(home, [with_rows(finished_batch(), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and not at.error
    [warning] = at.sidebar.warning
    assert warning.value.startswith("- conf/prices.toml, Claude „claude-x“: Eintrag 1: input muss eine Zahl ab 0 sein")
    assert "\n" not in warning.value  # ein Problem, eine Zeile
    assert box(at) is not None  # die Infobox gibt es weiter
    assert cost_captions(at)[0].value.startswith("Geschätzte Kosten: 6,20 USD")  # das gültige Modell der Datei gilt


@ui
def test_a_price_file_that_is_not_toml_is_reported_and_the_built_in_prices_apply(use_all, home):
    write_prices(home, "[[price]\nkaputt")
    write_history(home, [with_rows(finished_batch(), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [warning] = at.sidebar.warning
    assert "conf/prices.toml lässt sich nicht lesen" in warning.value
    assert "Es gelten die eingebauten Preise" in warning.value
    assert cost_captions(at)[0].value.startswith("Geschätzte Kosten: 2,12 USD als Batch")


@ui
def test_the_problems_are_shown_even_without_a_model_name(use_all, home):
    write_prices(home, "[[price]\nkaputt")
    at = new_app()
    at.run()
    assert box(at) is not None and len(at.sidebar.warning) == 1
    type_model(at, "model_gemini", "")  # ohne Modellnamen gibt es keine Infobox, die Warnung bleibt
    assert not at.exception and box(at) is None and len(at.sidebar.warning) == 1


@ui
def test_without_a_price_file_there_is_no_warning(use_all, home):
    write_history(home, [with_rows(finished_batch(), row(**TOKENS))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception and not at.sidebar.warning and not at.warning


# ---------- README ----------
def test_the_example_of_the_price_file_in_the_readme_is_valid(home, pricing):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = re.search(r"\n### 6\.6[^\n]*\n(.*?)\n##+ ", readme, re.S)  # bis zur nächsten Überschrift
    assert section, "Der Abschnitt 6.6 der README fehlt"
    example = re.search(r"```toml\n(.*?)```", section.group(1), re.S)
    assert example, "Der Abschnitt 6.6 braucht ein Beispiel für conf/prices.toml (```toml)"
    write_prices(home, example.group(1))
    book = pricing.current_prices()
    assert book.problems == [], book.problems
    assert book.own, "Das Beispiel enthält keinen einzigen Preis"
