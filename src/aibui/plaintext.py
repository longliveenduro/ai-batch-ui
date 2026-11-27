"""Antworttext als Klartext zum Kopieren (Issue #35): der Text, den man am Bildschirm liest, ohne Markdown-Zeichen.

Die Antworten der Modelle sind Markdown. Die Oberfläche zeigt sie gerendert, der Kopierknopf soll aber keinen
Markdown-Quelltext liefern (kein `**`, kein `#`, keine `[Text](Adresse)`), sondern Klartext, wie man ihn beim Markieren
und Kopieren von Hand bekäme, nur ohne dessen Verluste: Dabei fallen Aufzählungszeichen und Nummern weg, Formeln werden
zu Zeilen voller Einzelzeichen, und die Adresse eines Links geht verloren.

Geparst wird mit markdown-it-py nach der CommonMark-Spezifikation, so wie auch Streamlit Markdown liest. Das Modul
kennt Streamlit nicht und ist ohne Oberfläche testbar.
"""
import re
from functools import lru_cache

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

BULLET = "•"  # Aufzählungszeichen, wie es die Oberfläche zeigt (kein Markdown-Zeichen wie "-" oder "*")
MATH_OPEN, MATH_CLOSE = "\ue000", "\ue001"  # Zeichen aus dem privaten Bereich: Platzhalter für geschützte Formeln

# HTML ist aus: Streamlit zeigt HTML-Marken in Antworten als Text (unsafe_allow_html ist aus), also bleiben sie stehen.
PARSER = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])

# Formeln, wie sie Streamlit mit KaTeX setzt: $$...$$ (auch über mehrere Zeilen) und $...$ in einer Zeile. Wie in Pandoc
# steht hinter dem öffnenden $ kein Leerraum, vor dem schließenden kein Leerraum und danach keine Ziffer. So bleibt
# "kostet 5 $ und 6 $" oder "$20.000 und $30.000" Text. Ein Backslash davor (\$) schützt das Zeichen.
MATH = re.compile(r"\$\$.+?\$\$|(?<![\\$])\$(?!\s)(?:[^$\n\\]|\\.)+?(?<!\s)\$(?![\d$])", re.S)
MATH_SLOT = re.compile(f"{MATH_OPEN}(\\d+){MATH_CLOSE}")


@lru_cache(maxsize=512)  # Die Ergebnisliste zeichnet sich bei jedem Rerun neu: gleiche Antworten nicht neu umwandeln.
def plain_text(markdown):
    """Der Text einer Antwort ohne Markdown-Zeichen. Absätze, Überschriften, Listen, Tabellen und Codeblöcke bleiben
    als Zeilen und Leerzeilen erhalten. Ein Zeilenumbruch mitten im Absatz wird wie am Bildschirm zum Leerzeichen.
    Aufzählungen beginnen mit dem Zeichen BULLET, nummerierte Listen mit der Nummer, Unterpunkte sind eingerückt.
    Tabellenzellen stehen durch Tabulatoren getrennt. Ein Link steht als „Text (Adresse)“, ein Bild als sein Alt-Text.
    Formeln ($...$ und $$...$$) bleiben unverändert."""
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    formulas = []
    if MATH_OPEN not in text and MATH_CLOSE not in text:  # sonst wären die Platzhalter nicht eindeutig
        text = MATH.sub(lambda m: protect(formulas, m.group(0)), text)
    result = "\n\n".join(block_texts(SyntaxTreeNode(PARSER.parse(text)).children)).strip("\n").rstrip()
    return MATH_SLOT.sub(lambda m: formulas[int(m.group(1))], result) if formulas else result


def protect(formulas, formula):
    """Merkt sich die Formel und gibt den Platzhalter dafür zurück, damit der Parser sie nicht anfasst."""
    formulas.append(formula)
    return f"{MATH_OPEN}{len(formulas) - 1}{MATH_CLOSE}"


def block_texts(nodes):
    """Die Blöcke einer Ebene als Texte. Leere Blöcke (etwa eine Trennlinie) fallen weg."""
    texts = (block_text(node) for node in nodes)
    return [t for t in texts if t]


def block_text(node):
    kind = node.type
    if kind in ("fence", "code_block"):
        return node.content.rstrip("\n")
    if kind == "blockquote":
        return "\n\n".join(block_texts(node.children))
    if kind in ("bullet_list", "ordered_list"):
        return list_text(node)
    if kind == "table":
        return table_text(node)
    if kind == "hr":
        return ""
    if node.children and node.children[0].type == "inline":  # Absatz und Überschrift
        return inline_text(node.children[0]).strip()
    return node.content


def list_text(node):
    """Eine Liste: je Punkt das Zeichen oder die Nummer vorn, die Folgezeilen eingerückt. Eine lockere Liste (Leerzeilen
    zwischen den Punkten) behält ihre Leerzeilen. markdown-it-py erkennt sie an den Absätzen, die nicht verborgen sind."""
    number = int(node.attrs.get("start", 1)) if node.type == "ordered_list" else None
    loose = any(not child.nester_tokens.opening.hidden for item in node.children for child in item.children
                if child.type == "paragraph")
    gap = "\n\n" if loose else "\n"
    items = []
    for item in node.children:
        marker = BULLET if number is None else f"{number}."
        number = None if number is None else number + 1
        lines = gap.join(block_texts(item.children)).split("\n")
        pad = " " * (len(marker) + 1)
        items.append("\n".join([f"{marker} {lines[0]}".rstrip(), *[pad + line if line else "" for line in lines[1:]]]))
    return gap.join(items)


def table_text(node):
    """Eine Tabelle: eine Zeile je Tabellenzeile, die Zellen durch Tabulatoren getrennt (so fügt sie auch eine
    Tabellenkalkulation richtig ein)."""
    rows = []
    for part in node.children:  # thead und tbody
        for row in part.children:
            rows.append("\t".join(inline_text(cell.children[0]).strip() if cell.children else "" for cell in row.children))
    return "\n".join(rows)


def inline_text(node):
    """Der Text einer Zeile samt Hervorhebungen, Code, Links und Bildern, ohne deren Zeichen."""
    parts = []
    for child in node.children:
        if child.type == "link":
            parts.append(link_text(child))
        elif child.type == "softbreak":
            parts.append(" ")
        elif child.type == "hardbreak":
            parts.append("\n")
        elif child.children:  # Hervorhebung, Fettdruck, Durchgestrichenes, Bild (sein Alt-Text)
            parts.append(inline_text(child))
        else:  # Text und Code im Text
            parts.append(child.content)
    return "".join(parts)


def link_text(node):
    """„Text (Adresse)“. Steht die Adresse schon als Text da (Autolink, oder der Text ist die Adresse), nur einmal.
    Bei einer Mail- oder Telefonadresse steht in der Klammer die Adresse ohne das „mailto:“ bzw. „tel:“ davor."""
    text, href = inline_text(node), str(node.attrs.get("href", ""))
    address = re.sub(r"^(?:mailto|tel):", "", href)
    if not href or node.markup == "autolink" or bare(text) == bare(address):
        return text or address
    return f"{text} ({address})" if text else address


def bare(address):
    """Eine Adresse ohne Schema (https://) und ohne Schrägstrich am Ende, klein geschrieben: zum Vergleich mit dem
    Text eines Links."""
    return re.sub(r"^[a-z][a-z0-9+.-]*://", "", address, flags=re.I).rstrip("/").lower()
