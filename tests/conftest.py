"""Gemeinsame Fixtures. Jeder Test läuft in einem Wegwerf-Ordner und ohne echten API-Zugriff."""
import os

# Streamlit meldet im „bare mode“ (ohne laufende App) „missing ScriptRunContext“. Das ist hier erwartet und stört nur.
os.environ.setdefault("STREAMLIT_LOGGER_LEVEL", "error")

import importlib  # noqa: E402
import pkgutil  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
import time as real_time  # noqa: E402
from datetime import date  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from helpers import PACKAGE, PACKAGE_DIR, ROOT  # noqa: E402

PRICE_DAY = date(2026, 12, 15)  # der Tag der Preise in allen Tests: nach dem Preiswechsel von Gemini 4 am 01.12.2026


@pytest.fixture(scope="session", autouse=True)
def project_folder_stays_untouched():
    """Sicherheitsnetz: Kein Test darf conf/ oder data/ im echten Projektordner anlegen oder verändern."""
    def snapshot():
        state = {}
        for name in ("conf", "data"):
            folder = ROOT / name
            if folder.exists():
                state[name] = sorted((str(p.relative_to(ROOT)), p.stat().st_size, p.stat().st_mtime_ns)
                                     for p in folder.rglob("*") if p.is_file())
        return state

    before = snapshot()
    yield
    assert snapshot() == before, ("Ein Test hat conf/ oder data/ im Projektordner verändert. "
                                  "Testdaten gehören nach AI_BATCH_UI_HOME (Fixture „home“).")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Wegwerf-Ordner als Wurzel für conf/ und data/ (AI_BATCH_UI_HOME) und Dummy-API-Keys für alle Anbieter."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("AI_BATCH_UI_HOME", str(folder))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-claude-key")
    return folder


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    """Ohne installierten Fake-Client scheitert jeder Versuch, einen echten Client zu bauen."""
    import anthropic
    import google.genai as genai
    import openai

    def refuse(*args, **kwargs):
        raise AssertionError("Kein Fake-Client installiert: Der Test hätte die echte API angesprochen.")

    monkeypatch.setattr(genai, "Client", refuse)
    monkeypatch.setattr(openai, "OpenAI", refuse)
    monkeypatch.setattr(anthropic, "Anthropic", refuse)


def forget_package():
    """Entfernt alle Module von aibui aus dem Importspeicher. Der nächste Import rechnet BASE, DATA_DIR usw. neu."""
    for name in [n for n in sys.modules if n == PACKAGE or n.startswith(PACKAGE + ".")]:
        del sys.modules[name]


@pytest.fixture(autouse=True)
def fresh_package(home):
    """Die Module von aibui berechnen ihre Ordner beim Import aus AI_BATCH_UI_HOME. Damit jeder Test seinen eigenen Ordner
    sieht, fliegen sie vor und nach jedem Test aus dem Importspeicher. Das gilt auch für die Oberflächentests: Deren
    Hauptskript importiert die Module selbst, und zwar in jedem Test neu."""
    forget_package()
    yield
    forget_package()


@pytest.fixture(autouse=True)
def price_day(request, fresh_package, monkeypatch):
    """Alle Tests rechnen die Preise mit demselben Tag PRICE_DAY. Sonst hingen die Reihenfolge der Modellliste und die
    Preise in der Infobox vom Datum des Laufs ab (pricing.model_choices(): bis 30.11.2026 ist Neon das teuerste
    Gemini-Modell, danach Carbon). Das vorausgewählte Modell hängt seit Issue #45 nicht mehr vom Tag ab. Das Modul
    pricing wird hier vorab importiert, damit das Hauptskript in den Oberflächentests dasselbe Modul mit dem festen Tag
    nutzt. Ein Test, der einen anderen Tag braucht, setzt ihn selbst (Fixture on_day). Ein Test, der die echte Uhr
    oder einen frischen Import von aibui braucht (etwa aus einer Kopie des Pakets), trägt den Marker real_date: Dann
    tut die Fixture nichts."""
    if request.node.get_closest_marker("real_date"):
        return
    pricing = importlib.import_module(f"{PACKAGE}.pricing")
    monkeypatch.setattr(pricing, "today", lambda: PRICE_DAY)


@pytest.fixture
def pricing(app):
    """Das Modul pricing."""
    return app.modules["pricing"]


@pytest.fixture
def on_day(pricing, monkeypatch):
    """on_day(Datum) legt fest, welcher Tag für die Preise heute ist (statt PRICE_DAY)."""
    def make(day):
        monkeypatch.setattr(pricing, "today", lambda: day)
    return make


@pytest.fixture
def use_all(monkeypatch):
    """Installiert Fakes für alle drei Anbieter, damit die Oberfläche jeden von ihnen bauen kann."""
    from fakes import FakeClaude, FakeGemini, FakeOpenAI, install, install_claude, install_openai
    install(monkeypatch, FakeGemini())
    install_openai(monkeypatch, FakeOpenAI())
    install_claude(monkeypatch, FakeClaude())


class StubTime:
    """Ersatz für das Modul time: keine echten Pausen (sleep wird nur notiert), aber echte Uhr."""

    def __init__(self):
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def time(self):
        return real_time.time()


class AppModule:
    """Alle Module von aibui als ein Objekt: app.parse_line(...). Ein Name wird der Reihe nach in allen Modulen gesucht.
    app.modules["config"] liefert ein Modul selbst, z. B. um dort etwas zu ersetzen."""

    def __init__(self, modules):
        self.modules = modules

    def __getattr__(self, name):
        for module in self.modules.values():
            if name in vars(module):
                return vars(module)[name]
        raise AttributeError(name)


@pytest.fixture
def app(fresh_package):
    """Die Logik der App ohne Oberfläche (alle Module von aibui), Ordner aus der Fixture home."""
    names = sorted(m.name for m in pkgutil.iter_modules([str(PACKAGE_DIR)]))
    return AppModule({name: importlib.import_module(f"{PACKAGE}.{name}") for name in names})


@pytest.fixture
def fake_time(app, monkeypatch):
    """Ersetzt time in allen Modulen der App-Logik: Wiederholungs- und Wartepausen kosten keine Zeit."""
    stub = StubTime()
    for module in app.modules.values():
        if hasattr(module, "time"):
            monkeypatch.setattr(module, "time", stub)
    return stub


@pytest.fixture
def rt():
    """Ersatz für runtime(): die Sperre für den Verlauf."""
    return SimpleNamespace(lock=threading.Lock())
