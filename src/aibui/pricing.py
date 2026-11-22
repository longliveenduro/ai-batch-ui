"""Preise der Modelle (Issue #12): Preistabelle je Anbieter und Modell und die Kosten des gewählten Modells als Text für
die Infobox in der Seitenleiste. Dieselbe Tabelle liefert die Auswahl im Feld „Modell“ (Issue #11). Ohne Streamlit.

Die Anbieter nennen ihre Preise nicht über die API, darum stehen sie fest in PRICES (Stand: PRICES_AS_OF, Quellen in der
README, Abschnitt 13). Ändert sich ein Preis oder kommt ein Modell dazu, wird nur diese Tabelle angepasst (README,
Abschnitt 9.2). Aus demselben Grund kommt auch die Liste der Modelle aus der Tabelle und nicht aus der Modellliste der
API: Die Modelllisten der Anbieter nennen keine Preise, eine Sortierung nach Kosten wäre damit nicht möglich.
"""
from datetime import date
from decimal import Decimal as D

from .config import PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI

PRICES_AS_OF = date(2026, 11, 21)  # Tag, an dem die Tabelle mit den Preisseiten der Anbieter abgeglichen wurde
BATCH_FACTOR = D("0.5")  # Batch kostet bei Gemini, OpenAI und Claude die Hälfte des Standardpreises
MAX_MODELS = 5  # so viele Modelle zeigt die Auswahl je Anbieter höchstens: die aktuellen (ein Test prüft die Tabelle)

# Preise in USD je 1 Mio. Token im Standardtarif. Je Modell eine Liste von Preisständen (gültig ab, Stufen), der erste
# gilt von jeher. Eine Stufe ist (Prompt bis … Token, Eingabe, Ausgabe, Eingabe aus dem Cache), die Ausgabe schließt die
# Denk-Token ein. Die letzte Stufe hat keine Obergrenze: Ist der Prompt länger als die Grenze der Stufe davor, gilt ihr
# Preis für die ganze Anfrage.
# Die Tabelle ist auch die Liste der Modelle im Feld „Modell“ (model_choices()): höchstens MAX_MODELS je Anbieter, die
# aktuellen. Bei gleichem Preis gilt die Reihenfolge hier.
_GEMINI_4 = [  # Carbon und Argon: Einführungspreis bis 30.11.2026, ab 01.12.2026 doppelt so hoch
    (None, [(None, D("2"), D("10"), D("0.10"))]),
    (date(2026, 12, 1), [(None, D("4"), D("20"), D("0.20"))]),
]
PRICES = {
    PROVIDER_GEMINI: {  # Gemini 4: Der Preis gilt für das ganze 1-Mio.-Fenster, ohne Stufen nach der Länge des Prompts
        "gemini-4-carbon": _GEMINI_4,
        "gemini-4-argon": _GEMINI_4,
        "gemini-4-neon": [(None, [(None, D("3"), D("15"), D("0.15"))])],
        "gemini-4-hydrogen": [(None, [(None, D("1.50"), D("7.50"), D("0.075"))])],
    },
    PROVIDER_OPENAI: {  # ab 272.000 Eingabe-Token: Eingabe und Cache das Doppelte, Ausgabe das 1,5-fache
        "gpt-6-astra": [(None, [(272_000, D("10"), D("50"), D("1")),
                                (None, D("20"), D("75"), D("2"))])],
        "gpt-6.2-astra": [(None, [(272_000, D("8"), D("40"), D("0.40")),
                                  (None, D("16"), D("60"), D("0.80"))])],
        "gpt-6.2-sol": [(None, [(272_000, D("2"), D("10"), D("0.10")),
                                (None, D("4"), D("15"), D("0.20"))])],
        "gpt-6.1-terra": [(None, [(272_000, D("1"), D("5"), D("0.05")),
                                  (None, D("2"), D("7.50"), D("0.10"))])],
        "gpt-6-luna": [(None, [(272_000, D("0.10"), D("0.50"), D("0.01")),
                               (None, D("0.20"), D("0.75"), D("0.02"))])],
    },
    PROVIDER_CLAUDE: {
        "claude-fable-5-2": [(None, [(None, D("8"), D("40"), D("0.20"))])],
        "claude-opus-5-5": [(None, [(None, D("4"), D("20"), D("0.20"))])],
        "claude-sonnet-5-5": [(None, [(None, D("2"), D("10"), D("0.10"))])],
        "claude-haiku-5-5": [(None, [(100_000, D("0.10"), D("0.50"), D("0.01")),
                                     (None, D("0.50"), D("2.50"), D("0.05"))])],
    },
}


def today():
    """Heutiges Datum (eine eigene Funktion, damit Tests es ersetzen können)."""
    return date.today()


def find_model(provider, model):
    """Name des Modells in PRICES oder None. Groß- und Kleinschreibung, ein Vorspann „models/“ und ein angehängter Stand
    (gpt-6-astra-2026-09-01) ändern nichts. Eine andere Fassung (gpt-6-astra-pro) ist ein anderes Modell."""
    name = model.strip().lower().removeprefix("models/")
    for known in sorted(PRICES.get(provider, {}), key=len, reverse=True):
        if name == known or (name.startswith(known + "-") and name[len(known) + 1:][:1].isdigit()):
            return known
    return None


def _current(periods, on):
    """Der Preisstand aus periods, der am Tag on gilt: der letzte, der an diesem Tag schon begonnen hat."""
    return [p for p in periods if p[0] is None or p[0] <= on][-1]


def model_choices(provider, on=None):
    """Modelle des Anbieters für die Auswahl im Feld „Modell“ (Issue #11): die Modelle aus PRICES, das teuerste zuerst,
    also nach dem Ausgabepreis (erste Stufe, kurze Prompts) am Tag on (Voreinstellung: heute). Bei gleichem Preis gilt
    die Reihenfolge der Tabelle. Weil sich Preise ändern, kann sich die Reihenfolge an einem Stichtag ändern (bei
    Gemini 4 am 01.12.2026). Ein Anbieter ohne Eintrag ergibt eine leere Liste."""
    on = on or today()
    models = PRICES.get(provider, {})
    return sorted(models, key=lambda name: _current(models[name], on)[1][0][2], reverse=True)  # stabil bei Gleichstand


def default_model(provider, on=None):
    """Das vorausgewählte Modell des Anbieters: der erste Eintrag von model_choices(), also das teuerste."""
    return model_choices(provider, on)[0]


def price_text(value):
    """Preis im deutschen Format: mindestens zwei, höchstens vier Nachkommastellen (2,00 oder 0,0375)."""
    whole, _, fraction = f"{value:.4f}".partition(".")
    return f"{whole},{fraction.rstrip('0').ljust(2, '0')}"


def _tokens(count):
    return f"{count:,}".replace(",", ".")


def _tier_name(tiers, k):
    """Zusatz zum Namen der Stufe k: leer bei nur einer Stufe, sonst die Grenzen des Prompts."""
    if len(tiers) == 1:
        return ""
    lower, upper = (tiers[k - 1][0] if k else None), tiers[k][0]
    if lower and upper:
        return f", Prompt über {_tokens(lower)} bis {_tokens(upper)} Token"
    return f", Prompt bis {_tokens(upper)} Token" if upper else f", Prompt über {_tokens(lower)} Token"


def _rows(provider, tiers):
    """Zeilen (Abrechnungsart, Eingabe, Ausgabe, Cache) eines Preisstands: Batch, bei Gemini auch der Hintergrund-Modus
    (Long Decode, er kostet den Standardpreis)."""
    modes = [("Batch", BATCH_FACTOR)]
    if provider == PROVIDER_GEMINI:
        modes.append(("Hintergrund (Long Decode)", D(1)))
    return [(name + _tier_name(tiers, k), *(price * factor for price in tier[1:]))
            for name, factor in modes for k, tier in enumerate(tiers)]


def model_costs(provider, model, on=None):
    """Kosten des Modells je 1 Mio. Token in USD am Tag on (Voreinstellung: heute), bei einem Modell ohne Preis None:
    {"model": Name in PRICES, "rows": [(Abrechnungsart, Eingabe, Ausgabe, Cache), ...], "later": [(ab Datum, Zeilen)]}.
    "later" nennt die Preisstände, die erst nach on beginnen."""
    key = find_model(provider, model)
    if key is None:
        return None
    on = on or today()
    periods = PRICES[provider][key]
    now = _current(periods, on)
    later = [p for p in periods if p[0] is not None and p[0] > on]
    return {"model": key, "rows": _rows(provider, now[1]),
            "later": [(since, _rows(provider, tiers)) for since, tiers in later]}


def _table(rows):
    lines = ["| | Eingabe | Ausgabe | Cache |", "|---|--:|--:|--:|"]
    return lines + [f"| {name} | {price_text(i)} | {price_text(o)} | {price_text(c)} |" for name, i, o, c in rows]


def costs_markdown(provider, model, on=None):
    """Text der Infobox als Markdown: die Kosten des Modells, bei einem schon bekannten Preiswechsel mit einer zweiten
    Tabelle für die späteren Preise. Ohne Preis für das Modell steht dort ein Hinweis, ohne Modellnamen gibt es None.
    Die Zahlen stehen ohne Währungszeichen da (die Überschrift nennt USD): Ein $ würde Streamlit als Formel lesen."""
    name = model.strip()
    if not name:
        return None
    costs = model_costs(provider, model, on)
    if costs is None:
        shown = name.replace("`", "")
        known = ", ".join(f"`{k}`" for k in model_choices(provider, on))  # in der Reihenfolge der Combobox
        return (f"**Kosten in USD je 1 Mio. Token**\n\nFür `{shown}` ist kein Preis hinterlegt (bekannt: {known}). "
                "Den Preis nennt die Preisseite des Anbieters.")
    lines = [f"**Kosten in USD je 1 Mio. Token:** `{costs['model']}`", "", *_table(costs["rows"])]
    for since, rows in costs["later"]:
        lines += ["", f"**Ab {since:%d.%m.%Y}**", "", *_table(rows)]
    return "\n".join(lines)


def costs_caption():
    """Zeile unter der Infobox: was die Ausgabe einschließt und wie alt die Preise sind."""
    return (f"Ausgabe einschließlich Denk-Token. Stand der Preise: {PRICES_AS_OF:%d.%m.%Y}. Preise ändern sich, "
            "maßgeblich ist die Preisseite des Anbieters.")


def costs_help(provider):
    """Erklärung zur Infobox (Tooltip der Zeile darunter), je Anbieter ergänzt um das, was bei ihm anders ist."""
    text = ("Batch kostet die Hälfte des Standardpreises. Cache: Eingabe-Token, die aus dem Cache gelesen werden "
            "und weniger kosten als neue Eingabe-Token.")
    if provider == PROVIDER_GEMINI:
        text += (" Der Hintergrund-Modus (Long Decode) kostet den Standardpreis und berechnet die Eingabe bei jedem "
                 "Schritt von 64K Token erneut, meist als Cache.")
    if provider == PROVIDER_CLAUDE:
        text += (" Einen Cache-Treffer gibt es nur mit dem Kästchen „Dateien im Prompt-Cache halten“. Das Schreiben in "
                 "den Cache kostet extra und steht hier nicht.")
    return text
