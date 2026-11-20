"""Prüft, dass README und Code zusammenpassen, damit die Dokumentation nicht still veraltet."""
import re

from helpers import PACKAGE_DIR, ROOT, SOURCE_FILES

README = (ROOT / "README.md").read_text("utf-8")
APP = "\n".join(p.read_text("utf-8") for p in SOURCE_FILES)  # Hauptskript und alle Module von aibui
TEST_FILES = sorted((ROOT / "tests").glob("*.py"))
TESTS_SOURCE = "\n".join(p.read_text("utf-8") for p in TEST_FILES)

# Namen, die die README erwähnt, die aber aus Bibliotheken oder dem Python-Kern stammen
EXTERNAL_FUNCTIONS = {"generate_content", "create", "count_tokens", "model_dump", "exec", "get", "setdefault", "tabs",
                      "fragment", "rerun", "run", "set_value", "from_file", "getattr", "compile", "split", "join",
                      "resolve", "mkdir", "read_text", "write_text", "glob", "upload", "download", "cancel"}
EXTERNAL_CONSTANTS = {"GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_BATCH_UI_HOME", "MAX_TOKENS", "STOP", "SAFETY", "RUNNING",
                      "DONE", "FAILED", "CANCELLED", "INTERRUPTED", "PENDING", "STREAMLIT_LOGGER_LEVEL",
                      "GEMINI_UI_HOME"}  # alter Name von AI_BATCH_UI_HOME, steht nur im Hinweis zur Umbenennung (Issue #18)


def defined_functions(source):
    return set(re.findall(r"^\s*(?:def|class) ([A-Za-z_][A-Za-z_0-9]*)", source, flags=re.M))


def test_functions_named_in_the_readme_exist():
    named = set(re.findall(r"`([A-Za-z_][A-Za-z_0-9]*)\(", README))
    unknown = sorted(n for n in named - EXTERNAL_FUNCTIONS if n not in defined_functions(APP + TESTS_SOURCE))
    assert not unknown, f"In der README genannt, im Code nicht (mehr) vorhanden: {unknown}"


def test_constants_named_in_the_readme_exist():
    named = set(re.findall(r"`([A-Z][A-Z_]{3,})`", README))
    unknown = sorted(n for n in named - EXTERNAL_CONSTANTS
                     if not re.search(rf"^{n}\s*=", APP + "\n" + TESTS_SOURCE, flags=re.M))
    assert not unknown, f"In der README genannt, im Code nicht (mehr) definiert: {unknown}"


def test_session_and_widget_keys_in_the_readme_exist_in_the_code():
    section = README.split("### Session-State- und Widget-Schlüssel")[1].split("\n## ")[0]
    keys = set()
    for line in section.splitlines():
        match = re.match(r"\|\s*((?:`[^`]+`(?:,\s*)?)+)\s*\|", line)
        if match:
            keys |= {k.replace("<name>", "") for k in re.findall(r"`([^`]+)`", match.group(1))}
    assert {"view", "mode", "sel", "raw"} <= keys, "Tabelle der Schlüssel nicht gefunden oder unvollständig"
    # Schlüssel dürfen im Code auch zusammengesetzt sein (z. B. "label_" + Art): dann genügt das Präfix bis zum letzten "_"
    unknown = sorted(k for k in keys if f'"{k}' not in APP and f'"{k.rsplit("_", 1)[0]}_' not in APP)
    assert not unknown, f"In der README genannte Schlüssel fehlen im Code: {unknown}"


def test_requirement_versions_are_documented():
    requirements = (ROOT / "requirements.txt").read_text()
    pinned = re.findall(r"^(streamlit|google-genai|openai|anthropic)(>=[0-9.]+)", requirements, flags=re.M)
    assert len(pinned) == 4
    for name, version in pinned:
        assert f"{name}{version}" in README, f"{name}{version} aus requirements.txt fehlt in der README"


def test_project_files_named_in_the_readme_exist():
    for name in ("src/ai_batch_ui.py", "src/aibui", "requirements.txt", "requirements-dev.txt", "pytest.ini",
                 "README.md"):
        assert name in README and (ROOT / name).exists(), f"{name} fehlt in der README oder im Projekt"


def test_every_package_module_is_described_in_the_readme():
    for path in PACKAGE_DIR.glob("*.py"):
        if path.name != "__init__.py":
            assert f"src/aibui/{path.name}" in README, f"src/aibui/{path.name} wird in der README nicht erwähnt"


def test_package_modules_named_in_the_readme_exist():
    named = set(re.findall(r"src/aibui/([A-Za-z_0-9]+\.py)", README))
    assert named, "Keine Module von aibui in der README gefunden"
    unknown = sorted(n for n in named if not (PACKAGE_DIR / n).exists())
    assert not unknown, f"In der README genannte Module fehlen in src/aibui/: {unknown}"


def test_every_test_module_is_described_in_the_readme():
    for path in TEST_FILES:
        if path.name.startswith("test_") or path.name in ("conftest.py", "fakes.py", "helpers.py"):
            assert path.name in README, f"tests/{path.name} wird in der README nicht erwähnt"
