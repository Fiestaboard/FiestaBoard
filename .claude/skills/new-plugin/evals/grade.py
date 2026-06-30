#!/usr/bin/env python3
"""Grade new-plugin eval runs: structural checks + a real test run in the dev container.

Writes grading.json into each run-* dir with the schema the skill-creator aggregator/viewer
expect: {summary:{pass_rate,passed,failed,total}, expectations:[{text,passed,evidence}]}.

Usage: python3 grade.py <iteration-dir> [<fiestaboard-repo>]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

# grade.py lives at <repo>/.claude/skills/new-plugin/evals/grade.py
_DEFAULT_REPO = Path(__file__).resolve().parents[4]
REPO = Path(sys.argv[2]) if len(sys.argv) > 2 else _DEFAULT_REPO
VALID_CATEGORIES = {"art", "data", "transit", "weather", "entertainment", "utility", "home"}


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def find_container() -> str:
    """Find the running dev container by name (robust to compose project drift)."""
    r = sh(["docker", "ps", "--format", "{{.Names}}"])
    names = r.stdout.split()
    for pref in ("fiestaboard-dev",):
        if pref in names:
            return pref
    for n in names:
        if "fiestaboard" in n and not any(x in n for x in ("web", "mock", "storybook")):
            return n
    return "fiestaboard-dev"


CONTAINER = find_container()


def ensure_pytest():
    r = sh(["docker", "exec", CONTAINER, "python", "-m", "pytest", "--version"])
    if r.returncode != 0:
        print(f"  (installing pytest in container {CONTAINER}...)")
        sh(["docker", "exec", CONTAINER, "pip", "install", "-q",
            "pytest", "pytest-cov", "pytest-asyncio"])


def find_repo(outputs: Path) -> Path | None:
    for child in sorted(outputs.iterdir()):
        if child.is_dir() and child.name.startswith("fiestaboard-plugin--"):
            return child
    # fallback: any dir with a manifest.json
    for m in outputs.rglob("manifest.json"):
        return m.parent
    return None


def read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def entry_module(repo: Path, plugin_id: str) -> Path | None:
    nested = repo / "plugins" / plugin_id / "__init__.py"
    if nested.exists():
        return nested
    root = repo / "__init__.py"
    if root.exists():
        return root
    return None


def run_tests(repo: Path, plugin_id: str) -> dict:
    """Copy the repo into the container and run pytest, handling root vs nested layout."""
    nested = (repo / "plugins" / plugin_id / "__init__.py").exists()
    dest = f"/tmp/grade-{repo.name}"
    sh(["docker", "exec", CONTAINER, "sh", "-c", f"rm -rf {dest}"])
    cp = sh(["docker", "cp", str(repo), f"{CONTAINER}:{dest}"])
    if cp.returncode != 0:
        return {"ok": False, "passed": 0, "failed": 0, "coverage": 0.0, "evidence": f"docker cp failed: {cp.stderr[:200]}"}

    if nested:
        setup = f'cd {dest}; [ -f plugins/__init__.py ] || touch plugins/__init__.py'
        cov = "--cov=plugins"
    else:
        setup = (f'cd {dest}; mkdir -p plugins; touch plugins/__init__.py; '
                 f'ln -sf .. "plugins/{plugin_id}"; ln -sf . "{plugin_id}"')
        cov = "--cov=."
    script = (f'{setup}; PYTHONPATH="{dest}:/app" BOARD_READ_WRITE_KEY=test_key '
              f'python -m pytest tests/ -q {cov} --cov-report=term-missing --ignore=/app -p no:cacheprovider')
    r = sh(["docker", "exec", "-w", dest, CONTAINER, "sh", "-c", script])
    out = r.stdout + "\n" + r.stderr
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    errors = int(m.group(1)) if (m := re.search(r"(\d+) error", out)) else 0
    cov_pct = float(m.group(1)) if (m := re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", out)) else 0.0
    ok = r.returncode == 0 and passed > 0 and failed == 0 and errors == 0
    tail = "\n".join(out.strip().splitlines()[-3:])
    sh(["docker", "exec", CONTAINER, "sh", "-c", f"rm -rf {dest}"])
    return {"ok": ok, "passed": passed, "failed": failed + errors, "coverage": cov_pct,
            "evidence": f"layout={'nested' if nested else 'root'}; {passed} passed, {failed} failed, {errors} errors, cov {cov_pct}% | {tail}"}


def grade_run(run_dir: Path, eval_name: str) -> dict:
    outputs = run_dir / "outputs"
    exp = []

    def add(text, passed, evidence):
        exp.append({"text": text, "passed": bool(passed), "evidence": str(evidence)[:400]})

    repo = find_repo(outputs) if outputs.is_dir() else None
    if not repo:
        add("Standalone plugin repo produced", False, "no fiestaboard-plugin--* dir under outputs/")
        return finalize(exp)

    add("Standalone repo directory present (fiestaboard-plugin--<slug>)", True, repo.name)

    manifest = read_json(repo / "manifest.json")
    plugin_id = (manifest or {}).get("id", "")
    man_ok = bool(manifest) and all(k in manifest for k in ("id", "name", "version")) and manifest.get("category") in VALID_CATEGORIES
    add("manifest.json valid with id/name/version and a valid category", man_ok,
        f"id={plugin_id} category={(manifest or {}).get('category')}" if manifest else "missing/invalid manifest.json")

    # Naming lockstep: repo slug -> id, and plugin_id literal in entry module matches.
    slug = repo.name.replace("fiestaboard-plugin--", "")
    derived = slug.replace("-", "_")
    entry = entry_module(repo, plugin_id) if plugin_id else None
    entry_txt = entry.read_text() if entry else ""
    pid_literal = re.search(r'def plugin_id\(self\)[^\n]*\n\s*(?:""".*?"""\s*)?return\s*["\']([a-z0-9_]+)["\']',
                            entry_txt, re.S)
    pid_ok = bool(plugin_id) and plugin_id == derived and pid_literal and pid_literal.group(1) == plugin_id
    add("Naming in lockstep (repo slug -> id -> plugin_id all agree)", pid_ok,
        f"slug={slug} derived={derived} manifest_id={plugin_id} plugin_id_literal={(pid_literal.group(1) if pid_literal else None)}")

    # Required files
    required = {
        "entry module": bool(entry),
        "manifest.json": (repo / "manifest.json").exists(),
        "README.md": (repo / "README.md").exists(),
        "docs/SETUP.md": (repo / "docs" / "SETUP.md").exists(),
        "tests/test_plugin.py": (repo / "tests" / "test_plugin.py").exists(),
        "tests/test_demo_pages.py": (repo / "tests" / "test_demo_pages.py").exists(),
        "ci.yml": (repo / ".github" / "workflows" / "ci.yml").exists(),
    }
    missing = [k for k, v in required.items() if not v]
    add("All required files present (entry, manifest, README, SETUP, tests, ci.yml)", not missing,
        "all present" if not missing else f"missing: {missing}")

    add("Module exports `Plugin = <Class>`", bool(re.search(r'^\s*Plugin\s*=\s*\w+', entry_txt, re.M)),
        "found Plugin export" if re.search(r'^\s*Plugin\s*=\s*\w+', entry_txt, re.M) else "no `Plugin =` export")

    rel = (repo / ".github" / "workflows" / "release.yml").exists()
    add("Release automation present (.github/workflows/release.yml)", rel,
        "release.yml present" if rel else "no release.yml (version-bump automation missing)")

    png = repo / "docs" / "board-display.png"
    add("docs/board-display.png present", png.exists(), "present" if png.exists() else "missing")

    # No hardcoded secret (heuristic): long base64-ish/hex tokens assigned to *key* vars.
    blob = "\n".join(p.read_text(errors="ignore") for p in repo.rglob("*.py")) + (repo / "manifest.json").read_text(errors="ignore")
    secret = re.search(r'(api_?key|token|secret)\s*[=:]\s*["\'][A-Za-z0-9_\-]{24,}["\']', blob, re.I)
    # DEMO_KEY and test_/example_ are allowed
    secret_bad = bool(secret) and not re.search(r'DEMO_KEY|test_|example_|your[-_]', secret.group(0), re.I)
    add("No hardcoded API key/secret committed", not secret_bad,
        "none found" if not secret_bad else f"suspicious: {secret.group(0)[:60]}")

    # Eval-specific
    if "nasa" in eval_name:
        props = ((manifest or {}).get("settings_schema", {}).get("properties", {}))
        has_pw = any(v.get("ui:widget") == "password" for v in props.values())
        has_env = bool((manifest or {}).get("env_vars"))
        add("API key via password widget AND env_var", has_pw and has_env,
            f"password_widget={has_pw} env_vars={has_env}")
    if "facts" in eval_name:
        # Board-safety: check string LITERALS in code (excluding docstrings/comments,
        # where stylistic unicode like em-dashes is harmless and never reaches the board).
        code = re.sub(r'""".*?"""', "", entry_txt, flags=re.S)
        code = re.sub(r"'''.*?'''", "", code, flags=re.S)
        code = re.sub(r"#.*", "", code)
        lits = re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'', code)
        flat = "".join(a or b for a, b in lits)
        bad = re.search(r"[^\x00-\x7f]", flat)
        add("Board output strings are ASCII (board-safe, no unicode)", not bad,
            "ASCII only in code string literals" if not bad else f"non-ASCII in a string literal: {bad.group(0)!r}")

    # The big one: real test run
    if plugin_id:
        t = run_tests(repo, plugin_id)
        add("Tests pass in the dev container", t["ok"], t["evidence"])
    else:
        add("Tests pass in the dev container", False, "no plugin id to test")

    return finalize(exp)


def finalize(exp: list) -> dict:
    passed = sum(1 for e in exp if e["passed"])
    total = len(exp)
    return {
        "summary": {"pass_rate": round(passed / total, 4) if total else 0.0,
                    "passed": passed, "failed": total - passed, "total": total},
        "expectations": exp,
    }


def main():
    iteration = Path(sys.argv[1]).resolve()
    ensure_pytest()
    for eval_dir in sorted(iteration.glob("eval-*")):
        for cfg in ("with_skill", "without_skill"):
            for run_dir in sorted((eval_dir / cfg).glob("run-*")):
                print(f"grading {eval_dir.name}/{cfg}/{run_dir.name} ...")
                grading = grade_run(run_dir, eval_dir.name)
                (run_dir / "grading.json").write_text(json.dumps(grading, indent=2))
                s = grading["summary"]
                print(f"  -> {s['passed']}/{s['total']} assertions  (pass_rate {s['pass_rate']})")


if __name__ == "__main__":
    main()
