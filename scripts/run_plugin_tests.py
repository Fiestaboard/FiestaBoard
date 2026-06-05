#!/usr/bin/env python3
"""Plugin test runner with coverage enforcement.

This script discovers and runs tests for all FiestaBoard plugins,
enforcing minimum coverage requirements for each plugin.

Usage:
    python scripts/run_plugin_tests.py [OPTIONS]

Options:
    --fail-under=N      Minimum coverage percentage (default: 80)
    --plugin=ID         Run tests for specific plugin only
    --verbose           Show detailed output
    --dry-run           Show what would be run without executing
    --no-coverage       Run tests without coverage checking
    --report            Generate HTML coverage report

Exit codes:
    0 - All tests passed with sufficient coverage
    1 - Tests failed or coverage below threshold
    2 - No plugins found or configuration error
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Project paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PLUGINS_DIR = PROJECT_ROOT / "plugins"
COVERAGE_DIR = PROJECT_ROOT / "coverage"

# Default settings
DEFAULT_FAIL_UNDER = 80  # Minimum coverage percentage required
WARNING_THRESHOLD = 80  # Warn if coverage is below this percentage
SKIP_DIRECTORIES = {"_template", "__pycache__"}


class PluginTestResult:
    """Result of running tests for a single plugin."""

    def __init__(
        self,
        plugin_id: str,
        passed: bool,
        coverage: float,
        tests_run: int = 0,
        tests_failed: int = 0,
        error: str | None = None,
    ):
        self.plugin_id = plugin_id
        self.passed = passed
        self.coverage = coverage
        self.tests_run = tests_run
        self.tests_failed = tests_failed
        self.error = error

    @property
    def coverage_warning(self) -> bool:
        """Check if coverage is below warning threshold."""
        return self.coverage < WARNING_THRESHOLD

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        warning = " (!)" if self.coverage_warning else ""
        return f"{self.plugin_id}: {status} (coverage: {self.coverage:.1f}%){warning}"


def discover_plugins() -> list[Path]:
    """Discover all plugin directories with tests.

    Returns:
        List of paths to plugin directories that have tests/ subdirectory
    """
    plugins = []

    if not PLUGINS_DIR.exists():
        print(f"Warning: Plugins directory not found: {PLUGINS_DIR}")
        return plugins

    for item in PLUGINS_DIR.iterdir():
        if not item.is_dir():
            continue

        if item.name in SKIP_DIRECTORIES:
            continue

        # Check for tests directory
        tests_dir = item / "tests"
        if tests_dir.exists() and tests_dir.is_dir():
            # Check for actual test files
            test_files = list(tests_dir.glob("test_*.py"))
            if test_files:
                plugins.append(item)

    return sorted(plugins, key=lambda p: p.name)


def run_plugin_tests(plugin_dir: Path, verbose: bool = False) -> PluginTestResult:
    """Run tests for a single plugin with coverage.

    Args:
        plugin_dir: Path to the plugin directory
        fail_under: Minimum coverage percentage
        verbose: Show detailed output

    Returns:
        PluginTestResult with test and coverage information
    """
    plugin_id = plugin_dir.name
    tests_dir = plugin_dir / "tests"

    # Build coverage + pytest command
    # Use absolute path to plugin directory to ensure it works in CI
    plugin_abs_path = str(plugin_dir.resolve())
    coverage_file = PROJECT_ROOT / f".coverage.{plugin_id}"

    test_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "run",
        f"--data-file={coverage_file!s}",
        f"--source={plugin_abs_path}",  # Absolute path to plugin directory
        "-m",
        "pytest",
        str(tests_dir),
        "-v" if verbose else "-q",
    ]

    # Build coverage report command (no fail-under to allow tests to pass)
    report_cmd = [
        sys.executable,
        "-m",
        "coverage",
        "report",
        f"--data-file={coverage_file!s}",
        f"--include={plugin_abs_path}/*",  # Include only this plugin's files (absolute path)
        "--show-missing",  # Show which lines are missing for debugging
    ]

    try:
        # Run tests with coverage
        test_result = subprocess.run(test_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))

        # Check if coverage file was created
        if not coverage_file.exists():
            error_msg = f"Coverage data file not created: {coverage_file}"
            if verbose:
                print(f"[{plugin_id}] ERROR: {error_msg}", file=sys.stderr)
                print(f"[{plugin_id}] Test stdout:", test_result.stdout, file=sys.stderr)
                print(f"[{plugin_id}] Test stderr:", test_result.stderr, file=sys.stderr)
            return PluginTestResult(
                plugin_id=plugin_id,
                passed=False,
                coverage=0.0,
                tests_run=parse_test_results(test_result.stdout + test_result.stderr)[0],
                tests_failed=parse_test_results(test_result.stdout + test_result.stderr)[1],
                error=error_msg,
            )

        # Generate coverage report
        report_result = subprocess.run(report_cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))

        # Always show stderr if there are errors (helps debug CI issues)
        if report_result.returncode != 0 or verbose:
            if test_result.stderr:
                print(f"[{plugin_id}] Test stderr:", test_result.stderr, file=sys.stderr)
            if report_result.stderr:
                print(f"[{plugin_id}] Coverage stderr:", report_result.stderr, file=sys.stderr)
            if verbose:
                print(f"[{plugin_id}] Test stdout:", test_result.stdout)
                print(f"[{plugin_id}] Coverage stdout:", report_result.stdout)

        # Parse output for coverage percentage
        full_output = report_result.stdout + report_result.stderr
        coverage = parse_coverage_from_output(full_output)

        # If coverage parsing failed, try to get it from test output (pytest-cov format)
        if coverage == 0.0:
            coverage = parse_coverage_from_output(test_result.stdout + test_result.stderr)

        # Parse test results
        tests_run, tests_failed = parse_test_results(test_result.stdout + test_result.stderr)

        # Tests pass if pytest succeeded AND coverage meets threshold
        passed = test_result.returncode == 0 and coverage >= DEFAULT_FAIL_UNDER

        if coverage < DEFAULT_FAIL_UNDER:
            print(
                f"❌ FAIL: {plugin_id} coverage ({coverage:.1f}%) is below minimum threshold ({DEFAULT_FAIL_UNDER}%)",
                file=sys.stderr,
            )

        return PluginTestResult(
            plugin_id=plugin_id, passed=passed, coverage=coverage, tests_run=tests_run, tests_failed=tests_failed
        )

    except Exception as e:
        return PluginTestResult(plugin_id=plugin_id, passed=False, coverage=0.0, error=str(e))


def parse_coverage_from_output(output: str) -> float:
    """Parse coverage percentage from coverage report output.

    Args:
        output: Combined stdout/stderr from coverage report

    Returns:
        Coverage percentage (0-100)
    """
    import re

    # Look for TOTAL line with branch coverage: "TOTAL    stmts    miss    branch    brpart    cover%"
    # Format: TOTAL <stmts> <miss> <branch> <brpart> <cover>%
    total_pattern = r"TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%"
    match = re.search(total_pattern, output)
    if match:
        return float(match.group(1))

    # Fallback: Look for TOTAL line without branch coverage: "TOTAL    xxx    xxx    xx%"
    total_pattern_simple = r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)%"
    match = re.search(total_pattern_simple, output)
    if match:
        return float(match.group(1))

    # Alternative pattern: "Coverage: xx%"
    coverage_pattern = r"Coverage:\s*(\d+(?:\.\d+)?)%"
    match = re.search(coverage_pattern, output)
    if match:
        return float(match.group(1))

    return 0.0


def parse_test_results(output: str) -> tuple[int, int]:
    """Parse test count from pytest output.

    Args:
        output: Combined stdout/stderr from pytest

    Returns:
        Tuple of (tests_run, tests_failed)
    """
    import re

    # Pattern: "X passed" or "X passed, Y failed"
    passed_pattern = r"(\d+) passed"
    failed_pattern = r"(\d+) failed"

    passed_match = re.search(passed_pattern, output)
    failed_match = re.search(failed_pattern, output)

    passed = int(passed_match.group(1)) if passed_match else 0
    failed = int(failed_match.group(1)) if failed_match else 0

    return (passed + failed, failed)


def generate_coverage_report(results: list[PluginTestResult]) -> str:
    """Generate a summary report of plugin coverage.

    Args:
        results: List of plugin test results

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 60)
    lines.append("PLUGIN TEST COVERAGE REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Header
    lines.append(f"{'Plugin':<25} {'Tests':<10} {'Coverage':<12} {'Status':<10}")
    lines.append("-" * 60)

    all_passed = True
    total_tests = 0
    low_coverage_plugins = []

    for result in results:
        status = "PASS" if result.passed else "FAIL"
        if status == "FAIL":
            all_passed = False

        total_tests += result.tests_run

        coverage_str = f"{result.coverage:.1f}%"
        if result.coverage_warning:
            coverage_str += " (!)"
            low_coverage_plugins.append(result.plugin_id)

        lines.append(f"{result.plugin_id:<25} {result.tests_run:<10} {coverage_str:<12} {status:<10}")

        if result.error:
            lines.append(f"  Error: {result.error}")

    lines.append("-" * 60)

    # Summary
    passed_count = sum(1 for r in results if r.passed)
    lines.append(f"Total: {len(results)} plugins, {total_tests} tests")
    lines.append(f"Passed: {passed_count}/{len(results)} plugins")
    lines.append("")

    if all_passed:
        lines.append("All plugins passed tests.")
        if low_coverage_plugins:
            lines.append("")
            lines.append(f"⚠️  WARNING: {len(low_coverage_plugins)} plugin(s) have coverage below {WARNING_THRESHOLD}%:")
            lines.append(f"   {', '.join(low_coverage_plugins)}")
            lines.append("   See GitHub issue #64 for improvement plan.")
    else:
        lines.append("Some plugins failed tests.")
        if low_coverage_plugins:
            lines.append("")
            lines.append(f"⚠️  WARNING: {len(low_coverage_plugins)} plugin(s) have coverage below {WARNING_THRESHOLD}%:")
            lines.append(f"   {', '.join(low_coverage_plugins)}")
            lines.append("   See GitHub issue #64 for improvement plan.")

    lines.append("")
    lines.append("Plugins marked with (!) have coverage below warning threshold.")
    lines.append("=" * 60)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Run FiestaBoard plugin tests with coverage reporting")
    parser.add_argument("--plugin", type=str, help="Run tests for specific plugin only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be run without executing")
    parser.add_argument("--no-coverage", action="store_true", help="Run tests without coverage checking")
    parser.add_argument("--report", action="store_true", help="Generate HTML coverage report")

    args = parser.parse_args()

    print("FiestaBoard Plugin Test Runner")
    print(f"Coverage threshold: {DEFAULT_FAIL_UNDER}% (plugins must meet this to pass)")
    print()

    # Discover plugins
    plugins = discover_plugins()

    if args.plugin:
        # Filter to specific plugin
        plugins = [p for p in plugins if p.name == args.plugin]
        if not plugins:
            print(f"Error: Plugin '{args.plugin}' not found or has no tests")
            sys.exit(2)

    if not plugins:
        print("No plugins with tests found.")
        print(f"Plugins directory: {PLUGINS_DIR}")
        print("Ensure plugins have a tests/ directory with test_*.py files")
        sys.exit(2)

    print(f"Found {len(plugins)} plugin(s) with tests:")
    for p in plugins:
        test_count = len(list((p / "tests").glob("test_*.py")))
        print(f"  - {p.name} ({test_count} test file(s))")
    print()

    if args.dry_run:
        print("Dry run - no tests executed")
        sys.exit(0)

    # Run tests for each plugin
    results: list[PluginTestResult] = []

    for plugin_dir in plugins:
        print(f"Testing plugin: {plugin_dir.name}")
        print("-" * 40)

        if args.no_coverage:
            # Run without coverage
            cmd = [
                sys.executable,
                "-m",
                "pytest",
                str(plugin_dir / "tests"),
                "-v" if args.verbose else "-q",
            ]
            result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
            results.append(
                PluginTestResult(
                    plugin_id=plugin_dir.name,
                    passed=result.returncode == 0,
                    coverage=100.0,  # Skip coverage check
                )
            )
        else:
            result = run_plugin_tests(plugin_dir, verbose=args.verbose)
            results.append(result)

        print()

    # Generate report
    report = generate_coverage_report(results)
    print(report)

    # Generate HTML report if requested
    if args.report:
        COVERAGE_DIR.mkdir(exist_ok=True)
        report_path = COVERAGE_DIR / "plugin_coverage_report.txt"
        with open(report_path, "w") as f:
            f.write(report)
        print(f"\nReport saved to: {report_path}")

    # Determine exit code (only based on test results, not coverage)
    all_passed = all(r.passed for r in results)

    if all_passed:
        print("\nAll plugin tests passed.")
        sys.exit(0)
    else:
        failed_plugins = [r.plugin_id for r in results if not r.passed]
        print(f"\nFailed plugins: {', '.join(failed_plugins)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
