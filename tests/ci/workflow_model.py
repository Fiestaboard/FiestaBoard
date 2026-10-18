"""Evaluate the small status-expression subset used by our CI jobs."""

import re


def run_steps(job, failed_step=None, cancelled=False):
    """Evaluate this job's status/outcome expressions with controlled outcomes.

    This deliberately only models our simple conditions, not arbitrary Actions
    expressions. Unknown syntax fails the test instead of assuming reachability.
    """
    outcomes = {}
    failed = False
    ran = []
    for index, step in enumerate(job["steps"]):
        expression = str(step.get("if", "success()"))
        expression = expression.removeprefix("${{").removesuffix("}}").strip()
        # Login's event/actor guard is covered by its existing workflow condition;
        # use an internal PR here, for which login is required.
        if step.get("uses", "").startswith("docker/login-action"):
            expression = "success()"
        expression = re.sub(r"steps\.([\w-]+)\.outcome", lambda m: repr(outcomes.get(m[1], "skipped")), expression)
        for token, value in {
            "success()": not failed and not cancelled,
            "failure()": failed,
            "always()": True,
            "cancelled()": cancelled,
        }.items():
            expression = expression.replace(token, str(value))
        expression = expression.replace("&&", " and ").replace("||", " or ")
        expression = re.sub(r"!(?!=)", " not ", expression).strip()
        admitted = eval(expression, {"__builtins__": {}}, {})  # trusted repository YAML only
        identifier = step.get("id", step.get("name", f"step-{index}"))
        outcome = "skipped"
        if admitted:
            ran.append(identifier)
            outcome = "failure" if identifier == failed_step else "success"
            if outcome == "failure" and not step.get("continue-on-error", False):
                failed = True
        outcomes[identifier] = outcome
    return ran, failed
