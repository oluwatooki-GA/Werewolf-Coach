"""Structural rules from CONSTRAINTS.md, checked with the stdlib `ast` module.

A. engine/ imports only the stdlib (minus network and clock modules), pydantic, and itself.
B. agents/ may import from werewolf.engine only `views` and `actions`.
C. litellm, openai and anthropic are imported only under llm/.
D. No dynamic imports (`__import__`, importlib) outside llm/.
"""
import ast
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"

ENGINE_BANNED_STDLIB = {
    "socket", "ssl", "http", "urllib", "ftplib", "smtplib", "imaplib", "poplib",
    "socketserver", "xmlrpc", "subprocess", "ctypes", "time", "datetime", "uuid", "secrets",
}  # fmt: skip
AGENT_ENGINE_ALLOWED = ("werewolf.engine.views", "werewolf.engine.actions")
LLM_PACKAGES = {"litellm", "openai", "anthropic"}


def _targets(tree: ast.AST, package: list[str]) -> list[str]:
    """Every module an import statement can reach, as a full dotted name."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - (node.level - 1)] if node.level else []
            module = ".".join(base + ([node.module] if node.module else []))
            if module in ("werewolf", "werewolf.engine"):
                found += [f"{module}.{alias.name}" for alias in node.names]
            else:
                found.append(module)
    return found


def _calls_dynamic_import(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("__import__", "import_module")
        or isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "import_module"
        for node in ast.walk(tree)
    )


def _is_under(target: str, prefix: str) -> bool:
    return target == prefix or target.startswith(prefix + ".")


def violations(src_root: Path) -> list[str]:
    found: list[str] = []
    pkg_root = src_root / "werewolf"
    for path in sorted(pkg_root.rglob("*.py")):
        rel = path.relative_to(pkg_root)
        package = ["werewolf", *rel.parts[:-1]]
        area = rel.parts[0] if len(rel.parts) > 1 else ""
        tree = ast.parse(path.read_text(encoding="utf-8"))
        where = rel.as_posix()
        for target in _targets(tree, package):
            top = target.split(".")[0]
            if area == "engine":
                stdlib = top in sys.stdlib_module_names and top not in ENGINE_BANNED_STDLIB
                if not (stdlib or top == "pydantic" or _is_under(target, "werewolf.engine")):
                    found.append(f"{where}: engine may not import {target}")
            if area == "agents" and _is_under(target, "werewolf.engine"):
                if not any(_is_under(target, ok) for ok in AGENT_ENGINE_ALLOWED):
                    found.append(f"{where}: agents may not import {target}")
            if area != "llm" and top in LLM_PACKAGES:
                found.append(f"{where}: only llm/ may import {target}")
            if area != "llm" and top == "importlib":
                found.append(f"{where}: dynamic imports are not allowed ({target})")
        if area != "llm" and _calls_dynamic_import(tree):
            found.append(f"{where}: dynamic imports are not allowed")
    return found


def write(root: Path, rel: str, code: str) -> None:
    path = root / "werewolf" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)


def test_required_packages_exist() -> None:
    for package in ("engine", "agents", "llm"):
        assert (SRC / "werewolf" / package / "__init__.py").is_file(), package


def test_real_source_tree_follows_the_rules() -> None:
    assert violations(SRC) == []


def test_clean_tree_has_no_violations(tmp_path: Path) -> None:
    write(tmp_path, "engine/rules.py", "import random\nfrom pydantic import BaseModel\n")
    write(tmp_path, "engine/views.py", "from . import rules\nfrom werewolf.engine import rules\n")
    write(tmp_path, "agents/bot.py", "from werewolf.engine.views import PlayerView\n")
    write(tmp_path, "agents/bot2.py", "from werewolf.engine import views, actions\n")
    write(tmp_path, "llm/ledger.py", "import litellm\n")
    assert violations(tmp_path) == []


def test_engine_rejects_a_third_party_import(tmp_path: Path) -> None:
    write(tmp_path, "engine/bad.py", "import requests\n")
    assert any("engine/bad.py" in v and "requests" in v for v in violations(tmp_path))


def test_engine_rejects_a_network_module(tmp_path: Path) -> None:
    write(tmp_path, "engine/bad.py", "import socket\n")
    assert any("engine/bad.py" in v and "socket" in v for v in violations(tmp_path))


def test_engine_rejects_the_clock(tmp_path: Path) -> None:
    write(tmp_path, "engine/bad.py", "from datetime import datetime\n")
    assert any("engine/bad.py" in v for v in violations(tmp_path))


def test_engine_rejects_importing_other_werewolf_packages(tmp_path: Path) -> None:
    write(tmp_path, "engine/bad.py", "from werewolf.llm import ledger\n")
    assert any("engine/bad.py" in v for v in violations(tmp_path))


def test_engine_rejects_a_relative_import_that_leaves_the_engine(tmp_path: Path) -> None:
    write(tmp_path, "engine/bad.py", "from ..agents import bot\n")
    assert any("engine/bad.py" in v for v in violations(tmp_path))


def test_agents_reject_engine_game_state(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "from werewolf.engine.state import GameState\n")
    assert any("agents/bad.py" in v and "engine.state" in v for v in violations(tmp_path))


def test_agents_reject_importing_the_engine_state_module_by_name(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "from werewolf.engine import state\n")
    assert any("agents/bad.py" in v and "engine.state" in v for v in violations(tmp_path))


def test_agents_reject_a_relative_import_of_engine_state(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "from ..engine import state\n")
    assert any("agents/bad.py" in v and "engine.state" in v for v in violations(tmp_path))


def test_agents_reject_a_bare_engine_package_import(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "import werewolf.engine\n")
    assert any("agents/bad.py" in v for v in violations(tmp_path))


def test_agents_reject_a_star_import_from_the_engine(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "from werewolf.engine import *\n")
    assert any("agents/bad.py" in v for v in violations(tmp_path))


def test_model_libraries_are_rejected_outside_llm(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "import openai\n")
    write(tmp_path, "strategies/bad.py", "from anthropic import Anthropic\n")
    found = violations(tmp_path)
    assert any("agents/bad.py" in v and "openai" in v for v in found)
    assert any("strategies/bad.py" in v and "anthropic" in v for v in found)


def test_dynamic_imports_are_rejected_outside_llm(tmp_path: Path) -> None:
    write(tmp_path, "agents/bad.py", "m = __import__('litellm')\n")
    write(tmp_path, "tagger/bad.py", "import importlib\nm = importlib.import_module('openai')\n")
    found = violations(tmp_path)
    assert any("agents/bad.py" in v for v in found)
    assert any("tagger/bad.py" in v for v in found)
