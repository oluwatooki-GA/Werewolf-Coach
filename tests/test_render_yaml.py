"""The Render blueprint for the API: a free Docker web service, secrets named but never valued."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BLUEPRINT = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
SERVICE = BLUEPRINT["services"][0]
ENV = {item["key"]: item for item in SERVICE["envVars"]}


def test_it_is_one_free_web_service_built_from_the_existing_dockerfile() -> None:
    assert len(BLUEPRINT["services"]) == 1
    assert (SERVICE["type"], SERVICE["runtime"], SERVICE["plan"]) == ("web", "docker", "free")
    assert (ROOT / SERVICE["dockerfilePath"]).is_file()


def test_render_checks_health_where_the_api_answers_it() -> None:
    assert SERVICE["healthCheckPath"] == "/health"


def test_a_deploy_happens_only_when_the_release_asks_for_one() -> None:
    assert SERVICE["autoDeploy"] is False  # the release workflow calls the deploy hook


def test_the_port_render_sends_traffic_to_is_the_port_the_image_serves() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    served = re.search(r'"--port", "(\d+)"', dockerfile)
    assert served is not None and ENV["PORT"]["value"] == served.group(1)


def test_the_site_is_the_only_origin_and_the_rate_limit_sees_visitors() -> None:
    assert ENV["FORWARDED_ALLOW_IPS"]["value"] == "*"  # the site passes the visitor's address on
    assert ENV["WEB_ORIGIN"] == {"key": "WEB_ORIGIN", "sync": False}  # set to the Vercel address


def test_every_secret_and_setting_the_owner_chooses_is_asked_for_not_written_down() -> None:
    for key in ("DATABASE_URL", "OPENAI_API_KEY", "ADMIN_TOKEN", "PLAY_MODEL", "WEB_ORIGIN"):
        assert ENV[key] == {"key": key, "sync": False}, key
    valued = {key for key, item in ENV.items() if "value" in item}
    assert valued == {"PORT", "FORWARDED_ALLOW_IPS"}  # nothing else has a value in the file


def test_no_fault_switch_and_no_test_mode_and_nothing_that_looks_like_a_key() -> None:
    text = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "FAULTS" not in ENV and "APP_ENV" not in ENV
    assert not re.search(r"sk-[A-Za-z0-9]|postgres(ql)?://[^\s]*:[^\s]*@", text)
