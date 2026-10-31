"""The Render blueprint for the API: a free Python web service, secrets named but never valued."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
SERVICE = BLUEPRINT["services"][0]
ENV = {item["key"]: item for item in SERVICE["envVars"]}


def test_it_is_one_free_python_web_service() -> None:
    assert len(BLUEPRINT["services"]) == 1
    assert (SERVICE["type"], SERVICE["runtime"], SERVICE["plan"]) == ("web", "python", "free")


def test_it_installs_exactly_what_the_lock_file_says_and_no_dev_tools() -> None:
    assert SERVICE["buildCommand"] == "uv sync --frozen --no-dev"


def test_it_serves_on_the_port_render_gives_without_reinstalling_dev_tools_at_start() -> None:
    start = SERVICE["startCommand"]
    assert "werewolf.cli app serve" in start
    assert "--host 0.0.0.0" in start and "--port $PORT" in start
    assert (
        "--frozen" in start and "--no-dev" in start
    )  # `uv run` would otherwise sync the dev group


def test_the_python_version_is_the_one_the_project_pins() -> None:
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert ENV["PYTHON_VERSION"]["value"].startswith(pinned + ".")


def test_render_checks_health_where_the_api_answers_it() -> None:
    assert SERVICE["healthCheckPath"] == "/health"


def test_render_deploys_by_itself_whenever_the_repository_is_pushed() -> None:
    assert SERVICE["autoDeploy"] is True


def test_the_site_is_the_only_origin_and_the_rate_limit_sees_visitors() -> None:
    assert ENV["FORWARDED_ALLOW_IPS"]["value"] == "*"  # the site passes the visitor's address on
    assert ENV["WEB_ORIGIN"] == {"key": "WEB_ORIGIN", "sync": False}  # set to the Vercel address


def test_every_secret_and_setting_the_owner_chooses_is_asked_for_not_written_down() -> None:
    for key in ("DATABASE_URL", "OPENAI_API_KEY", "ADMIN_TOKEN", "PLAY_MODEL", "WEB_ORIGIN"):
        assert ENV[key] == {"key": key, "sync": False}, key
    valued = {key for key, item in ENV.items() if "value" in item}
    assert valued == {"PYTHON_VERSION", "FORWARDED_ALLOW_IPS"}  # nothing else has a value


def test_no_fault_switch_and_no_test_mode_and_nothing_that_looks_like_a_key() -> None:
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "FAULTS" not in ENV and "APP_ENV" not in ENV
    assert not re.search(r"sk-[A-Za-z0-9]|postgres(ql)?://[^\s]*:[^\s]*@", text)
