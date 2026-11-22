"""Tests der Modell-Combobox (Issue #11): Die Liste der Modelle kommt aus der Preistabelle, das teuerste steht vorn und
ist vorausgewählt, und ein anderer Name lässt sich eintippen.

Die Preise und die Reihenfolge in den Tests sind die der Preisseiten (Stand PRICES_AS_OF, Quellen in der README,
Abschnitt 13). Ob sie heute noch stimmen, prüft kein Test.
"""
from datetime import date
from decimal import Decimal as D

import pytest

from fakes import FakeGemini, install
from helpers import (PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, TAB_JOBS, click, model_field, new_app,
                     openai_entry, set_prompts, type_model, write_history)

ui = pytest.mark.ui
BEFORE, CHANGE = date(2026, 11, 20), date(2026, 12, 1)  # Tag vor dem Preiswechsel bei Gemini 4 und sein erster Tag
OPENAI_LIST = ["gpt-6-astra", "gpt-6.2-astra", "gpt-6.2-sol", "gpt-6.1-terra", "gpt-6-luna"]
CLAUDE_LIST = ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
KEYS = {PROVIDER_GEMINI: "model_gemini", PROVIDER_OPENAI: "model_openai", PROVIDER_CLAUDE: "model_claude"}


# ---------- Liste und Voreinstellung (Logik) ----------
@pytest.mark.parametrize("provider, day, expected", [
    # Vor dem Preiswechsel ist Neon (3/15) teurer als Carbon und Argon (2/10), danach sind sie es (4/20)
    (PROVIDER_GEMINI, BEFORE, ["gemini-4-neon", "gemini-4-carbon", "gemini-4-argon", "gemini-4-hydrogen"]),
    (PROVIDER_GEMINI, CHANGE, ["gemini-4-carbon", "gemini-4-argon", "gemini-4-neon", "gemini-4-hydrogen"]),
    # gpt-6-astra (10/50) steht vor dem neueren gpt-6.2-astra (8/40): Die Reihenfolge folgt dem Preis, nicht dem Alter
    (PROVIDER_OPENAI, BEFORE, OPENAI_LIST),
    (PROVIDER_OPENAI, CHANGE, OPENAI_LIST),
    (PROVIDER_CLAUDE, BEFORE, CLAUDE_LIST),
    (PROVIDER_CLAUDE, CHANGE, CLAUDE_LIST),
])
def test_the_list_is_the_price_table_sorted_by_cost_from_high_to_low(pricing, provider, day, expected):
    assert pricing.model_choices(provider, day) == expected
    assert set(expected) == set(pricing.PRICES[provider])  # nichts fehlt, nichts kommt dazu


def test_the_costs_never_rise_along_the_list(pricing):
    for provider in pricing.PRICES:
        for day in (BEFORE, CHANGE, date(2027, 6, 1)):
            names = pricing.model_choices(provider, day)
            outputs = [pricing.model_costs(provider, name, day)["rows"][0][2] for name in names]  # erste Zeile: Batch
            assert outputs == sorted(outputs, reverse=True), f"{provider} am {day}: {names}"


def test_models_with_the_same_price_keep_the_order_of_the_table(pricing, monkeypatch):
    same = [(None, [(None, D("2"), D("10"), D("0.10"))])]
    cheap = [(None, [(None, D("1"), D("5"), D("0.05"))])]
    dear = [(None, [(None, D("3"), D("15"), D("0.15"))])]
    monkeypatch.setattr(pricing, "PRICES", {"X": {"zweites": same, "billig": cheap, "erstes": same, "teuer": dear}})
    assert pricing.model_choices("X", BEFORE) == ["teuer", "zweites", "erstes", "billig"]  # nicht nach dem Alphabet
    assert pricing.model_choices(PROVIDER_GEMINI, BEFORE) == []  # ein Anbieter ohne Eintrag: leere Liste
    monkeypatch.undo()
    assert pricing.model_choices(PROVIDER_GEMINI, CHANGE)[:2] == ["gemini-4-carbon", "gemini-4-argon"]  # Gleichstand


def test_the_list_follows_the_day_and_without_a_day_it_is_today(pricing, on_day):
    on_day(BEFORE)
    assert pricing.model_choices(PROVIDER_GEMINI)[0] == "gemini-4-neon"
    on_day(CHANGE)
    assert pricing.model_choices(PROVIDER_GEMINI)[0] == "gemini-4-carbon"


def test_the_default_is_the_first_entry_of_the_list(pricing):
    assert pricing.default_model(PROVIDER_GEMINI, BEFORE) == "gemini-4-neon"
    assert pricing.default_model(PROVIDER_GEMINI, CHANGE) == "gemini-4-carbon"
    assert pricing.default_model(PROVIDER_OPENAI, BEFORE) == "gpt-6-astra"  # wie bisher
    assert pricing.default_model(PROVIDER_CLAUDE, BEFORE) == "claude-fable-5-2"  # bisher Sonnet 5.5, ein Viertel des Preises
    for provider in pricing.PRICES:
        assert pricing.default_model(provider, BEFORE) == pricing.model_choices(provider, BEFORE)[0]


def test_the_hint_for_an_unknown_model_names_the_known_ones_in_the_order_of_the_list(pricing):
    for day in (BEFORE, CHANGE):
        text = pricing.costs_markdown(PROVIDER_GEMINI, "gemini-9-xenon", day)
        names = ", ".join(f"`{name}`" for name in pricing.model_choices(PROVIDER_GEMINI, day))
        assert f"(bekannt: {names})" in text, day


@pytest.mark.real_date
def test_the_list_works_with_the_real_date(pricing):
    for provider in pricing.PRICES:
        assert pricing.model_choices(provider) and pricing.default_model(provider) == pricing.model_choices(provider)[0]


# ---------- Oberfläche: Liste und Voreinstellung ----------
@ui
def test_every_provider_offers_its_models_the_most_expensive_first_and_preselects_it(use_all, on_day, pricing):
    on_day(BEFORE)
    at = new_app()
    at.run()
    for provider in (PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDER_CLAUDE):
        at.radio(key="provider").set_value(provider)
        at.run()
        assert not at.exception, provider
        box = model_field(at)
        expected = pricing.model_choices(provider, BEFORE)
        assert box.key == KEYS[provider] and box.options == expected and box.value == expected[0], provider
        assert box.proto.accept_new_options is True, "ohne das ließe sich kein anderer Name eintippen"
        assert box.proto.required is True, "das Feld lässt sich nicht leeren"
        assert "das teuerste zuerst" in box.help and "eintippen" in box.help


@ui
def test_the_preselected_gemini_model_follows_the_day_for_a_new_session_only(use_all, on_day):
    on_day(BEFORE)
    at = new_app()
    at.run()
    assert model_field(at).value == "gemini-4-neon"
    on_day(CHANGE)
    at.run()  # dieselbe Sitzung: Sie behält ihre Wahl, nur die Liste folgt dem Tag
    assert model_field(at).value == "gemini-4-neon" and model_field(at).options[0] == "gemini-4-carbon"
    fresh = new_app()
    fresh.run()  # eine neue Sitzung wählt den ersten Eintrag der Liste von heute
    assert model_field(fresh).value == "gemini-4-carbon"


@ui
def test_the_list_is_shown_without_an_api_key(monkeypatch, pricing):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    at = new_app()
    at.run()
    assert not at.exception and any("Gemini API-Key" in i.value for i in at.info)
    assert model_field(at).options == pricing.model_choices(PROVIDER_GEMINI)


@ui
def test_only_the_field_model_is_a_combobox(use_all):
    at = new_app()
    at.run()
    assert [s.key for s in at.sidebar.selectbox if s.label == "Modell"] == ["model_gemini"]
    assert not [t for t in at.text_input if t.label == "Modell"]
    name_model = at.text_input(key="name_model")  # „Modell für die Namen“ bleibt ein Textfeld
    assert name_model.label == "Modell für die Namen" and name_model.value == "gemini-3.5-flash-lite"


# ---------- Oberfläche: Auswahl und freie Eingabe ----------
@ui
def test_a_model_picked_from_the_list_is_the_one_the_batch_is_started_with(monkeypatch):
    fake = install(monkeypatch, FakeGemini())
    at = new_app()
    at.run()
    model_field(at).set_value("gemini-4-hydrogen")
    set_prompts(at, "Frage")
    click(at, "Batch starten")
    assert not at.exception and fake.created_batches[0][0] == "gemini-4-hydrogen"


@ui
@pytest.mark.parametrize("provider, typed", [(PROVIDER_GEMINI, "gemini-9-xenon"), (PROVIDER_OPENAI, "gpt-9-nova"),
                                             (PROVIDER_CLAUDE, "claude-opus-9")])
def test_a_typed_model_is_kept_and_stays_in_the_list_until_another_one_is_picked(use_all, pricing, provider, typed):
    at = new_app()
    at.run()
    at.radio(key="provider").set_value(provider)
    at.run()
    listed = pricing.model_choices(provider)
    type_model(at, KEYS[provider], typed)
    assert not at.exception
    assert model_field(at).value == typed and model_field(at).options == listed + [typed]  # der eigene Name steht hinten
    at.run()  # ein weiterer Lauf ändert nichts
    assert not at.exception and model_field(at).value == typed and model_field(at).options == listed + [typed]
    model_field(at).set_value(listed[1])
    at.run()
    assert model_field(at).value == listed[1] and model_field(at).options == listed  # er verschwindet wieder


@ui
def test_a_model_the_table_no_longer_lists_stays_usable_from_the_history(use_all, home, pricing):
    """gpt-6.1-sol stand vor Issue #11 in der Tabelle. Einträge im Verlauf mit diesem Modell lassen sich weiter
    übernehmen: Der Name steht dann hinter der Liste im Feld, nur die Preise fehlen in der Infobox."""
    entry = openai_entry(model="gpt-6.1-sol", prompts={"prompt-1": "Eins"})
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    at.button(key="reuse:" + entry["name"]).click()
    at.run()
    assert not at.exception and at.radio(key="provider").value == PROVIDER_OPENAI
    box = model_field(at)
    assert box.value == "gpt-6.1-sol" and box.options == pricing.model_choices(PROVIDER_OPENAI) + ["gpt-6.1-sol"]
    assert any("kein Preis hinterlegt" in i.value for i in at.sidebar.info)
