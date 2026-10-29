"""The container files: what the local stack runs, and that no secret can end up in the image."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_the_stack_has_a_database_with_a_health_check_and_an_api_that_waits_for_it() -> None:
    services = COMPOSE["services"]
    assert services["db"]["image"].startswith("postgres:16")
    assert "healthcheck" in services["db"] and "volumes" in services["db"]
    api = services["api"]
    assert api["build"] == "." and api["depends_on"]["db"]["condition"] == "service_healthy"
    assert api["environment"]["DATABASE_URL"].startswith("postgresql://")
    assert "db" in api["environment"]["DATABASE_URL"].split("@")[1]  # the compose service name


def test_data_and_cards_are_mounted_read_only_not_copied_into_the_image() -> None:
    mounts = COMPOSE["services"]["api"]["volumes"]
    assert "./data/games:/app/data/games:ro" in mounts
    assert "./data/coach:/app/data/coach:ro" in mounts
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert {".env", ".env.*", "data/", ".git/"} <= set(dockerignore)


def test_no_key_is_written_in_the_compose_file_or_the_dockerfile() -> None:
    for name in ("docker-compose.yml", "Dockerfile"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "sk-" not in text and "sk_" not in text
    api_env = COMPOSE["services"]["api"]["environment"]
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        assert api_env.get(key, "${X}").startswith("${")  # passed in from .env, never a value


def test_the_image_runs_as_a_normal_user_and_starts_the_api() -> None:
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("USER ") and "root" not in line for line in lines)
    assert any("app" in line and "serve" in line and line.startswith("CMD") for line in lines)


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker is not installed")
def test_docker_compose_accepts_the_file() -> None:
    result = subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "config", "--quiet"],
        capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    assert result.returncode == 0, result.stderr


def test_the_site_runs_beside_the_api_and_reaches_it_by_its_service_name() -> None:
    web = COMPOSE["services"]["web"]
    assert web["build"] == "./web"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert web["environment"]["API_URL"] == "http://api:8000"
    assert "${WEB_PORT:-3100}:3100" in web["ports"]
    assert "healthcheck" in COMPOSE["services"]["api"]  # the site waits for a working API


def test_the_site_image_holds_no_secret_and_runs_as_a_normal_user() -> None:
    dockerfile = (ROOT / "web" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER node" in dockerfile and ".next/standalone" in dockerfile
    assert "API_KEY" not in dockerfile and "NEXT_PUBLIC" not in dockerfile
    ignored = (ROOT / "web" / ".dockerignore").read_text(encoding="utf-8").split()
    assert {"node_modules", ".next", ".env*"} <= set(ignored)
    web_env = COMPOSE["services"]["web"]["environment"]
    assert not any(
        "KEY" in name or "NEXT_PUBLIC" in name for name in web_env
    )  # no key reaches the browser


def test_play_mode_is_off_by_default_and_the_api_trusts_the_site_to_name_the_visitor() -> None:
    env = COMPOSE["services"]["api"]["environment"]
    assert (
        env["PLAY_MODEL"] == "${PLAY_MODEL:-}"
    )  # empty unless someone turns it on: spends nothing
    assert env["PLAY_GAME_BUDGET"] == "${PLAY_GAME_BUDGET:-0.40}"  # defaults match the API's own
    assert env["PLAY_GAME_ESTIMATE"] == "${PLAY_GAME_ESTIMATE:-0.30}"
    # the site passes each visitor's address on; without this the rate limit would count the
    # site as one visitor and every real one would share a single allowance
    assert env["FORWARDED_ALLOW_IPS"] == "*"
