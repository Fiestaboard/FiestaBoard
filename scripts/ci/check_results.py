"""Fail closed on job failures and the preflight checks sharing a runner.

Read Actions' toJSON(needs) from stdin. Preflight steps use continue-on-error
so their failures do not suppress the test fleet; their raw outcomes must
therefore be checked here before CI Success can pass.
"""

import json
import os
import sys
from pathlib import Path


def main() -> int:
    needs = json.load(sys.stdin)
    rows = [(name, job.get("result", "missing")) for name, job in needs.items()]
    failed = [name for name, result in rows if result not in ("success", "skipped")]
    preflight = needs.get("detect-changes", {}).get("outputs", {})
    for name, output, allowed in (
        ("check-image-formats", "image_formats_result", ("success",)),
        ("build", "structure_result", ("success", "skipped")),
    ):
        result = preflight.get(output, "missing")
        rows.append((name, result))
        if result not in allowed:
            failed.append(name)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        icons = {"success": "✅", "skipped": "⏭️", "failure": "❌", "cancelled": "🚫"}
        with Path(summary).open("a") as out:
            out.write("## CI job results\n\n| Check | Result |\n|---|---|\n")
            for name, result in rows:
                out.write(f"| {name} | {icons.get(result, '❓')} {result} |\n")
    if failed:
        print(f"::error::Failed, cancelled, or missing checks: {', '.join(failed)}")
        return 1
    print("All CI checks passed or were intentionally skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
