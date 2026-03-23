#!/usr/bin/env python3
"""Scan plugin registry repositories for security vulnerabilities.

This script clones each plugin listed in plugin-registry.json and runs:
1. Bandit (Python SAST) for code-level security issues (medium+ severity)
2. pip-audit for known dependency vulnerabilities (when requirements.txt exists)

Usage:
    python scripts/scan_registry.py [OPTIONS]

Options:
    --verbose       Show detailed output
    --output=DIR    Directory for scan results (default: scan-results)

Exit codes:
    0 - No vulnerabilities found
    1 - Vulnerabilities found
    2 - Configuration/setup error
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Project paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
REGISTRY_FILE = PROJECT_ROOT / "plugin-registry.json"


class PluginScanResult:
    """Result of scanning a single plugin repository."""

    def __init__(self, plugin_id: str, name: str, repository: str):
        self.plugin_id = plugin_id
        self.name = name
        self.repository = repository
        self.bandit_findings: List[Dict] = []
        self.dependency_findings: List[Dict] = []
        self.clone_error: Optional[str] = None

    @property
    def has_findings(self) -> bool:
        return bool(self.bandit_findings or self.dependency_findings)

    @property
    def has_errors(self) -> bool:
        return self.clone_error is not None


def load_registry() -> List[Dict]:
    """Load plugin registry and return list of plugin entries."""
    if not REGISTRY_FILE.exists():
        print(f"Error: Registry file not found: {REGISTRY_FILE}")
        sys.exit(2)

    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in registry file: {exc}")
        sys.exit(2)

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        print("Error: Registry 'plugins' field must be an array")
        sys.exit(2)

    return plugins


def clone_repo(repo_url: str, target_dir: str, verbose: bool) -> Optional[str]:
    """Shallow-clone a repository. Returns error message or None on success."""
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", f"{repo_url}.git", target_dir],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            return f"git clone failed: {result.stderr.strip()}"
        if verbose:
            print("  Cloned successfully")
        return None
    except subprocess.TimeoutExpired:
        return "git clone timed out (120s)"
    except Exception as exc:
        return f"git clone error: {exc}"


def run_bandit(plugin_dir: str, verbose: bool) -> List[Dict]:
    """Run bandit SAST scan on a plugin directory.

    Uses ``-ll`` to report only medium-severity and above findings.
    Returns a list of finding dicts.
    """
    findings: List[Dict] = []
    try:
        result = subprocess.run(
            ["bandit", "-r", plugin_dir, "-f", "json", "-q", "-ll"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout
        if output:
            try:
                data = json.loads(output)
                for entry in data.get("results", []):
                    filename = entry.get("filename", "")
                    if plugin_dir in filename:
                        filename = filename[len(plugin_dir) :].lstrip("/\\")
                    findings.append(
                        {
                            "severity": entry.get("issue_severity", "UNKNOWN"),
                            "confidence": entry.get("issue_confidence", "UNKNOWN"),
                            "text": entry.get("issue_text", ""),
                            "file": filename,
                            "line": entry.get("line_number", 0),
                            "test_id": entry.get("test_id", ""),
                        }
                    )
            except json.JSONDecodeError:
                if verbose:
                    print("  Warning: bandit produced non-JSON output")
    except subprocess.TimeoutExpired:
        if verbose:
            print("  Warning: bandit scan timed out")
    except FileNotFoundError:
        print("Error: bandit not found. Install with: pip install bandit")
        sys.exit(2)

    return findings


def run_pip_audit(requirements_path: str, verbose: bool) -> List[Dict]:
    """Run pip-audit against a requirements file.

    Returns a list of finding dicts for each known vulnerability.
    """
    findings: List[Dict] = []
    try:
        result = subprocess.run(
            [
                "pip-audit",
                "-r",
                requirements_path,
                "--format",
                "json",
                "--desc",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout
        if output:
            try:
                data = json.loads(output)
                for dep in data:
                    for vuln in dep.get("vulns", []):
                        findings.append(
                            {
                                "package": dep.get("name", ""),
                                "version": dep.get("version", ""),
                                "vuln_id": vuln.get("id", ""),
                                "fix_versions": vuln.get("fix_versions", []),
                                "description": (
                                    vuln.get("description", "See advisory")[:200]
                                ),
                            }
                        )
            except json.JSONDecodeError:
                if verbose:
                    print(
                        f"  Warning: pip-audit produced non-JSON output "
                        f"for {requirements_path}"
                    )
    except subprocess.TimeoutExpired:
        if verbose:
            print(f"  Warning: pip-audit timed out for {requirements_path}")
    except FileNotFoundError:
        print("Error: pip-audit not found. Install with: pip install pip-audit")
        sys.exit(2)

    return findings


def scan_plugin(entry: Dict, workspace: str, verbose: bool) -> PluginScanResult:
    """Clone and scan a single plugin repository."""
    plugin_id = entry.get("id", "unknown")
    name = entry.get("name", plugin_id)
    repo_url = entry.get("repository", "")

    result = PluginScanResult(plugin_id, name, repo_url)
    plugin_dir = os.path.join(workspace, plugin_id)

    # Clone
    clone_error = clone_repo(repo_url, plugin_dir, verbose)
    if clone_error:
        result.clone_error = clone_error
        return result

    # Bandit SAST scan
    if verbose:
        print("  Running bandit scan...")
    result.bandit_findings = run_bandit(plugin_dir, verbose)
    if verbose:
        print(f"  Bandit: {len(result.bandit_findings)} finding(s)")

    # pip-audit dependency scan (only when requirements.txt exists)
    req_file = os.path.join(plugin_dir, "requirements.txt")
    if os.path.exists(req_file):
        if verbose:
            print("  Running pip-audit...")
        result.dependency_findings = run_pip_audit(req_file, verbose)
        if verbose:
            print(f"  pip-audit: {len(result.dependency_findings)} finding(s)")
    elif verbose:
        print("  No requirements.txt found, skipping pip-audit")

    return result


def generate_report(results: List[PluginScanResult]) -> str:
    """Generate a markdown report from scan results."""
    scan_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        "# Plugin Registry Security Scan Results",
        "",
        f"**Scan date:** {scan_date}",
        f"**Plugins scanned:** {len(results)}",
        "",
    ]

    plugins_with_findings = [r for r in results if r.has_findings]
    plugins_with_errors = [r for r in results if r.has_errors]
    plugins_clean = [
        r for r in results if not r.has_findings and not r.has_errors
    ]

    total_bandit = sum(len(r.bandit_findings) for r in results)
    total_deps = sum(len(r.dependency_findings) for r in results)

    lines.extend(
        [
            f"**Plugins with findings:** {len(plugins_with_findings)}",
            f"**Plugins clean:** {len(plugins_clean)}",
            f"**Plugins with errors:** {len(plugins_with_errors)}",
            f"**Total code findings (bandit):** {total_bandit}",
            f"**Total dependency vulnerabilities (pip-audit):** {total_deps}",
            "",
            "---",
            "",
        ]
    )

    # Plugins with findings first
    for result in results:
        if not result.has_findings and not result.has_errors:
            continue

        if result.clone_error:
            lines.append(f"## ❌ {result.name} (`{result.plugin_id}`)")
            lines.append("")
            lines.append(f"Repository: {result.repository}")
            lines.append(f"Clone error: {result.clone_error}")
            lines.append("")
            continue

        lines.append(f"## ⚠️ {result.name} (`{result.plugin_id}`)")
        lines.append("")
        lines.append(f"Repository: {result.repository}")
        lines.append("")

        if result.bandit_findings:
            lines.append("### Static Analysis (Bandit)")
            lines.append("")
            for finding in result.bandit_findings:
                lines.append(
                    f"- **[{finding['severity']}/{finding['confidence']}]** "
                    f"{finding['text']} "
                    f"(`{finding['file']}:{finding['line']}`)"
                )
            lines.append("")

        if result.dependency_findings:
            lines.append("### Dependency Vulnerabilities (pip-audit)")
            lines.append("")
            for finding in result.dependency_findings:
                fix = (
                    ", ".join(finding["fix_versions"])
                    if finding.get("fix_versions")
                    else "No fix available"
                )
                lines.append(
                    f"- **{finding['package']}=={finding['version']}**: "
                    f"{finding['vuln_id']} (fix: {fix})"
                )
            lines.append("")

    # Clean plugins
    if plugins_clean:
        lines.append("## ✅ Clean Plugins")
        lines.append("")
        for result in plugins_clean:
            lines.append(f"- {result.name} (`{result.plugin_id}`)")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scan FiestaBoard plugin registry repositories for vulnerabilities"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed output",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="scan-results",
        help="Output directory for scan results (default: scan-results)",
    )

    args = parser.parse_args()

    print("FiestaBoard Plugin Registry Security Scanner")
    print("=" * 50)
    print()

    # Load registry
    plugins = load_registry()
    print(f"Found {len(plugins)} plugins in registry")
    print()

    # Prepare directories
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace = tempfile.mkdtemp(prefix="fiestaboard-scan-")

    try:
        # Scan each plugin
        results: List[PluginScanResult] = []
        for i, entry in enumerate(plugins, 1):
            plugin_id = entry.get("id", "unknown")
            name = entry.get("name", plugin_id)
            print(f"[{i}/{len(plugins)}] Scanning: {name} ({plugin_id})")

            result = scan_plugin(entry, workspace, args.verbose)
            results.append(result)

            if result.clone_error:
                print(f"  ❌ Clone failed: {result.clone_error}")
            elif result.has_findings:
                total = len(result.bandit_findings) + len(
                    result.dependency_findings
                )
                print(f"  ⚠️  {total} finding(s)")
            else:
                print("  ✅ Clean")

        print()

        # Generate report
        report = generate_report(results)
        report_path = output_dir / "scan-report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report written to: {report_path}")

        # Summary
        print()
        print("=" * 50)
        print("SCAN SUMMARY")
        print("=" * 50)

        has_vulnerabilities = any(r.has_findings for r in results)
        plugins_with_findings = sum(1 for r in results if r.has_findings)
        total_findings = sum(
            len(r.bandit_findings) + len(r.dependency_findings)
            for r in results
        )

        print(f"Plugins scanned: {len(results)}")
        print(f"Plugins with findings: {plugins_with_findings}")
        print(f"Total findings: {total_findings}")
        print()

        # Set GitHub Actions outputs when running in CI
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(
                    f"has_vulnerabilities="
                    f"{'true' if has_vulnerabilities else 'false'}\n"
                )
                f.write(f"plugin_count={len(results)}\n")
                f.write(f"finding_count={total_findings}\n")

        # Write job summary when running in CI
        github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if github_summary:
            with open(github_summary, "a", encoding="utf-8") as f:
                f.write(report)

        if has_vulnerabilities:
            print("VULNERABILITIES FOUND")
            sys.exit(1)
        else:
            print("NO VULNERABILITIES FOUND")
            sys.exit(0)

    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
