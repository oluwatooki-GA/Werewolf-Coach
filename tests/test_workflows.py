"""The GitHub workflows: what runs when, and that no secret is written in them."""

import re
from pathlib import Path
from typing import Any

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def load(name: str) -> dict[str, Any]:
    doc: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    doc["on"] = doc.pop(True)  # YAML 1.1 reads the key `on` as the boolean true
    return doc


def text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def steps(doc: dict[str, Any], job: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = doc["jobs"][job]["steps"]
    return found


def looks_like_a_secret(content: str) -> bool:
    return bool(
        re.search(
            r"https://api\.render\.com/deploy/|https://api\.vercel\.com/v1/integrations/deploy|"
            r"ghp_[A-Za-z0-9]{20}|github_pat_|sk-[A-Za-z0-9]{10}|postgres(ql)?://[^\s$]+:[^\s$]+@",
            content,
        )
    )


# --- ci ------------------------------------------------------------------------------------


def test_ci_runs_on_pushes_and_pull_requests_and_can_be_called_by_the_release() -> None:
    triggers = load("ci.yml")["on"]
    assert {"push", "pull_request", "workflow_call"} <= set(triggers)


def test_ci_checks_python_the_site_and_both_images() -> None:
    assert set(load("ci.yml")["jobs"]) == {"python", "web", "docker"}
    web = " ".join(str(s.get("run", "")) for s in steps(load("ci.yml"), "web"))
    assert all(part in web for part in ("typecheck", "lint", "npm test", "build"))
    docker = " ".join(str(s.get("run", "")) for s in steps(load("ci.yml"), "docker"))
    assert "docker compose config" in docker and "docker compose build" in docker


# --- eval-check ----------------------------------------------------------------------------


def test_the_eval_check_runs_for_changes_to_prompts_cards_and_agents_only() -> None:
    paths = load("eval-check.yml")["on"]["pull_request"]["paths"]
    for needed in ("src/werewolf/prompts/**", "src/werewolf/agents/**", "cards/**", "evals/**"):
        assert needed in paths


def test_the_eval_check_fails_the_run_when_a_number_got_worse() -> None:
    run = " ".join(str(s.get("run", "")) for s in steps(load("eval-check.yml"), "evals"))
    assert "werewolf.cli evals" in run and "exit 1" in run
    assert "GITHUB_STEP_SUMMARY" in run  # the table is shown on the run page


def test_the_eval_check_spends_nothing() -> None:
    content = text("eval-check.yml")
    assert "secrets." not in content and "API_KEY" not in content


# --- release -------------------------------------------------------------------------------


def test_only_a_version_tag_deploys() -> None:
    triggers = load("release.yml")["on"]
    assert list(triggers) == ["push"] and triggers["push"] == {"tags": ["v*"]}


def test_the_deploy_waits_for_the_checks_and_the_eval_check() -> None:
    doc = load("release.yml")
    assert set(doc["jobs"]["deploy"]["needs"]) == {"checks", "evals"}
    assert doc["jobs"]["checks"]["uses"] == "./.github/workflows/ci.yml"


def test_the_database_is_prepared_then_the_live_api_is_checked_then_the_release_is_written() -> (
    None
):
    names = [str(s.get("name", "")) for s in steps(load("release.yml"), "deploy")]
    order = [
        next(i for i, n in enumerate(names) if n.startswith(start))
        for start in ("Prepare the database", "Check the live API", "Mark")
    ]
    assert order == sorted(order)


def test_the_release_does_not_call_a_deploy_hook_because_render_and_vercel_deploy_themselves() -> (
    None
):
    assert "DEPLOY_HOOK" not in text("release.yml") and "curl" not in "".join(
        str(s.get("run", ""))
        for s in steps(load("release.yml"), "deploy")
        if "Check" not in s.get("name", "")
    )


def test_the_release_refuses_to_finish_if_a_fault_switch_is_on_in_production() -> None:
    check = next(
        s for s in steps(load("release.yml"), "deploy") if "Check the live API" in s.get("name", "")
    )
    assert r'"faults":\[\]' in check["run"]


def test_a_release_marks_the_deploy_and_only_it_may_write() -> None:
    doc = load("release.yml")
    assert doc["permissions"] == {"contents": "read"}
    assert doc["jobs"]["deploy"]["permissions"] == {"contents": "write"}
    assert "gh release create" in text("release.yml")


# --- secrets -------------------------------------------------------------------------------


def test_every_secret_a_workflow_uses_comes_from_the_actions_secrets() -> None:
    allowed = {"DATABASE_URL"}
    used = set()
    for path in WORKFLOWS.glob("*.yml"):
        used |= set(re.findall(r"secrets\.([A-Z_]+)", path.read_text(encoding="utf-8")))
    assert used == allowed


def test_no_workflow_has_a_secret_written_into_it() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        assert not looks_like_a_secret(path.read_text(encoding="utf-8")), path.name


def test_the_secret_detector_sees_what_it_is_meant_to() -> None:
    assert looks_like_a_secret("curl https://api.render.com/deploy/srv-abc?key=xyz")
    assert looks_like_a_secret("DATABASE_URL: postgresql://user:pass@host/db")
    assert looks_like_a_secret("token: ghp_abcdefghijklmnopqrst")
    assert not looks_like_a_secret("DATABASE_URL: ${{ secrets.DATABASE_URL }}")
