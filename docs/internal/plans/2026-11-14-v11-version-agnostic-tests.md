# Version-independent update test scenarios

Goal: make the historical stable/beta suites pass after the v11 version bump without weakening runtime isolation.

Architecture: pin the package version at the update-service seam in historical scenario fixtures; retain explicit beta VERSION inputs and all v11 guards. A subprocess regression sets src.__version__ to 11.0.0-alpha.0 before collecting the historical suites and v11 release guarantees.

- [ ] Reproduce the CI failures with a temporary package version bump; restore it afterward.
- [ ] Add the subprocess regression and observe failure before fixture repairs.
- [ ] Pin scenario versions locally, with no global conftest override; run channel/API/MCP/golden suites and v11 guards.
- [ ] Add patch changeset; run lint/format and full pytest at committed and temporary v11 versions, restoring the source bump.
- [ ] Open PR into v11, obtain Astra review (up to three rounds), fix findings, push normally and observe CI.
- [ ] Record exact checks/head/review and remaining gates in program status and ownership row. Never merge.
