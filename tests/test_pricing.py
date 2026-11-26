"""Tests der Kosten-Infobox (Issue #12): Preistabelle, Zuordnung des Modellnamens, Preiswechsel, Text der Infobox und
Oberfläche.

Die Preise in den Tests sind die der Preisseiten der Anbieter (Stand PRICES_AS_OF, Quellen in der README, Abschnitt 13).
Ob sie heute noch stimmen, prüft kein Test, das kann nur ein Blick auf die Preisseiten.
"""
import re
from datetime import date
from decimal import Decimal as D

import pytest

from helpers import (APP_PATH, PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, ROOT, new_app, new_claude_app,
                     new_openai_app, type_model)

ui = pytest.mark.ui
BEFORE, CHANGE = date(2026, 11, 20), date(2026, 12, 1)  # Tag vor dem Preiswechsel bei Gemini 4 und sein erster Tag
HEADER = ["| | Eingabe | Ausgabe | Cache |", "|---|--:|--:|--:|"]


def box(at):
    """Text der Infobox mit den Kosten in der Seitenleiste, None wenn es sie nicht gibt."""
    found = [i.value for i in at.sidebar.info if i.value.startswith("**Kosten in USD")]
    assert len(found) <= 1
    return found[0] if found else None


def stand_captions(at):
    return [c for c in at.sidebar.caption if "Stand der Preise" in c.value]


# ---------- Tabelle ----------
def test_the_price_table_is_well_formed(pricing):
    prefixes = {PROVIDER_GEMINI: "gemini-", PROVIDER_OPENAI: "gpt-", PROVIDER_CLAUDE: "claude-"}
    assert set(pricing.PRICES) == set(prefixes)
    for provider, models in pricing.PRICES.items():
        assert 1 <= len(models) <= pricing.MAX_MODELS, (
            f"{provider}: Die Auswahl zeigt höchstens {pricing.MAX_MODELS} Modelle")
        for name, periods in models.items():
            assert name.startswith(prefixes[provider]) and name == name.lower() and name == name.strip()
            assert periods[0][0] is None  # der erste Preisstand gilt von jeher
            starts = [p[0] for p in periods[1:]]
            assert None not in starts and starts == sorted(set(starts))
            for _, tiers in periods:
                bounds = [t[0] for t in tiers]
                assert bounds[-1] is None and None not in bounds[:-1] and bounds[:-1] == sorted(set(bounds[:-1]))
                for _, price_in, price_out, cached in tiers:
                    assert 0 < cached < price_in < price_out, f"{name}: Die Preise ergeben keinen Sinn"


def test_every_model_the_list_offers_has_a_price(app):
    """Die Auswahl im Feld „Modell“ kommt aus der Tabelle (Issue #11): Zu jedem Modell darin gibt es also einen Preis,
    am Tag der Tests wie vor und nach dem Preiswechsel. Auch die Voreinstellung (Issue #45) hat einen."""
    for provider in app.PROVIDERS:
        for day in (BEFORE, CHANGE, app.PRICES_AS_OF):
            names = app.model_choices(provider, day)
            assert names and app.default_model(provider, day) in names
            for name in names:
                assert app.find_model(provider, name) == name
                assert app.model_costs(provider, name, day)["rows"]
    assert app.find_model(PROVIDER_GEMINI, "gemini-4-argon") == "gemini-4-argon"  # der Vorgänger von Carbon


@pytest.mark.parametrize("provider, typed, expected", [
    (PROVIDER_GEMINI, "gemini-4-carbon", "gemini-4-carbon"),
    (PROVIDER_GEMINI, "  Gemini-4-Carbon ", "gemini-4-carbon"),  # Großschreibung und Leerzeichen zählen nicht
    (PROVIDER_GEMINI, "models/gemini-4-argon", "gemini-4-argon"),  # so nennt die Gemini API ihre Modelle
    (PROVIDER_OPENAI, "gpt-6-astra-2026-09-01", "gpt-6-astra"),  # ein angehängter Stand zählt nicht
    (PROVIDER_OPENAI, "gpt-6.2-astra-2026-11-01", "gpt-6.2-astra"),
    (PROVIDER_OPENAI, "gpt-6.1-sol", None),  # steht nicht mehr in der Tabelle: Das 6.2er Modell löste es ab
    (PROVIDER_GEMINI, "models/gemini-4-neon", "gemini-4-neon"),
    (PROVIDER_GEMINI, "Gemini-4-Hydrogen", "gemini-4-hydrogen"),
    (PROVIDER_CLAUDE, "claude-sonnet-5-5-20261001", "claude-sonnet-5-5"),
    (PROVIDER_OPENAI, "gpt-6-astra-pro", None),  # eine andere Fassung hat einen anderen Preis
    (PROVIDER_OPENAI, "gpt-6", None),
    (PROVIDER_CLAUDE, "claude-opus-5", None),  # Opus 5 ist nicht Opus 5.5
    (PROVIDER_CLAUDE, "gpt-6-astra", None),  # der Name gehört zu einem anderen Anbieter
    (PROVIDER_GEMINI, "", None),
])
def test_find_model(pricing, provider, typed, expected):
    assert pricing.find_model(provider, typed) == expected


# ---------- Kosten ----------
def test_a_claude_model_has_only_the_batch_price(pricing):
    costs = pricing.model_costs(PROVIDER_CLAUDE, "claude-sonnet-5-5", BEFORE)
    assert costs == {"model": "claude-sonnet-5-5", "rows": [("Batch", D("1"), D("5"), D("0.05"))], "later": [],
                     "custom": False}  # custom: die Preise stehen nicht in conf/prices.toml (Issue #39)


def test_gemini_has_the_batch_and_the_background_price_and_announces_the_price_change(pricing):
    costs = pricing.model_costs(PROVIDER_GEMINI, "gemini-4-carbon", BEFORE)
    assert costs["rows"] == [("Batch", D("1"), D("5"), D("0.05")),
                             ("Hintergrund (Long Decode)", D("2"), D("10"), D("0.10"))]
    assert costs["later"] == [(CHANGE, [("Batch", D("2"), D("10"), D("0.10")),
                                        ("Hintergrund (Long Decode)", D("4"), D("20"), D("0.20"))])]


def test_the_price_change_applies_from_its_first_day(pricing):
    last_day = pricing.model_costs(PROVIDER_GEMINI, "gemini-4-argon", date(2026, 11, 30))
    assert last_day["rows"][0][1] == D("1") and last_day["later"][0][0] == CHANGE
    first_day = pricing.model_costs(PROVIDER_GEMINI, "gemini-4-argon", CHANGE)
    assert first_day["rows"][0][1:] == (D("2"), D("10"), D("0.10")) and first_day["later"] == []
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-argon", date(2027, 6, 1))["rows"][0][1] == D("2")


def test_without_a_date_the_costs_are_those_of_today(pricing, on_day):
    on_day(date(2026, 12, 24))
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-carbon")["rows"][0][1] == D("2")
    on_day(BEFORE)
    assert pricing.model_costs(PROVIDER_GEMINI, "gemini-4-carbon")["rows"][0][1] == D("1")


def test_a_model_without_a_price_has_no_costs(pricing):
    assert pricing.model_costs(PROVIDER_OPENAI, "gpt-9-nova", BEFORE) is None


def test_batch_costs_half_of_the_standard_price_and_the_background_mode_the_full_price(pricing):
    for provider, models in pricing.PRICES.items():
        for name, periods in models.items():
            for since, tiers in periods:
                rows = pricing.model_costs(provider, name, since or date(2000, 1, 1))["rows"]
                standard = [t[1:] for t in tiers]
                batch = [r[1:] for r in rows if r[0].startswith("Batch")]
                background = [r[1:] for r in rows if r[0].startswith("Hintergrund")]
                assert batch == [tuple(p / 2 for p in t) for t in standard], name
                assert background == (standard if provider == PROVIDER_GEMINI else []), name


def test_long_prompts_have_their_own_price_tier(pricing):
    haiku = pricing.model_costs(PROVIDER_CLAUDE, "claude-haiku-5-5", BEFORE)["rows"]
    assert haiku == [("Batch, Prompt bis 100.000 Token", D("0.05"), D("0.25"), D("0.005")),
                     ("Batch, Prompt über 100.000 Token", D("0.25"), D("1.25"), D("0.025"))]
    astra = pricing.model_costs(PROVIDER_OPENAI, "gpt-6-astra", BEFORE)["rows"]
    assert astra == [("Batch, Prompt bis 272.000 Token", D("5"), D("25"), D("0.5")),
                     ("Batch, Prompt über 272.000 Token", D("10"), D("37.5"), D("1"))]


def test_a_middle_tier_names_both_limits(pricing, monkeypatch):
    tiers = [(1000, D("1"), D("2"), D("0.1")), (5000, D("2"), D("4"), D("0.2")), (None, D("3"), D("6"), D("0.3"))]
    monkeypatch.setattr(pricing, "PRICES", {PROVIDER_CLAUDE: {"claude-test": [(None, tiers)]}})
    names = [r[0] for r in pricing.model_costs(PROVIDER_CLAUDE, "claude-test", BEFORE)["rows"]]
    assert names == ["Batch, Prompt bis 1.000 Token", "Batch, Prompt über 1.000 bis 5.000 Token",
                     "Batch, Prompt über 5.000 Token"]


@pytest.mark.parametrize("value, text", [
    (D("2"), "2,00"), (D("10.5"), "10,50"), (D("37.5"), "37,50"), (D("0.05"), "0,05"), (D("0.005"), "0,005"),
    (D("0.0375"), "0,0375"), (D("0.10") * D("0.5"), "0,05"), (D("100"), "100,00"),
])
def test_price_text(pricing, value, text):
    assert pricing.price_text(value) == text


# ---------- Text der Infobox ----------
def test_the_info_box_text_for_a_gemini_model_with_a_coming_price_change(pricing):
    text = pricing.costs_markdown(PROVIDER_GEMINI, "gemini-4-carbon", BEFORE)
    assert text.split("\n") == [
        "**Kosten in USD je 1 Mio. Token:** `gemini-4-carbon`", "", *HEADER,
        "| Batch | 1,00 | 5,00 | 0,05 |",
        "| Hintergrund (Long Decode) | 2,00 | 10,00 | 0,10 |",
        "", "**Ab 01.12.2026**", "", *HEADER,
        "| Batch | 2,00 | 10,00 | 0,10 |",
        "| Hintergrund (Long Decode) | 4,00 | 20,00 | 0,20 |",
    ]


def test_the_texts_have_no_dollar_sign_because_streamlit_would_read_it_as_a_formula(pricing):
    for provider, models in pricing.PRICES.items():
        for name in models:
            assert "$" not in pricing.costs_markdown(provider, name, BEFORE)
        assert "$" not in pricing.costs_markdown(provider, "unbekannt", BEFORE)
        assert "$" not in pricing.costs_help(provider)
    assert "$" not in pricing.costs_caption()


def test_an_unknown_model_gets_a_hint_instead_of_a_price(pricing):
    text = pricing.costs_markdown(PROVIDER_OPENAI, "gpt-9 `nova`", BEFORE)
    assert "kein Preis hinterlegt" in text and "`gpt-9 nova`" in text  # Backticks der Eingabe fallen weg
    assert all(f"`{name}`" in text for name in pricing.PRICES[PROVIDER_OPENAI]) and "|" not in text


def test_without_a_model_name_there_is_no_text(pricing):
    assert pricing.costs_markdown(PROVIDER_GEMINI, "", BEFORE) is None
    assert pricing.costs_markdown(PROVIDER_GEMINI, "   ", BEFORE) is None


def test_the_caption_names_the_date_of_the_prices_and_the_help_the_differences_of_the_provider(pricing):
    assert f"Stand der Preise: {pricing.PRICES_AS_OF:%d.%m.%Y}" in pricing.costs_caption()
    assert "Hintergrund-Modus" in pricing.costs_help(PROVIDER_GEMINI)
    assert not any("Hintergrund" in pricing.costs_help(p) for p in (PROVIDER_OPENAI, PROVIDER_CLAUDE))
    label = "Dateien im Prompt-Cache halten"  # so heißt das Kästchen in der App
    assert label in pricing.costs_help(PROVIDER_CLAUDE) and label in APP_PATH.read_text(encoding="utf-8")
    assert label not in pricing.costs_help(PROVIDER_GEMINI) and label not in pricing.costs_help(PROVIDER_OPENAI)


def test_the_date_of_the_prices_is_named_with_its_constant_in_the_readme(pricing):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    day = f"{pricing.PRICES_AS_OF:%d.%m.%Y}"
    assert re.search(rf"{day}[^\n]*`PRICES_AS_OF`|`PRICES_AS_OF`[^\n]*{day}", readme), (
        f"Die README muss den Stand {day} der Preise nennen, zusammen mit `PRICES_AS_OF`")


# ---------- Oberfläche ----------
@ui
def test_the_sidebar_shows_the_costs_of_the_gemini_model(use_all, on_day, pricing):
    on_day(BEFORE)
    at = new_app()
    at.run()
    at.selectbox(key="model_gemini").set_value("gemini-4-carbon")  # vor dem Preiswechsel ist Neon vorausgewählt
    at.run()
    assert not at.exception
    text = box(at)
    assert "`gemini-4-carbon`" in text
    assert "| Batch | 1,00 | 5,00 | 0,05 |" in text and "| Hintergrund (Long Decode) | 2,00 | 10,00 | 0,10 |" in text
    assert "**Ab 01.12.2026**" in text and "| Hintergrund (Long Decode) | 4,00 | 20,00 | 0,20 |" in text
    [note] = stand_captions(at)
    assert f"{pricing.PRICES_AS_OF:%d.%m.%Y}" in note.value and "Long Decode" in note.help


@ui
def test_the_costs_follow_the_date_of_the_price_change(use_all, on_day):
    on_day(CHANGE)
    at = new_app()
    at.run()
    assert not at.exception
    text = box(at)
    assert "| Batch | 2,00 | 10,00 | 0,10 |" in text and "| Hintergrund (Long Decode) | 4,00 | 20,00 | 0,20 |" in text
    assert "Ab 01.12.2026" not in text


@ui
@pytest.mark.real_date
def test_the_info_box_works_with_the_real_date(use_all):
    at = new_app()
    at.run()
    assert not at.exception and "| Batch |" in box(at) and "| Hintergrund (Long Decode) |" in box(at)


@ui
def test_the_costs_follow_the_model_field(use_all, on_day):
    on_day(BEFORE)
    at = new_app()
    at.run()
    at.selectbox(key="model_gemini").set_value("gemini-4-argon")
    at.run()
    assert not at.exception and "`gemini-4-argon`" in box(at) and len(stand_captions(at)) == 1
    type_model(at, "model_gemini", "gemini-9-xenon")  # ein getippter Name, den die Tabelle nicht kennt
    assert not at.exception and "kein Preis hinterlegt" in box(at) and "`gemini-9-xenon`" in box(at)
    assert not stand_captions(at)  # ohne Preis gibt es keinen Stand


@ui
def test_the_sidebar_shows_the_batch_costs_of_the_openai_model(use_all, on_day):
    on_day(BEFORE)
    at = new_openai_app()
    at.run()
    assert not at.exception
    text = box(at)
    assert "`gpt-6.2-astra`" in text and "Hintergrund" not in text  # vorausgewählt: das beste Modell (Issue #45)
    assert "| Batch, Prompt bis 272.000 Token | 4,00 | 20,00 | 0,20 |" in text
    assert "| Batch, Prompt über 272.000 Token | 8,00 | 30,00 | 0,40 |" in text
    at.selectbox(key="model_openai").set_value("gpt-6-astra")  # das ältere und teurere Modell
    at.run()
    assert not at.exception and "`gpt-6-astra`" in box(at)
    assert "| Batch, Prompt bis 272.000 Token | 5,00 | 25,00 | 0,50 |" in box(at)
    assert "| Batch, Prompt über 272.000 Token | 10,00 | 37,50 | 1,00 |" in box(at)
    at.selectbox(key="model_openai").set_value("gpt-6-luna")
    at.run()
    assert not at.exception and "`gpt-6-luna`" in box(at)
    assert "| Batch, Prompt bis 272.000 Token | 0,05 | 0,25 | 0,005 |" in box(at)


@ui
def test_the_sidebar_shows_the_batch_costs_of_the_claude_model(use_all, on_day):
    on_day(BEFORE)
    at = new_claude_app()
    at.run()
    at.selectbox(key="model_claude").set_value("claude-sonnet-5-5")  # vorausgewählt ist das teuerste: Fable
    at.run()
    assert not at.exception
    text = box(at)
    assert "`claude-sonnet-5-5`" in text and "Hintergrund" not in text and "| Batch | 1,00 | 5,00 | 0,05 |" in text
    [note] = stand_captions(at)
    assert "Prompt-Cache" in note.help  # Hinweis auf das Kästchen, ohne das es keine Cache-Treffer gibt
    at.selectbox(key="model_claude").set_value("claude-haiku-5-5")
    at.run()
    assert not at.exception and "| Batch, Prompt über 100.000 Token | 0,25 | 1,25 | 0,025 |" in box(at)


@ui
def test_the_costs_follow_the_provider(use_all, on_day, pricing):
    on_day(BEFORE)
    at = new_app()
    at.run()
    for provider in (PROVIDER_OPENAI, PROVIDER_CLAUDE, PROVIDER_GEMINI):
        model = pricing.default_model(provider)  # jeder Anbieter zeigt die Kosten seines vorausgewählten Modells
        at.radio(key="provider").set_value(provider)
        at.run()
        assert not at.exception and f"`{model}`" in box(at), provider
        assert ("Hintergrund (Long Decode)" in box(at)) == (provider == PROVIDER_GEMINI)


@ui
def test_the_costs_are_shown_even_without_an_api_key(monkeypatch, on_day, pricing):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    on_day(BEFORE)
    at = new_app()
    at.run()
    assert not at.exception and any("Gemini API-Key" in i.value for i in at.info)
    assert f"`{pricing.default_model(PROVIDER_GEMINI)}`" in box(at)
