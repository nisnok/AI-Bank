"""Executable architecture checks include transitive local imports."""
import ast
from pathlib import Path


ROOT = Path("src/deterministic_ui")


def imports(module):
    tree = ast.parse((ROOT / f"{module}.py").read_text())
    external, local = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            external.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None, "Extend this check for bare relative imports"
            if node.level:
                local.add(node.module.split('.')[0])
            else:
                external.add(node.module.split('.')[0])
    return external, local


def dependency_closure(module, seen=None):
    seen = set() if seen is None else seen
    if module in seen:
        return set()
    seen.add(module)
    external, local = imports(module)
    for child in local:
        external |= dependency_closure(child, seen)
    return external


def test_replay_has_no_browser_or_model_dependencies():
    dependencies = dependency_closure("replay")
    assert not dependencies & {"playwright", "openai", "google", "gemini", "anthropic", "langchain", "langgraph"}
    assert dependencies <= {"asyncio", "collections", "datetime", "decimal", "enum", "json", "pathlib",
                            "pydantic", "re", "time", "typing", "uuid", "abc"}


def test_artifact_domain_only():
    assert dependency_closure("models") <= {"decimal", "enum", "typing", "pydantic", "re"}


def test_only_adapter_imports_playwright():
    assert [file.stem for file in ROOT.glob("*.py") if "playwright" in imports(file.stem)[0]] == ["playwright_surface"]
