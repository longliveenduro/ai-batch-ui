"""Preise der Modelle (Issue #12): Preistabelle je Anbieter und Modell und die Kosten des gewählten Modells als Text für
die Infobox in der Seitenleiste. Dieselbe Tabelle liefert die Auswahl im Feld „Modell“ (Issue #11), dazu nennt
BEST_MODELS das vorausgewählte Modell (Issue #45). Ohne Streamlit.

Die Anbieter nennen ihre Preise nicht über die API, darum stehen sie fest in PRICES (Stand: PRICES_AS_OF, Quellen in der
README, Abschnitt 13). Ändert sich ein Preis oder kommt ein Modell dazu, wird nur diese Tabelle angepasst (README,
Abschnitt 9.2). Aus demselben Grund kommt auch die Liste der Modelle aus der Tabelle und nicht aus der Modellliste der
API: Die Modelllisten der Anbieter nennen keine Preise, eine Sortierung nach Kosten wäre damit nicht möglich. Auch
welches Modell das beste ist, sagt keine der Listen (keine nennt eine Rangfolge): Das steht fest in BEST_MODELS.

Eigene Preise (Issue #39): Die optionale Datei conf/prices.toml (PRICES_FILE) ändert Preise oder ergänzt Modelle, ohne
dass der Quelltext angefasst wird (README, Abschnitt 6.6). Alle Funktionen dieses Moduls rechnen mit der geltenden
Tabelle, die current_prices() liefert: PRICES, überlagert von der Datei. PRICES selbst bleibt unverändert.
"""
import tomllib
from collections import namedtuple
from datetime import date, datetime
from decimal import Decimal as D
from math import isfinite

from .config import PRICES_FILE, PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI, PROVIDERS

PRICES_AS_OF = date(2026, 11, 21)  # Tag, an dem die Tabelle mit den Preisseiten der Anbieter abgeglichen wurde
BATCH_FACTOR = D("0.5")  # Batch kostet bei Gemini, OpenAI und Claude die Hälfte des Standardpreises
MAX_MODELS = 5  # so viele Modelle zeigt die Auswahl je Anbieter höchstens: die aktuellen (ein Test prüft die Tabelle)
# Claude: Das Schreiben in den Cache kostet ein Vielfaches des Eingabepreises, je nach Lebensdauer der Cache-Marke (die
# App nutzt CLAUDE_CACHE_TTL, ein Test prüft, dass sie hier steht). Der Batch-Rabatt gilt zusätzlich.
CLAUDE_CACHE_WRITE = {"5m": D("1.25"), "1h": D("2")}

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
# Das qualitativ beste Modell je Anbieter (Issue #45): Es ist im Feld „Modell“ vorausgewählt (default_model()). Das ist
# nicht das teuerste: Die Liste ist nach Preis sortiert (Issue #11), und der Preis sagt nichts über die Qualität (bei
# OpenAI kostet gpt-6-astra mehr als das bessere gpt-6.2-astra, bei Gemini 4 ist bis 30.11.2026 Neon teurer als Carbon).
# Keine API nennt das beste Modell, es folgt der Selbstauskunft des Anbieters (README, Abschnitt 13). Jeder Anbieter in
# PRICES braucht einen Eintrag, und das Modell muss in PRICES stehen (ein Test prüft beides). Kommt ein stärkeres
# Modell, wird der Eintrag ausgetauscht (README, Abschnitt 9.2). Modelle aus conf/prices.toml ändern ihn nicht.
BEST_MODELS = {
    PROVIDER_GEMINI: "gemini-4-carbon",  # Googles Modell für die schwersten Projekte, Neon liegt darunter
    PROVIDER_OPENAI: "gpt-6.2-astra",  # OpenAIs neues Frontier-Modell (laut OpenAI besser und billiger als gpt-6-astra)
    PROVIDER_CLAUDE: "claude-fable-5-2",  # Anthropics fähigstes allgemein verfügbares Modell
}


def today():
    """Heutiges Datum (eine eigene Funktion, damit Tests es ersetzen können)."""
    return date.today()


def run_day(created):
    """Tag, dessen Preise für einen Lauf gelten (Issue #39): der Tag, an dem er gestartet wurde (Feld created des
    Eintrags, ISO-Format). Fehlt die Angabe oder ist sie unlesbar, gilt heute."""
    try:
        return datetime.fromisoformat(created).date()
    except (TypeError, ValueError):
        return today()


# ---------- Eigene Preise: conf/prices.toml (Issue #39) ----------
_REQUIRED = ("provider", "model", "input", "output", "cache")  # Schlüssel eines Eintrags [[price]], die nötig sind
_OPTIONAL = ("from", "up_to")  # ab welchem Tag der Preis gilt, bis zu welcher Prompt-Länge (Stufe)


def _provider(value):
    name = value.strip().lower() if isinstance(value, str) else ""
    for provider in PROVIDERS:
        if provider.lower() == name:
            return provider
    raise ValueError("provider muss " + ", ".join(PROVIDERS[:-1]) + " oder " + PROVIDERS[-1] + " sein")


def _model_name(value):
    """Name wie die Schlüssel von PRICES: klein geschrieben, ohne Vorspann „models/“."""
    name = value.strip().lower().removeprefix("models/") if isinstance(value, str) else ""
    if not name or any(c.isspace() for c in name):
        raise ValueError("model muss ein Modellname ohne Leerzeichen sein")
    return name


def _price(value, key):
    """Preis aus der Datei als Decimal: eine endliche Zahl ab 0 (ein Wahrheitswert oder ein Text ist keine)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} muss eine Zahl ab 0 sein")
    if (isinstance(value, float) and not isfinite(value)) or value < 0:
        raise ValueError(f"{key} muss eine Zahl ab 0 sein")
    return D(str(value))


def _limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("up_to muss eine ganze Zahl über 0 sein (Token)")
    return value


def _day(value):
    """Datum aus der Datei: ein TOML-Datum (2026-12-01) oder ein Text im selben Format."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError("from muss ein Datum sein (zum Beispiel 2026-12-01)")


def _entry(raw):
    """Ein Eintrag [[price]] als (Anbieter, Modell, ab, bis Prompt-Länge, (Eingabe, Ausgabe, Cache)). Jeder Fehler ist
    ein ValueError mit dem Grund; unbekannte Schlüssel gelten auch als Fehler, sonst bliebe ein Tippfehler in from oder
    up_to stumm und der Preis gälte falsch."""
    if not isinstance(raw, dict):
        raise ValueError("kein Eintrag [[price]]")
    unknown = [k for k in raw if k not in (*_REQUIRED, *_OPTIONAL)]
    if unknown:
        raise ValueError("unbekannter Schlüssel: " + ", ".join(unknown))
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"{', '.join(missing)} {'fehlt' if len(missing) == 1 else 'fehlen'}")
    prices = (_price(raw["input"], "input"), _price(raw["output"], "output"), _price(raw["cache"], "cache"))
    since = _day(raw["from"]) if "from" in raw else None
    limit = _limit(raw["up_to"]) if "up_to" in raw else None
    return _provider(raw["provider"]), _model_name(raw["model"]), since, limit, prices


def _who(raw):
    """(Anbieter, Modell) eines Eintrags, auch wenn etwas anderes an ihm falsch ist, sonst None."""
    try:
        return _provider(raw["provider"]), _model_name(raw["model"])
    except (KeyError, TypeError, ValueError):
        return None


def _periods(found):
    """Preisstände eines Modells im Format von PRICES aus {ab: {Obergrenze: (Eingabe, Ausgabe, Cache)}}. Der erste
    Preisstand gilt von jeher, in jedem hat die letzte Stufe keine Obergrenze. Sonst ein ValueError."""
    if None not in found:
        raise ValueError("der erste Preisstand muss ohne from stehen (er gilt von jeher)")
    periods = []
    for since in sorted(found, key=lambda s: (s is not None, s or date.min)):
        tiers = found[since]
        if None not in tiers:
            raise ValueError("die letzte Stufe braucht einen Eintrag ohne up_to"
                             + (f" (Preisstand ab {since:%d.%m.%Y})" if since else ""))
        periods.append((since, [(limit, *tiers[limit]) for limit in sorted(tiers, key=lambda x: (x is None, x or 0))]))
    return periods


def read_price_file(path=None):
    """Die Preisdatei conf/prices.toml (PRICES_FILE) lesen: (Preise, Probleme). Preise ist {Anbieter: {Modell:
    Preisstände}} im Format von PRICES, Probleme eine Liste von Texten für die Anzeige. Die Datei ist optional: Fehlt
    sie, ist beides leer. Jeder Eintrag [[price]] ist ein Preis (Anbieter, Modell, ab Datum, bis Prompt-Länge), die
    Einträge eines Modells ergeben seine Preisstände und Stufen. Ein Fehler macht nur das betroffene Modell ungültig
    (es gelten dann die eingebauten Preise), ein Fehler im TOML selbst die ganze Datei. Nichts davon bricht die App
    ab."""
    path = path or PRICES_FILE
    label = f"{path.parent.name}/{path.name}"
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return {}, []
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:  # auch eine fehlende Berechtigung
        return {}, [f"{label} lässt sich nicht lesen ({e}). Es gelten die eingebauten Preise."]
    problems = [f"{label}: Unbekannter Abschnitt „{key}“, erlaubt sind nur Einträge [[price]]."
                for key in data if key != "price"]
    entries = data.get("price", [])
    if not isinstance(entries, list):
        return {}, problems + [f"{label}: „price“ muss mit doppelten eckigen Klammern stehen: [[price]]."]
    found, bad = {}, {}  # (Anbieter, Modell) -> {ab: {Obergrenze: Preise}}, bzw. -> der erste Fehler
    for n, raw in enumerate(entries, 1):
        try:
            provider, model, since, limit, prices = _entry(raw)
            tiers = found.setdefault((provider, model), {}).setdefault(since, {})
            if limit in tiers:
                raise ValueError("zwei Einträge mit demselben from und up_to")
            tiers[limit] = prices
        except ValueError as e:
            who = _who(raw)
            if who:
                bad.setdefault(who, f"Eintrag {n}: {e}")
            else:
                problems.append(f"{label}, Eintrag {n}: {e}. Der Eintrag gilt nicht.")
    table = {}
    for (provider, model), by_day in found.items():
        if (provider, model) in bad:
            continue
        try:
            table.setdefault(provider, {})[model] = _periods(by_day)
        except ValueError as e:
            bad[(provider, model)] = str(e)
    problems += [f"{label}, {provider} „{model}“: {reason}. Die Preise dieses Modells aus der Datei gelten nicht."
                 for (provider, model), reason in bad.items()]
    return table, problems


# Die geltende Preistabelle: table {Anbieter: {Modell: Preisstände}} wie PRICES, own {Anbieter: Modelle aus der Datei},
# problems die Texte zu Fehlern in der Datei.
PriceBook = namedtuple("PriceBook", "table own problems")


def current_prices():
    """Die geltende Preistabelle (Issue #39): PRICES, überlagert von der Preisdatei. Ein Modell aus der Datei ersetzt
    den ganzen Eintrag des Modells in PRICES (alle Preisstände und Stufen), ein neuer Name kommt hinter die eingebauten
    Modelle (bei gleichem Preis bestimmt diese Reihenfolge die der Auswahl). Die Datei wird bei jedem Aufruf gelesen:
    Ein geänderter Preis gilt beim nächsten Rerun, die App braucht keinen Neustart. Wer in einer Schleife rechnet, ruft
    sie einmal auf und reicht die Tabelle weiter."""
    own, problems = read_price_file()
    providers = [*PRICES, *(p for p in own if p not in PRICES)]
    table = {p: {**PRICES.get(p, {}), **own.get(p, {})} for p in providers}
    return PriceBook(table, {p: set(models) for p, models in own.items()}, problems)


def find_model(provider, model, table=None):
    """Name des Modells in der Preistabelle oder None. Groß- und Kleinschreibung, ein Vorspann „models/“ und ein
    angehängter Stand (gpt-6-astra-2026-09-01) ändern nichts. Eine andere Fassung (gpt-6-astra-pro) ist ein anderes
    Modell. Ohne table gilt die geltende Tabelle (current_prices())."""
    table = current_prices().table if table is None else table
    name = model.strip().lower().removeprefix("models/")
    for known in sorted(table.get(provider, {}), key=len, reverse=True):
        if name == known or (name.startswith(known + "-") and name[len(known) + 1:][:1].isdigit()):
            return known
    return None


def _current(periods, on):
    """Der Preisstand aus periods, der am Tag on gilt: der letzte, der an diesem Tag schon begonnen hat."""
    return [p for p in periods if p[0] is None or p[0] <= on][-1]


def model_choices(provider, on=None):
    """Modelle des Anbieters für die Auswahl im Feld „Modell“ (Issue #11): die Modelle der Preistabelle, das teuerste
    zuerst, also nach dem Ausgabepreis (erste Stufe, kurze Prompts) am Tag on (Voreinstellung: heute). Bei gleichem
    Preis gilt die Reihenfolge der Tabelle. Weil sich Preise ändern, kann sich die Reihenfolge an einem Stichtag ändern
    (bei Gemini 4 am 01.12.2026). Modelle aus conf/prices.toml gehören dazu (MAX_MODELS gilt nur für PRICES). Ein
    Anbieter ohne Eintrag ergibt eine leere Liste. Vorausgewählt ist nicht unbedingt das erste: default_model()."""
    on = on or today()
    models = current_prices().table.get(provider, {})
    return sorted(models, key=lambda name: _current(models[name], on)[1][0][2], reverse=True)  # stabil bei Gleichstand


def default_model(provider, on=None):
    """Das vorausgewählte Modell des Anbieters (Issue #45): sein bestes Modell aus BEST_MODELS, nicht das teuerste. Es
    steht nicht unbedingt vorn in model_choices(), denn dort gilt der Preis (bei OpenAI das ältere gpt-6-astra vor dem
    besseren gpt-6.2-astra, bei Gemini 4 bis 30.11.2026 Neon vor Carbon). Die Voreinstellung hängt deshalb nicht vom Tag
    ab. Hat der Anbieter keinen Eintrag in BEST_MODELS, oder steht das Modell nicht in der Tabelle, gilt der erste
    Eintrag der Liste. on wie bei model_choices(): Es bestimmt nur diesen Rückfall."""
    choices = model_choices(provider, on)
    best = BEST_MODELS.get(provider)
    return best if best in choices else choices[0]


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


def price_tier(table, provider, key, on, prompt_tokens):
    """Preise (Eingabe, Ausgabe, Cache) in USD je 1 Mio. Token, die für das Modell key am Tag on bei einem Prompt dieser
    Länge gelten (Issue #39): die erste Stufe, deren Obergrenze der Prompt nicht überschreitet, bei einem längeren die
    letzte. table ist die Tabelle von current_prices(), key ein Name aus find_model()."""
    for limit, *prices in _current(table[provider][key], on)[1]:
        if limit is None or prompt_tokens <= limit:
            return tuple(prices)


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
    {"model": Name in der Tabelle, "rows": [(Abrechnungsart, Eingabe, Ausgabe, Cache), ...], "later": [(ab Datum,
    Zeilen)], "custom": True bei Preisen aus conf/prices.toml}. "later" nennt die Preisstände, die erst nach on
    beginnen."""
    book = current_prices()
    key = find_model(provider, model, book.table)
    if key is None:
        return None
    on = on or today()
    periods = book.table[provider][key]
    now = _current(periods, on)
    later = [p for p in periods if p[0] is not None and p[0] > on]
    return {"model": key, "rows": _rows(provider, now[1]),
            "later": [(since, _rows(provider, tiers)) for since, tiers in later],
            "custom": key in book.own.get(provider, ())}


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


def costs_caption(custom=False):
    """Zeile unter der Infobox: was die Ausgabe einschließt und wie alt die Preise sind. Bei eigenen Preisen aus
    conf/prices.toml (custom) steht dort, woher sie kommen, statt des Stands der eingebauten Tabelle."""
    if custom:
        return ("Ausgabe einschließlich Denk-Token. Eigene Preise aus conf/prices.toml: Für dieses Modell gilt, was "
                "dort steht. Preise ändern sich, maßgeblich ist die Preisseite des Anbieters.")
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
    return text + " Eigene Preise stehen in conf/prices.toml (README, Abschnitt 6.6)."
