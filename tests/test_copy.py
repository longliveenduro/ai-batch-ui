"""Tests für den Kopierknopf unter jeder Antwort (Issue #35) und für plaintext.py, das den Text dafür liefert.

Der Knopf kopiert die Antwort als reinen Text, so wie man sie am Bildschirm liest: ohne Markdown-Zeichen und ohne
Formatierung. Die Erwartungen sind von Hand aus diesen Regeln abgeleitet und nicht mit dem Code der App gerechnet:
- Ein Zeilenumbruch mitten im Absatz wird wie am Bildschirm zum Leerzeichen, ein harter Umbruch bleibt einer.
- Absätze, Überschriften, Listen, Tabellen und Codeblöcke stehen durch eine Leerzeile getrennt.
- Aufzählungen beginnen mit „•“, nummerierte Listen mit ihrer Nummer, Unterpunkte sind eingerückt.
- Tabellenzellen sind durch Tabulatoren getrennt, ein Link steht als „Text (Adresse)“, ein Bild als sein Alt-Text.
- Formeln ($...$ und $$...$$), Code und HTML-Marken bleiben, wie sie sind.
"""
import json
import random

import pytest

from helpers import (TAB_JOBS, copy_buttons, copy_texts, finished_background, finished_batch, finished_claude_batch,
                     finished_openai_batch, new_app, row, sync_entry, write_history)

ui = pytest.mark.ui


def case(markdown, expected, name):
    return pytest.param(markdown, expected, id=name)


def with_rows(entry, *rows):
    entry["rows"] = list(rows)
    return entry


# ---------- plain_text(): was von der Auszeichnung wegfällt ----------
UNCHANGED = [
    case("Ein Satz.", "Ein Satz.", "ein-satz"),
    case("Erster Absatz.\n\nZweiter: äöüß € 😄.", "Erster Absatz.\n\nZweiter: äöüß € 😄.", "absaetze-umlaute"),
    case("Preis: 5 € & mehr; 2 * 3 * 4 = 24; a_b_c; 1 < 2 > 0; 50 %; (a) [b] {c}; ~5 bis ~10 Minuten",
         "Preis: 5 € & mehr; 2 * 3 * 4 = 24; a_b_c; 1 < 2 > 0; 50 %; (a) [b] {c}; ~5 bis ~10 Minuten",
         "zeichen-ohne-bedeutung"),
    case("Um 12:30 im Verhältnis 3:2, Datei snake_case_name.txt", "Um 12:30 im Verhältnis 3:2, Datei snake_case_name.txt",
         "uhrzeit-verhaeltnis-dateiname"),
]


@pytest.mark.parametrize("markdown, expected", UNCHANGED)
def test_text_without_markup_stays_as_it_is(app, markdown, expected):
    assert app.plain_text(markdown) == expected


INLINE = [
    case("**fett** und __fett__", "fett und fett", "fett"),
    case("*kursiv* und _kursiv_", "kursiv und kursiv", "kursiv"),
    case("***beides***", "beides", "fett-und-kursiv"),
    case("**fett mit *kursiv* darin**", "fett mit kursiv darin", "verschachtelt"),
    case("~~weg~~ und da", "weg und da", "durchgestrichen"),
    case("`Code` im Satz", "Code im Satz", "code-im-satz"),
    case("`**kein Fett**` im Code", "**kein Fett** im Code", "code-wird-nicht-gelesen"),
    case("# Titel\n\nText", "Titel\n\nText", "ueberschrift"),
    case("## Unter **titel** ##\nText darunter", "Unter titel\n\nText darunter", "ueberschrift-mit-abschluss"),
    case("Titel\n=====\nText", "Titel\n\nText", "ueberschrift-unterstrichen"),
    case("\\*kein Stern\\* und \\# kein Titel", "*kein Stern* und # kein Titel", "maskierte-zeichen"),
    case("&amp; &lt;b&gt; &copy; &#35;", "& <b> © #", "html-entitaeten"),
]


@pytest.mark.parametrize("markdown, expected", INLINE)
def test_markdown_characters_fall_away(app, markdown, expected):
    assert app.plain_text(markdown) == expected


LINE_BREAKS = [
    case("Zeile eins\nZeile zwei", "Zeile eins Zeile zwei", "weicher-umbruch-wird-leerzeichen"),
    case("Zeile eins  \nZeile zwei", "Zeile eins\nZeile zwei", "harter-umbruch-mit-leerzeichen"),
    case("Zeile eins\\\nZeile zwei", "Zeile eins\nZeile zwei", "harter-umbruch-mit-backslash"),
    case("A\n\n\n\nB", "A\n\nB", "viele-leerzeilen-werden-eine"),
]


@pytest.mark.parametrize("markdown, expected", LINE_BREAKS)
def test_line_breaks_are_kept_the_way_the_screen_shows_them(app, markdown, expected):
    assert app.plain_text(markdown) == expected


LISTS = [
    case("- Apfel\n- Birne", "• Apfel\n• Birne", "aufzaehlung"),
    case("* a\n* b\n\ntext\n\n+ c\n+ d", "• a\n• b\n\ntext\n\n• c\n• d", "stern-und-plus"),
    case("1. Erst\n2. Dann\n3. Zuletzt", "1. Erst\n2. Dann\n3. Zuletzt", "nummeriert"),
    case("3. drei\n4. vier", "3. drei\n4. vier", "erste-nummer-zaehlt"),
    case("1) eins\n2) zwei", "1. eins\n2. zwei", "klammer-nummer"),
    case("7. a\n7. b\n7. c", "7. a\n8. b\n9. c", "fortlaufend-wie-am-bildschirm"),
    case("- a\n  - b\n    - c\n- d", "• a\n  • b\n    • c\n• d", "unterpunkte"),
    case("1. a\n   - b\n2. c\n   1. d\n   2. e", "1. a\n   • b\n2. c\n   1. d\n   2. e", "gemischt-verschachtelt"),
    case("9. neun\n10. zehn\n    - sub", "9. neun\n10. zehn\n    • sub", "mehrstellige-nummer-rueckt-weiter-ein"),
    case("Text:\n- a\n- b", "Text:\n\n• a\n• b", "liste-nach-absatz"),
    case("- a\n\n- b", "• a\n\n• b", "lockere-liste-behaelt-leerzeile"),
    case("- erster\n\n  zweiter\n- b", "• erster\n\n  zweiter\n\n• b", "punkt-mit-zwei-absaetzen"),
    case("-\n- b", "•\n• b", "leerer-punkt"),
    case("- [x] erledigt\n- [ ] offen", "• [x] erledigt\n• [ ] offen", "aufgabenliste-behaelt-den-stand"),
    case("- Beispiel:\n\n  ```\n  code\n  ```\n- b", "• Beispiel:\n\n  code\n\n• b", "codeblock-im-punkt"),
    case("- eins  \n  zwei\n- drei", "• eins\n  zwei\n• drei", "harter-umbruch-im-punkt"),
]


@pytest.mark.parametrize("markdown, expected", LISTS)
def test_lists_keep_their_bullets_numbers_and_nesting(app, markdown, expected):
    assert app.plain_text(markdown) == expected


TABLES = [
    case("| Name | Wert |\n|---|---|\n| Alpha | 1 |\n| Beta | 22 |", "Name\tWert\nAlpha\t1\nBeta\t22", "tabelle"),
    case("| A | B |\n|:--|--:|\n| **x** | `y` |", "A\tB\nx\ty", "ausrichtung-und-auszeichnung"),
    case("| a \\| b | c |\n|---|---|\n| 1 | 2 |", "a | b\tc\n1\t2", "maskierter-strich"),
    case("| A | B | C |\n|---|---|---|\n| 1 | | 3 |", "A\tB\tC\n1\t\t3", "leere-zelle"),
    case("Davor\n\n| A |\n|---|\n| 1 |\n\nDanach", "Davor\n\nA\n1\n\nDanach", "zwischen-absaetzen"),
]


@pytest.mark.parametrize("markdown, expected", TABLES)
def test_a_table_becomes_lines_with_tab_separated_cells(app, markdown, expected):
    assert app.plain_text(markdown) == expected


CODE = [
    case("```python\ndef f(x):\n    return x * 2\n```", "def f(x):\n    return x * 2", "codeblock-ohne-zaun-und-sprache"),
    case("Davor\n\n```\nzeile 1\n\n\nzeile 4\n```\n\nDanach", "Davor\n\nzeile 1\n\n\nzeile 4\n\nDanach",
         "leerzeilen-im-code-bleiben"),
    case("Text:\n\n    eingerückt\n    zweite Zeile\n\nEnde.", "Text:\n\neingerückt\nzweite Zeile\n\nEnde.", "eingerueckter-code"),
    case("```\nnie geschlossen", "nie geschlossen", "offener-codeblock"),
    case("~~~\nTilden\n~~~", "Tilden", "tilden-zaun"),
    case("Davor\n\n```\n```\n\nDanach", "Davor\n\nDanach", "leerer-codeblock-faellt-weg"),
]


@pytest.mark.parametrize("markdown, expected", CODE)
def test_code_keeps_its_lines_and_loses_its_fences(app, markdown, expected):
    assert app.plain_text(markdown) == expected


LINKS = [
    case("[die Doku](https://example.com/doku)", "die Doku (https://example.com/doku)", "link-mit-adresse"),
    case('[Doku](https://example.com/doku "Titel")', "Doku (https://example.com/doku)", "titel-des-links-faellt-weg"),
    case("<https://example.org/x>", "https://example.org/x", "autolink"),
    case("[https://example.org](https://example.org)", "https://example.org", "text-ist-die-adresse"),
    case("[Example.org](https://example.org/)", "Example.org", "text-nennt-die-adresse"),
    case("<mail@example.org>", "mail@example.org", "mail-autolink"),
    case("[Mail](mailto:mail@example.org)", "Mail (mail@example.org)", "mail-link-ohne-mailto"),
    case("[Ref][1] und [kurz]\n\n[1]: https://a.example/eins\n[kurz]: https://a.example/zwei",
         "Ref (https://a.example/eins) und kurz (https://a.example/zwei)", "referenz-links"),
    case("[](https://x.example/a)", "https://x.example/a", "link-ohne-text"),
    case("# [Titel](https://t.example)\n\n| [A](https://a.example) |\n|---|\n| 1 |",
         "Titel (https://t.example)\n\nA (https://a.example)\n1", "link-in-ueberschrift-und-tabelle"),
    case("![Ein Bild](https://example.com/b.png)", "Ein Bild", "bild-als-alt-text"),
    case("![Alt mit **fett**](b.png)", "Alt mit fett", "alt-text-ohne-auszeichnung"),
    case("Vor ![](b.png)", "Vor", "bild-ohne-alt-text"),
]


@pytest.mark.parametrize("markdown, expected", LINKS)
def test_links_and_images_keep_what_a_reader_needs(app, markdown, expected):
    assert app.plain_text(markdown) == expected


QUOTES = [
    case("> Ein Zitat\n> über zwei Zeilen", "Ein Zitat über zwei Zeilen", "zitat"),
    case("> Erster\n>\n> Zweiter", "Erster\n\nZweiter", "zitat-mit-absaetzen"),
    case("> a\n>\n> > b", "a\n\nb", "zitat-im-zitat"),
    case("> - a\n> - b", "• a\n• b", "liste-im-zitat"),
    case("Oben\n\n---\n\nUnten", "Oben\n\nUnten", "trennlinie-faellt-weg"),
    case("***", "", "nur-eine-trennlinie"),
]


@pytest.mark.parametrize("markdown, expected", QUOTES)
def test_quotes_and_rules(app, markdown, expected):
    assert app.plain_text(markdown) == expected


def test_html_stays_text_because_the_screen_shows_it_as_text(app):
    assert app.plain_text("Ein <b>Tag</b> und <br> Umbruch") == "Ein <b>Tag</b> und <br> Umbruch"
    assert app.plain_text("<div>\nText\n</div>") == "<div> Text </div>"


FORMULAS = [
    case("Die Formel $x^2 + y^2 = z^2$ gilt.", "Die Formel $x^2 + y^2 = z^2$ gilt.", "formel-im-satz"),
    case("$$\\int_0^1 x\\,dx = \\tfrac{1}{2}$$", "$$\\int_0^1 x\\,dx = \\tfrac{1}{2}$$", "formel-block-backslash-komma"),
    case("Mit $a_1 * b_2 * c$ und $x_i*y_i*z_i$ gerechnet", "Mit $a_1 * b_2 * c$ und $x_i*y_i*z_i$ gerechnet",
         "sternchen-und-unterstriche-in-formeln"),
    case("$$\na = b\n\nc = d\n$$", "$$\na = b\n\nc = d\n$$", "formel-ueber-eine-leerzeile"),
    case("**fett** $x$ *kursiv*", "fett $x$ kursiv", "formel-neben-auszeichnung"),
    case("```\necho $$ und $$\n```", "echo $$ und $$", "dollar-im-codeblock"),
    case("Das kostet 5 $ und 6 $, dann $20.000 und $30.000, ab US$5-$10.",
         "Das kostet 5 $ und 6 $, dann $20.000 und $30.000, ab US$5-$10.", "geld-ist-keine-formel"),
    case("Nur \\$5 und \\$6 sind Geld", "Nur $5 und $6 sind Geld", "maskiertes-dollarzeichen"),
]


@pytest.mark.parametrize("markdown, expected", FORMULAS)
def test_formulas_stay_exactly_as_the_model_wrote_them(app, markdown, expected):
    assert app.plain_text(markdown) == expected


EMPTY_AND_SPACES = [
    case("", "", "leer"),
    case("   \n\n  ", "", "nur-leerraum"),
    case("\r\nA\r\n\r\nB\r\n", "A\n\nB", "windows-zeilenenden"),
    case("\n\n\nText\n\n\n", "Text", "umgebende-leerzeilen"),
    case("Text mit Ende   ", "Text mit Ende", "leerzeichen-am-ende"),
]


@pytest.mark.parametrize("markdown, expected", EMPTY_AND_SPACES)
def test_surrounding_blank_lines_and_spaces_are_dropped(app, markdown, expected):
    assert app.plain_text(markdown) == expected


def test_no_text_gives_an_empty_string(app):
    assert app.plain_text(None) == ""


def test_text_that_already_contains_the_placeholder_characters_is_left_alone(app):
    text = "x \ue0000\ue001 y $a$"  # die Zeichen, mit denen plain_text() Formeln schützt
    assert app.plain_text(text) == text


def test_a_realistic_answer_reads_as_plain_text(app):
    markdown = """## Zusammenfassung

Der **Abschnitt** beschreibt, wie Anna in die *Stadt* zieht. Sie findet dort:

1. **Eine Wohnung**: klein, aber hell.
2. **Arbeit** in einer Bäckerei:
   - früh aufstehen
   - Brot backen

| Ort | Dauer |
|:----|------:|
| Wohnung | 2 Wochen |

> „Das Leben ist schön“, sagt Anna.

---

Mehr dazu bei [der Stadt](https://example.com/anna)."""
    assert app.plain_text(markdown) == (
        "Zusammenfassung\n\n"
        "Der Abschnitt beschreibt, wie Anna in die Stadt zieht. Sie findet dort:\n\n"
        "1. Eine Wohnung: klein, aber hell.\n"
        "2. Arbeit in einer Bäckerei:\n"
        "   • früh aufstehen\n"
        "   • Brot backen\n\n"
        "Ort\tDauer\n"
        "Wohnung\t2 Wochen\n\n"
        "„Das Leben ist schön“, sagt Anna.\n\n"
        "Mehr dazu bei der Stadt (https://example.com/anna).")


# ---------- plain_text(): Eigenschaften über viele zufällige Texte (fester Startwert, also wiederholbar) ----------
WORDS = ["Anna", "Stadt", "Wohnung", "Bäckerei", "früh", "Brot", "Äpfel", "Straße", "zehn", "Haus"]
PATHS = ["a", "b", "doku", "seite"]  # nur ASCII: markdown-it-py schreibt Umlaute in Adressen prozentkodiert um


def random_markdown(rng):
    """Ein zufälliges Dokument aus den WORDS in allen Auszeichnungen und Blockarten. Gibt den Markdown-Text und die
    verwendeten Wörter zurück."""
    used = []

    def word():
        used.append(rng.choice(WORDS))
        return used[-1]

    def piece():
        return rng.choice([word, lambda: f"**{word()}**", lambda: f"*{word()}*", lambda: f"~~{word()}~~",
                           lambda: f"`{word()}`", lambda: f"[{word()}](https://example.org/{rng.choice(PATHS)})"])()

    def line():
        return " ".join(piece() for _ in range(rng.randint(1, 4)))

    blocks = [
        lambda: line(),
        lambda: "# " + line(),
        lambda: f"- {line()}\n- {line()}\n  - {line()}",
        lambda: f"1. {line()}\n2. {line()}",
        lambda: "> " + line(),
        lambda: f"| {line()} | {line()} |\n|---|---|\n| {line()} | {line()} |",
        lambda: f"```\n{word()}\n```",
    ]
    text = "\n\n".join(rng.choice(blocks)() for _ in range(rng.randint(1, 6)))
    return text, used


def test_no_word_is_lost_and_no_markdown_character_is_left(app):
    rng = random.Random(35)
    for _ in range(300):
        markdown, used = random_markdown(rng)
        plain = app.plain_text(markdown)
        assert all(word in plain for word in used), (markdown, plain)
        assert not any(mark in plain for mark in ("**", "~~", "`", "](", "# ", "|")), (markdown, plain)
        assert "\ue000" not in plain and "\ue001" not in plain


def test_any_text_converts_without_an_error(app):
    """Die Antwort eines Modells ist beliebiger Text: Die Umwandlung darf daran nie scheitern, sonst bliebe die Liste
    der Ergebnisse leer."""
    rng = random.Random(3501)
    alphabet = list("*_`#>-+|[]()!~$\\<&:;.,\n\n \t0123456789abcXYZäß€😄")
    for _ in range(800):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 90)))
        plain = app.plain_text(text)
        assert isinstance(plain, str) and "\ue000" not in plain and "\ue001" not in plain, text


# ---------- Kopierknopf unter jeder Antwort ----------
ANSWER = "## Ergebnis\n\nDie **Antwort** hat zwei Punkte:\n\n- eins\n- zwei\n\nSiehe [Doku](https://example.com/doku)."
ANSWER_PLAIN = "Ergebnis\n\nDie Antwort hat zwei Punkte:\n\n• eins\n• zwei\n\nSiehe Doku (https://example.com/doku)."


def copy_key(entry, prompt="prompt-1"):
    return f"copy:{entry['name']}:{prompt}"


@ui
def test_every_answer_has_a_copy_button_with_its_plain_text(use_all, home):
    entry = with_rows(finished_batch(prompts={"prompt-1": "Eins", "prompt-2": "Zwei"}), row(text=ANSWER),
                      row(key="prompt-2", prompt="Zwei", text="Zweite **Antwort**"))
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    assert copy_texts(at) == {copy_key(entry): ANSWER_PLAIN, copy_key(entry, "prompt-2"): "Zweite Antwort"}
    assert {proto.component_name for proto in copy_buttons(at)} == {"aibui_copy_text"}


@ui
def test_the_screen_still_shows_the_answer_as_markdown(use_all, home):
    write_history(home, [with_rows(finished_batch(), row(text=ANSWER))])
    at = new_app(TAB_JOBS)
    at.run()
    assert ANSWER in [m.value for m in at.markdown]  # gezeichnet wie bisher, gerendert von Streamlit
    assert ANSWER not in copy_texts(at).values()  # kopiert wird der Klartext, nicht der Quelltext


@ui
def test_an_answer_that_is_an_error_has_nothing_to_copy(use_all, home):
    entry = with_rows(finished_batch(prompts={"prompt-1": "Eins", "prompt-2": "Zwei"}), row(text=ANSWER),
                      row(key="prompt-2", prompt="Zwei", text="", error="Blockiert: SAFETY"))
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    assert list(copy_texts(at)) == [copy_key(entry)]  # nur die Antwort, nicht die Fehlermeldung von prompt-2
    assert any("Blockiert: SAFETY" in e.value for e in at.error)


KINDS = [
    pytest.param(lambda: with_rows(finished_batch(), row(text=ANSWER)), id="gemini-batch"),
    pytest.param(lambda: with_rows(finished_openai_batch(), row(text=ANSWER)), id="openai-batch"),
    pytest.param(lambda: with_rows(finished_claude_batch(), row(text=ANSWER)), id="claude-batch"),
    pytest.param(lambda: finished_background(rows=[row(text=ANSWER)]), id="hintergrund"),
    pytest.param(lambda: sync_entry(rows=[row(text=ANSWER)]), id="alter-synchroner-eintrag"),
]


@ui
@pytest.mark.parametrize("make_entry", KINDS)
def test_every_kind_of_entry_gets_the_copy_button(use_all, home, make_entry):
    entry = make_entry()
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    assert copy_texts(at) == {copy_key(entry): ANSWER_PLAIN}


@ui
def test_the_prompt_toggle_next_to_the_copy_button_still_works(use_all, home):
    entry = with_rows(finished_batch(prompts={"prompt-1": "Mein ganzer Prompt"}), row(prompt="Mein ganzer Prompt", text=ANSWER))
    write_history(home, [entry])
    at = new_app(TAB_JOBS)
    at.run()
    assert not any("Mein ganzer Prompt" in c.value for c in at.code)
    at.toggle(key=f"prompt:{entry['name']}:prompt-1").set_value(True).run()
    assert not at.exception
    assert any("Mein ganzer Prompt" in c.value for c in at.code)  # der Schalter zeigt den Prompt wie bisher
    assert copy_texts(at) == {copy_key(entry): ANSWER_PLAIN}  # und der Knopf bleibt, mit demselben Text


@ui
def test_a_long_answer_is_passed_on_in_full(use_all, home):
    long_answer = "\n\n".join(f"Absatz {n} mit **Text** und einer Zahl: {n * 7}." for n in range(1500))
    write_history(home, [with_rows(finished_batch(), row(text=long_answer))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    [text] = copy_texts(at).values()
    assert len(long_answer) > 60_000 and text.startswith("Absatz 0 mit Text und einer Zahl: 0.")
    assert text.endswith("Absatz 1499 mit Text und einer Zahl: 10493.") and text.count("\n\n") == 1499
    assert "**" not in text


@ui
def test_the_answer_reaches_the_component_as_data_and_never_as_its_code(use_all, app, home):
    """Die Antwort eines Modells ist keine vertrauenswürdige Eingabe: Sie darf nie in das HTML, CSS oder JavaScript der
    Komponente geraten, sonst könnte ein Text wie </script><script>…</script> Code in der App ausführen."""
    hostile = "</script><script>alert(1)</script><img src=x onerror=alert(2)> \"'`${x}"
    write_history(home, [with_rows(finished_batch(prompts={"prompt-1": "Eins", "prompt-2": "Zwei"}), row(text=hostile),
                                   row(key="prompt-2", prompt="Zwei", text="Harmlos"))])
    at = new_app(TAB_JOBS)
    at.run()
    assert not at.exception
    protos = copy_buttons(at)
    assert [json.loads(p.json)["text"] for p in protos] == [app.plain_text(hostile), "Harmlos"]
    assert len({(p.html_content, p.css_content, p.js_content) for p in protos}) == 1  # der Code ist für alle gleich
    for code in (protos[0].html_content, protos[0].css_content, protos[0].js_content):
        assert "alert" not in code and "onerror" not in code and "${x}" not in code


def test_the_copy_script_writes_plain_text_only(app):
    """Der Kopierknopf soll keine Formatierung in die Zwischenablage legen (Issue #35): writeText() schreibt nur text/plain,
    kein HTML (kein ClipboardItem, kein Format text/html) und auch nicht Markdown."""
    js = app.COPY_JS
    assert "navigator.clipboard.writeText(text)" in js and 'execCommand("copy")' in js  # der zweite ist der Ausweg
    assert "ClipboardItem" not in js and "text/html" not in js and "innerHTML" not in js


def test_the_component_is_registered_once_and_not_for_every_answer(app, monkeypatch):
    app.copy_component.clear()  # der Cache von st.cache_resource überlebt den frischen Import des Pakets
    calls = []
    real = app.st.components.v2.component
    monkeypatch.setattr(app.st.components.v2, "component", lambda *a, **k: calls.append(a) or real(*a, **k))
    first, second = app.copy_component(), app.copy_component()
    assert first is second and len(calls) == 1
