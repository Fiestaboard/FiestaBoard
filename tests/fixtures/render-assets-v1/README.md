# Native render-asset response fixtures

These are raw response bodies captured through FastAPI TestClient against the
real app, authentication middleware, synthetic mobile/TV sessions, and vendored
FiestaUI assets. No handler response is mocked. They prove the API contract,
not a deployed reverse proxy or native renderer integration.

- `ios-catalog.json` and `android-catalog.json`: authenticated `200` catalogs.
- `not-modified.body`: the zero-byte `304` response to a matching ETag.
- `unauthenticated.json`: `401`, even with a matching conditional header.
- `tv-forbidden.json`: `403`; TV scope was not expanded.

`SOURCE.json` records the immutable hub source commit, source-file SHA-256 values,
request method/path and credential kind (never a token), relevant request and
response headers, status, and exact body SHA-256. JSON bodies are not reformatted:
ETag and body hashes describe the exact recorded bytes, including Unicode.

Regenerate inside the shared Python container after committing any source changes:

```sh
python scripts/record_render_assets.py --source-commit <full-hub-commit-sha>
```

Then run `pytest tests/test_render_assets_contract.py` without recording enabled.
Review both the manifest and body changes. Commit the fixtures separately so the
manifest's source commit already exists and can be inspected by native clients.
