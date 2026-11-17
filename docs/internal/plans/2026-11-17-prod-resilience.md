# Production resilience fixture preparation

The published-image recovery gate needs reproducible boundaries between a
synthetic board accepting a frame and the hub receiving a response. The existing
integration mock has no such controls. A separate fixture keeps existing mock
callers unchanged and records acceptance independently of the hub process.

## Scope

`integration-tests/resilience/fixtures.py` provides a loopback receiver with
before-accept and after-accept barriers, a one-request offline fault, a bounded
append-only receipt journal, and a direct-child process owner. These are test
utilities, with no application imports or product behavior changes. They do not
implement the eight production scenarios or certify recovery.

The receiver uses one request thread, finite socket and barrier deadlines,
bounded payloads and journal length, and exclusive evidence files. Controls are
Python methods rather than network endpoints. A barrier timeout fails closed;
the journal distinguishes received, accepted and response-written events. A
successful socket write is not proof that the client received an acknowledgement.
The journal is held outside the process being interrupted.

The process helper owns only the direct foreground child it launches. It uses
argument arrays, no shell, exclusive output logs, a finite terminate interval,
then kill and reap. It does not own arbitrary descendants or supervisord's
children. A future stock-image runner must address those separately using the
reserved hub lifecycle; this helper must never be used to kill shared processes.

## Validation before use

The contract tests were authored before implementation during serialized PROD
contention. They have not yet run. Do not interpret source review as observed
red/green test-first proof. In the exclusively reserved Python role, with the
verified task mount as `/work`, run:

```sh
docker exec -w /work fb-dev-py timeout --signal=TERM --kill-after=5s 120s \
  python -m pytest integration-tests/test_resilience_fixtures.py -q
```

Use the test-only commit to observe the baseline failure, then demonstrate
behavioral mutations: accept before releasing the first barrier; acknowledge
before releasing the second; omit kill after a child ignores termination; and
overwrite an existing evidence file. Require each relevant test to fail for its
intended reason, then restore the fixture and require passing results. Missing
imports alone do not establish meaningful red/green proof.

The API path filter includes `integration-tests/**`, so fixture-only changes
trigger the existing Platform Tests step that collects that directory. A guard
in `tests/test_ci_path_filters.py` covers this routing.

Run the full applicable Python checks, integration mock suite, Ruff check and
format, and API reference check before proposing a merge-ready PR. One heavy
process per job; pytest at most two workers. Never run these tests or their
fixture servers on the host, create a fourth container, or use another job's
mount or running process.

## Remaining production gate

Run restart mid-send, board offline/reconnect, plugin hang, disk full, clock
skew/DST, HA ingress, corrupt settings and backup restore serially against a
refreshed immutable published-image pin. Record index/platform/config/running
image IDs, source and fixture hashes, commands, timing budgets, expected and
actual results, and cleanup. Reproduce defects before product fixes. Injected
tests, published-image simulations, physical boards and real HA evidence remain
distinct. In particular, these fixtures establish neither exactly-once physical
delivery, power-loss durability nor Supervisor authentication.
