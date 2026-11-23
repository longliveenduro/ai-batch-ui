"""Geschätzte Kosten eines Laufs (Issue #39): aus den Token der Ergebniszeilen und den Preisen des Moduls pricing. Ohne
Streamlit.

Keine der drei APIs nennt die Kosten einer Anfrage in der Antwort, sie liefert nur Token-Zahlen. Die Kosten-APIs von
Anthropic und OpenAI brauchen einen Admin-Key und liefern nur Tagessummen. Darum rechnet die App selbst: Token mal
Preis je 1 Mio. Token, mit den Preisen der Kosten-Infobox (auch den eigenen aus conf/prices.toml) und dem Preisstand des
Tages, an dem der Lauf gestartet wurde. Das ist eine Schätzung, keine Abrechnung. Die Rechnung geht sofort, eine spätere
Abfrage beim Anbieter entfällt. Die Anzeige steht in views.show_rows() (README, Abschnitt 4).
"""
from decimal import Decimal as D

from .config import CLAUDE_CACHE_TTL, PROVIDER_CLAUDE, PROVIDER_GEMINI, PROVIDER_OPENAI
from .pricing import BATCH_FACTOR, CLAUDE_CACHE_WRITE, current_prices, find_model, price_text, price_tier, run_day

MILLION = 1_000_000  # die Preise gelten je 1 Mio. Token

# Betriebsart eines Eintrags (providers.entry_mode) -> (wie der Satz die Abrechnung nennt, Faktor auf den
# Standardpreis). Der ältere synchrone Modus lief zum Standardpreis, ohne Rabatt.
KINDS = {
    "batch": ("als Batch", BATCH_FACTOR),
    "background": ("im Hintergrund-Modus (Standardpreis)", D(1)),
    "sync": ("zum Standardpreis (älterer synchroner Lauf)", D(1)),
}
# Nur Gemini kennt beide Betriebsarten. Der Vergleich rechnet dieselben Token in der anderen: Betriebsart ->
# (andere Betriebsart, Satzanfang des Vergleichs).
COMPARISON = {"batch": ("background", "Im Hintergrund-Modus"), "background": ("batch", "Als Batch")}


def _count(source, name):
    """Token-Zahl aus einem Feld (eine ganze Zahl über 0). Fehlt es oder ist es etwas anderes, zählt es 0: Zeilen
    älterer Läufe haben nicht jedes Feld."""
    value = source.get(name) if isinstance(source, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _cache_writes(provider, row):
    """Das Schreiben in den Cache einer Zeile als (Token, Token mal Preisfaktor). Nur Claude weist es in den
    Nutzungsdaten aus und berechnet es gesondert (CLAUDE_CACHE_WRITE mal Eingabepreis). cache_creation trennt die
    Lebensdauer (fünf Minuten, eine Stunde), was darin nicht steht, zählt mit der Lebensdauer CLAUDE_CACHE_TTL. Bei
    OpenAI (ab GPT-5.6 mit gesondertem Preis) und Gemini ist es nicht eingerechnet."""
    if provider != PROVIDER_CLAUDE:
        return 0, D(0)
    usage = row.get("usage") if isinstance(row.get("usage"), dict) else {}
    detail = usage.get("cache_creation")
    five = _count(detail, "ephemeral_5m_input_tokens")
    hour = _count(detail, "ephemeral_1h_input_tokens")
    rest = max(_count(usage, "cache_creation_input_tokens") - five - hour, 0)
    weight = (five * CLAUDE_CACHE_WRITE["5m"] + hour * CLAUDE_CACHE_WRITE["1h"]
              + rest * CLAUDE_CACHE_WRITE[CLAUDE_CACHE_TTL])
    return five + hour + rest, weight


def standard_cost(provider, row, prices):
    """Kosten einer Ergebniszeile zum Standardpreis in USD (Decimal). prices ist (Eingabe, Ausgabe, Cache) je 1 Mio.
    Token der Stufe, die zur Länge des Prompts passt (pricing.price_tier()). „Eingabe“ der Zeile schließt die Token aus
    dem Cache ein (und bei Claude die für den Cache geschriebenen): Neu berechnet wird nur der Rest, die Cache-Token
    kosten den Cache-Preis. Die Ausgabe ist Denken plus Antwort."""
    price_in, price_out, price_cache = prices
    cached = _count(row, "cached")
    written, weight = _cache_writes(provider, row)
    fresh = max(_count(row, "in") - cached - written, 0)
    output = _count(row, "think") + _count(row, "out")
    return (fresh * price_in + weight * price_in + cached * price_cache + output * price_out) / MILLION


def run_costs(provider, mode, model, created, rows, api_model=None):
    """Geschätzte Kosten eines Laufs in USD oder None, wenn die Preistabelle das Modell nicht kennt. mode ist die
    Betriebsart des Eintrags (providers.entry_mode()), created sein Startzeitpunkt (der Preisstand dieses Tages gilt,
    pricing.run_day()). Das Modell ist das des Eintrags, sonst das, das die API gemeldet hat (api_model und die Zeilen):
    So findet ein Alias wie claude-sonnet-latest den Preis über den Namen in der Antwort. Das Ergebnis:
    {"model": Name in der Tabelle, "mode": mode, "day": Tag des Preisstands, "phrase": wie der Satz die Abrechnung
    nennt, "custom": True bei Preisen aus conf/prices.toml, "rows": {Schlüssel: Kosten}, "total": Summe,
    "other": (Satzanfang, Kosten) bei Gemini mit denselben Token in der anderen Betriebsart, sonst None}. Zeilen ohne
    Token (Fehler) fehlen in "rows"."""
    book = current_prices()
    names = dict.fromkeys(n for n in (model, api_model, *(r.get("model") for r in rows)) if isinstance(n, str))
    key = next((k for k in (find_model(provider, n, book.table) for n in names) if k), None)
    if key is None:
        return None
    on = run_day(created)
    standard = {}
    for r in rows:
        if any(_count(r, field) for field in ("in", "think", "out")):
            prices = price_tier(book.table, provider, key, on, _count(r, "in"))
            standard[r["key"]] = standard_cost(provider, r, prices)
    phrase, factor = KINDS.get(mode, KINDS["batch"])
    total = sum(standard.values(), D(0))
    other = None
    if provider == PROVIDER_GEMINI and mode in COMPARISON:
        other_mode, start = COMPARISON[mode]
        other = (start, total * KINDS[other_mode][1])
    return {"model": key, "mode": mode, "day": on, "phrase": phrase, "custom": key in book.own.get(provider, ()),
            "rows": {k: v * factor for k, v in standard.items()}, "total": total * factor, "other": other}


# ---------- Texte ----------
def cost_text(value):
    """Betrag im deutschen Format wie die Preise (zwei bis vier Nachkommastellen). Ein Rest unter 0,0001 würde als 0,00
    erscheinen und nach „kostenlos“ aussehen, darum steht dort „< 0,0001“."""
    return "< 0,0001" if 0 < value < D("0.0001") else price_text(value)


def row_cost_text(costs, key):
    """Kosten einer Zeile für die Zeile unter der Antwort, oder None (kein Preis, oder die Zeile hat keine Token)."""
    value = costs["rows"].get(key) if costs else None
    return None if value is None else f"Kosten ca. {cost_text(value)} USD"


def run_cost_text(costs, done, total):
    """Satz zu den Kosten eines Laufs, bei Gemini mit dem Vergleich Batch gegen Hintergrund-Modus. Sind erst done von
    total Prompts fertig (ein Hintergrund-Lauf kommt nach und nach), steht es dabei: Die Summe gilt nur für diese."""
    head = "Geschätzte Kosten" + (f" der bisher fertigen Prompts ({done} von {total})" if done < total else "")
    text = f"{head}: {cost_text(costs['total'])} USD {costs['phrase']}."
    if costs["other"]:
        start, value = costs["other"]
        text += f" {start} wären es bei gleichen Token {cost_text(value)} USD."
    return text


def no_price_text(model):
    """Hinweis, wenn die Preistabelle das Modell eines Laufs nicht kennt: Die Kosten lassen sich nicht schätzen."""
    shown = (model or "unbekannt").replace("`", "")
    return (f"Kosten: Für `{shown}` ist kein Preis hinterlegt, sie lassen sich nicht schätzen. Eigene Preise stehen in "
            "conf/prices.toml (README, Abschnitt 6.6).")


def costs_note(provider, mode, custom=False):
    """Erklärung zu den Kosten (Tooltip der Zeile): wie gerechnet wird und was je Anbieter nicht oder anders drin
    ist."""
    text = ("Berechnet aus den Token der Antworten und den Preisen der Kosten-Infobox in der Seitenleiste, mit dem "
            "Preisstand des Tages, an dem der Lauf gestartet wurde. Eine Schätzung, keine Abrechnung: Maßgeblich "
            "ist die Rechnung des Anbieters. Eingabe-Token aus dem Cache zählen zum Cache-Preis, Denk-Token zur "
            "Ausgabe.")
    if provider == PROVIDER_GEMINI and mode in COMPARISON:
        text += (" Der Vergleich nimmt dieselben Token an. Ein Batch kennt kein Long Decode, im Hintergrund-Modus wird "
                 "die Eingabe bei jedem Schritt erneut berechnet, meist als Cache.")
    if provider == PROVIDER_CLAUDE:
        hour, five = (str(CLAUDE_CACHE_WRITE[ttl]).replace(".", ",") for ttl in ("1h", "5m"))
        text += (f" Das Schreiben in den Cache ist eingerechnet: das {hour}-fache des Eingabepreises bei einer Stunde "
                 f"Lebensdauer, das {five}-fache bei fünf Minuten.")
    if provider == PROVIDER_OPENAI:
        text += " Das Schreiben in den Cache, das OpenAI ab GPT-5.6 gesondert berechnet, ist nicht eingerechnet."
    if custom:
        text += " Für dieses Modell gelten die Preise aus conf/prices.toml."
    return text
