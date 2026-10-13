"""Diff-scoped enforcement of the CONSTRAINTS.md floor. Stdlib only.

Usage: python scripts/floor_guard.py [--base main]
Exit 0 clean, 1 floor violation, 2 guard could not run.
Reports rule and location, never a matched value.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "main"

# Files that define the bar. Any change needs the owner's approval.
BAR_FILES = ("scripts/floor_guard.py", "scripts/check.ps1", ".constraints/")

SUPPRESSIONS = re.compile(
    r"#\s*noqa|#\s*type:\s*ignore|#\s*ruff:\s*noqa|#\s*mypy:\s*ignore-errors"
    r"|#\s*pragma:\s*no cover|#\s*nosec"
)
STUBS = re.compile(
    r"raise NotImplementedError|except[^:\n]*:\s*pass\b|^\s*pass\s*#\s*stub|\bTODO\b"
)
SKIPS = re.compile(r"pytest\.mark\.(skip|skipif|xfail)|pytest\.skip\(|pytest\.xfail\(")


def git(*args: str) -> str | None:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def main() -> int:
    base = (git("merge-base", BASE, "HEAD") or "").strip()
    if not base:
        print(f"floor-guard: no merge base against '{BASE}'", file=sys.stderr)
        return 2

    added: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []
    diff = git("diff", "--unified=0", base, "--") or ""
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("--- "):
            if line.startswith("--- a/"):
                path = line[6:]
        elif line.startswith("+"):
            added.append((path, line[1:]))
        elif line.startswith("-"):
            removed.append((path, line[1:]))

    # Untracked files count as fully added (git diff cannot see them).
    untracked = (git("ls-files", "--others", "--exclude-standard") or "").split("\n")
    for f in filter(None, untracked):
        p = ROOT / f
        try:
            for text in p.read_text(encoding="utf-8").splitlines():
                added.append((f, text))
        except (UnicodeDecodeError, OSError):
            pass

    changed = {p for p, _ in added} | {p for p, _ in removed}
    findings: list[tuple[str, str, str]] = []

    def flag(rule: str, where: str, text: str = "") -> None:
        findings.append((rule, where, text.strip()[:100]))

    # Secrets file: must be ignored and never tracked.
    if (ROOT / ".env").exists():
        if git("ls-files", ".env"):
            flag("env-tracked", ".env", "tracked by git")
        if git("check-ignore", ".env") is None:
            flag("env-not-ignored", ".env", "add to .gitignore")

    # The bar itself.
    for f in sorted(changed):
        if any(f == b or f.startswith(b) for b in BAR_FILES):
            flag("bar-edited", f, "owner approval required")

    for f, text in added:
        if f.endswith(".py") and f != "scripts/floor_guard.py":
            if SUPPRESSIONS.search(text):
                flag("silenced-checker", f, text)
            if STUBS.search(text):
                flag("unfinished-work", f, text)
            if f.startswith("tests/") and SKIPS.search(text):
                flag("test-made-easier", f, text)
        if f == "CONSTRAINTS.md" and re.match(r"^\|\s*W\d+\s*\|", text):
            flag("new-exception", f, text)

    for f, text in removed:
        if f.startswith("tests/") and re.search(r"\bassert\b|pytest\.raises", text):
            flag("assertion-removed", f, text)

    deleted = (git("diff", "--diff-filter=D", "--name-only", base, "--") or "").split("\n")
    for f in filter(None, deleted):
        if f.startswith("tests/"):
            flag("test-deleted", f)

    # Thresholds in CONSTRAINTS.md must not go down; rules and floor bullets must not vanish.
    def nums(s: str) -> list[float]:
        return [float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)]

    def key(s: str) -> str:
        return s.split("|")[1].strip() if s.startswith("|") else s

    add_c = [t for f, t in added if f == "CONSTRAINTS.md"]
    for f, text in removed:
        if f != "CONSTRAINTS.md" or not (text.startswith("|") or text.startswith("- ")):
            continue
        match = next((a for a in add_c if key(a) == key(text)), None)
        if match is None:
            flag("rule-removed", f, text)
        elif any(n < o for n, o in zip(nums(match), nums(text))):
            flag("threshold-lowered", f, text)

    # New dependencies need the owner's approval.
    approved = {
        ln.strip().lower()
        for ln in (ROOT / ".constraints" / "approved-deps.txt").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    for f, text in added:
        if f == "pyproject.toml":
            m = re.match(r'^\s*"([A-Za-z0-9_.\-]+)', text)
            if m and m.group(1).lower().replace("_", "-") not in approved:
                flag("unapproved-dependency", f, m.group(1))

    if not findings:
        print("floor-guard: clean")
        return 0
    print(f"floor-guard: {len(findings)} violation(s):", file=sys.stderr)
    for rule, where, text in findings:
        print(f"  [{rule}] {where}: {text}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
