"""Claude (nur Batch, Message Batches API): Dateien hochladen, Batch starten, Ergebnisse lesen."""
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import PurePath

from .config import (CLAUDE_CACHE_TTL, CLAUDE_FILE_MIN_LEFT, CLAUDE_FILE_TTL, CLAUDE_FILES_DB, DATA_DIR,
                     PROVIDER_CLAUDE)
from .files import PDF_MIME, check_files, file_info
from .rows import as_dict, pick, sort_rows

# Zeichen, die die Files API in Dateinamen ablehnt (Windows-typische Zeichen und Steuerzeichen)
FORBIDDEN_NAME_CHARS = re.compile(r'[<>:"|?*\\/\x00-\x1f]+')
FINISH_REASONS = {"end_turn": "STOP", "max_tokens": "MAX_TOKENS"}  # wie bei Gemini, damit die Warnung in show_rows() greift
NOT_PROCESSED = {  # Ergebnisarten ohne Antwort und ohne Kosten
    "canceled": "Abgebrochen, bevor die Anfrage bearbeitet wurde (wird nicht berechnet).",
    "expired": "Abgelaufen: Der Batch erreichte das 24-Stunden-Limit, bevor die Anfrage bearbeitet wurde "
               "(wird nicht berechnet).",
}


def claude_client(api_key):
    """Claude-Client (Paket anthropic). Das Paket wird erst hier geladen: Wer nur Gemini nutzt, braucht es nicht."""
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("Das Paket anthropic fehlt. Installieren: pip install -r requirements.txt") from e
    return Anthropic(api_key=api_key)


def claude_filename(name):
    """Dateiname für die Files API: Sie erlaubt 1 bis 255 Zeichen und lehnt Zeichen wie < > : " | ? * \\ / und
    Steuerzeichen ab. Verbotene Zeichen werden zu Bindestrichen, ein zu langer Name wird vor der Endung gekürzt."""
    clean = FORBIDDEN_NAME_CHARS.sub("-", name).strip() or "datei"
    if len(clean) > 255:
        ext = PurePath(clean).suffix[:20]
        clean = clean[:255 - len(ext)] + ext
    return clean


def claude_mime(name):
    """MIME-Typ, mit dem die Datei zur Files API geht: PDF und Bilder wie in file_info(), alle Textformate (auch CSV)
    als text/plain, denn nur PDF und text/plain liest Claude als Dokument. ValueError bei allem, was Claude nicht
    annimmt (unbekannter Typ, Audio, Video, Word, PowerPoint, Excel), siehe check_files()."""
    problems = check_files(PROVIDER_CLAUDE, [name])
    if problems:
        raise ValueError(problems[0])
    _, mime = file_info(name)
    return mime if mime == PDF_MIME or mime.startswith("image/") else "text/plain"


def file_alive(f, now=None):
    """Lebt die Datei bei Anthropic noch mindestens CLAUDE_FILE_MIN_LEFT Sekunden? Ohne Ablaufzeit gilt sie als lebendig.
    Die Metadaten einer abgelaufenen Datei liefert die API noch eine Weile, darum genügt es nicht, dass die Abfrage
    gelingt."""
    expires = getattr(f, "expires_at", None)
    if expires is None:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires - (now or datetime.now(timezone.utc)) >= timedelta(seconds=CLAUDE_FILE_MIN_LEFT)


def upload_file_claude(client, name, data):
    """Datei in die Files API von Anthropic laden (PDF, Text und Bilder, sonst ValueError, siehe claude_mime()). Gleicher
    Inhalt: gleiche Datei, solange sie noch lange genug lebt (file_alive)."""
    mime = claude_mime(name)
    key = hashlib.sha256(data).hexdigest()
    db = json.loads(CLAUDE_FILES_DB.read_text("utf-8")) if CLAUDE_FILES_DB.exists() else {}
    if key in db:
        try:
            f = client.files.retrieve_metadata(db[key])
            if file_alive(f):
                return f
        except Exception:  # gelöscht oder aus einem anderen Workspace: neu hochladen
            pass
    f = client.files.upload(file=(claude_filename(name), data, mime), expires_in_seconds=CLAUDE_FILE_TTL)
    db[key] = f.id
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CLAUDE_FILES_DB.write_text(json.dumps(db), "utf-8")
    return f


def claude_file_part(f):
    """Block einer Messages-Anfrage für eine hochgeladene Datei: Bilder als image-Block, alles andere als document-Block.
    Die Datei steht als file_id darin."""
    kind = "image" if (getattr(f, "mime_type", None) or "").startswith("image/") else "document"
    return {"type": kind, "source": {"type": "file", "file_id": f.id}}


def claude_request(model, files, prompt, system, effort, max_out, cache=False):
    """Rumpf (params) einer Messages-Anfrage für einen Prompt. Die Dateien stehen ganz vorn, immer in derselben
    Reihenfolge: Sie bilden mit der Systemanweisung den Prefix, den alle Prompts teilen. Mit cache trägt die letzte
    Datei die Marke für den Prompt-Cache (ohne Dateien gibt es nichts zu cachen). Ohne Denktiefe („Standard“)
    entscheidet das Modell."""
    parts = [claude_file_part(f) for f in files]
    if cache and parts:
        parts[-1]["cache_control"] = {"type": "ephemeral", "ttl": CLAUDE_CACHE_TTL}
    parts.append({"type": "text", "text": prompt})
    params = {"model": model, "max_tokens": int(max_out), "messages": [{"role": "user", "content": parts}]}
    if system:
        params["system"] = system
    if effort != "Standard":
        params["output_config"] = {"effort": effort}
    return params


def start_claude_batch(client, model, files, prompts, system, effort, max_out, cache=False):
    """Anfragen bauen (je Prompt eine), zur Kontrolle als JSONL ablegen und den Batch anlegen. Gibt (Batch-ID, Prompts je
    Schlüssel) zurück. Die Message Batches API kennt keinen Namen für den Batch, der Name bleibt lokal."""
    requests, keyed = [], {}
    for i, p in enumerate(prompts, 1):
        key = f"prompt-{i}"
        keyed[key] = p
        requests.append({"custom_id": key, "params": claude_request(model, files, p, system, effort, max_out, cache)})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"requests_claude_{int(time.time())}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in requests), "utf-8")
    batch = client.messages.batches.create(requests=requests)
    return batch.id, keyed


def claude_error_text(err):
    """Fehlerobjekt der API ({"type": "error", "error": {"type": …, "message": …}, "request_id": …}) als Text."""
    if not isinstance(err, dict):
        return str(err)
    inner = err.get("error") if isinstance(err.get("error"), dict) else err
    text = ": ".join(str(inner[k]) for k in ("type", "message") if inner.get(k))
    if not text:
        return json.dumps(err, ensure_ascii=False)
    return f"{text} (request_id: {err['request_id']})" if err.get("request_id") else text


def claude_refusal_text(message):
    """Text zu einer Antwort, die das Modell abgelehnt hat (stop_reason refusal): Kategorie und Erklärung, soweit da."""
    details = message.get("stop_details") or {}
    category = f" (Kategorie: {details['category']})" if details.get("category") else ""
    return f"Das Modell hat abgelehnt{category}" + (f": {details['explanation']}" if details.get("explanation") else ".")


def parse_claude_line(o, prompts):
    """Ein Ergebnis des Claude-Batches ({"custom_id": …, "result": {"type": …}}) in eine Tabellenzeile überführen,
    in der Form von parse_line(). Eingabe zählt alle Eingabe-Token (auch die aus dem Cache gelesenen und die für den
    Cache geschriebenen), „aus dem Cache“ nur die gelesenen. Claude rechnet Denk-Token in output_tokens ein, die
    Zeile trennt sie, wenn die API sie ausweist: „Ausgabe“ ohne Denken."""
    key = o.get("custom_id", "?")
    result = o.get("result") or {}
    kind = result.get("type")
    message = result.get("message") or {}
    text = "".join(b.get("text", "") for b in message.get("content") or [] if b.get("type") == "text")
    stop = message.get("stop_reason")
    finish = FINISH_REASONS.get(stop, stop.upper()) if kind == "succeeded" and stop else "unbekannt"
    if kind == "errored":
        err = claude_error_text(result.get("error"))
    elif kind in NOT_PROCESSED:
        err = NOT_PROCESSED[kind]
    elif kind != "succeeded":
        err = f"Unbekanntes Ergebnis ({kind or 'ohne Art'})"
    elif stop == "refusal" and not text:
        err = claude_refusal_text(message)
    elif not text:
        err = f"Keine Antwort (Abschlussgrund: {finish})"
    else:
        err = None
    usage = message.get("usage") or {}
    cached = pick(usage, "cache_read_input_tokens")
    think = pick(usage.get("output_tokens_details") or {}, "thinking_tokens")
    return {
        "key": key,
        "prompt": prompts.get(key, ""),
        "text": text,
        "model": message.get("model") or "unbekannt",
        "finish": finish,
        "usage": usage,
        "error": err,
        "in": pick(usage, "input_tokens") + cached + pick(usage, "cache_creation_input_tokens"),
        "cached": cached,
        "think": think,
        "out": max(pick(usage, "output_tokens") - think, 0),
    }


def fetch_claude_batch(client, j):
    """Stand eines Claude-Batches als (Status, Zeilen, Fehlertext, Modell). Erst wenn er endet (processing_status ended),
    werden die Ergebnisse geladen: Sie enthalten je Anfrage die Antwort, den Fehler oder den Hinweis auf Abbruch oder
    Ablauf. Die Message Batches API kennt keinen Fehler für den ganzen Batch, darum bleibt der Fehlertext leer. Das
    Modell steht erst in den Antworten."""
    b = client.messages.batches.retrieve(j["name"])
    rows = None
    if b.processing_status == "ended":
        rows = sort_rows([parse_claude_line(as_dict(x), j["prompts"])
                          for x in client.messages.batches.results(j["name"])]) or None
    model = next((r["model"] for r in rows or [] if r["model"] != "unbekannt"), None)
    return b.processing_status, rows, None, model
