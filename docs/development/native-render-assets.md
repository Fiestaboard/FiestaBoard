---
description: Versioned LED font and character-set data, conditional caching, and authentication for native renderers.
---

# Render assets for native clients

`GET /v1/render-assets` returns the hub's built-in FiestaUI LED fonts and
character sets in one versioned JSON document. The normal external path is
`GET /api/v1/render-assets`; preserve any deployment base prefix before `/api`.
The response supplies rendering data for iOS and Android consumers. Native
client downloading, persistence, and renderer integration remain separate work.

## Response contract

A successful `200` response has content type `application/json` and these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`, identifying this envelope and asset contract. |
| `revision` | SHA-256 of the canonical JSON object containing the `fonts` and `character_sets` maps. Treat it as an opaque content identifier. |
| `source` | Object containing exactly `source`, `commit`, and `version`, copied from the vendored FiestaUI provenance. |
| `fonts` | Map of font IDs to complete vendored face definitions. |
| `character_sets` | Map of built-in charset IDs to complete vendored character-set definitions. |

The data comes from `src/fiestaui/led-fonts.json` and
`src/fiestaui/character-sets.json`; source metadata comes from
`src/fiestaui/provenance.json`. Inner field names, Unicode content, and omitted
optional fields retain the vendored representation. Optional fields are not
filled with `null` or inferred defaults.

These identifiers have different roles. `schema_version` selects the decoder;
`revision` identifies the two asset maps; `source.version` names the upstream
FiestaUI release. Individual character sets also carry their own integer
`version`. The HTTP `ETag` identifies the entire serialized response, including
source metadata, so it can change even when `revision` stays the same. Neither
hash implies ordering or a minimum supported hub release.

## Font and character-set semantics

The built-in fonts are `3x5` and `5x7`. Each face contains `glyphWidth`,
`glyphHeight`, `spacingX`, `spacingY`, `glyphs`, and `icons`. Dimensions describe
the glyph box; spacing describes blank pixels between adjacent glyphs and text
rows. `glyphs` maps a character to bitmap rows, and `icons` maps an icon name to
bitmap rows. Rows run top to bottom, with pixels left to right: `#` is lit and
`.` is unlit. Each bitmap has `glyphHeight` rows of `glyphWidth` characters.
Glyph and icon availability is specific to the selected face.

The built-in character sets are `vestaboard_v1`, `vestaboard_v2`, `led_3x5`, and
`led_5x7`. Their definitions contain `id`, `label`, `version`, `chars`, `tiles`,
`icons`, `mixedCase`, `colorSpans`, and `blockSpans`, with optional `extends`,
`font`, `code62Glyph`, and `glyphs`. The built-ins are already flattened;
retained `extends` fields do not require clients to merge their arrays again.
`chars` lists supported printable code points with case preserved. Blank is
implicit. `icons` lists supported icon names; the boolean fields describe tile,
mixed-case, foreground-color-span, and background-block support. `font` selects
the LED face, and `code62Glyph` distinguishes degree and heart flaps.

This endpoint contains built-ins only. A board's custom plugin charset ID may
be absent, and this document does not resolve plugin definitions or their
inheritance. It also does not carry the markup icon registry, device models,
or rendering algorithms. Do not silently substitute a different font or
character set when the requested asset is unavailable.

Existing fallback behavior still applies within a supported renderer. In
`src/led/matrix.py`, a supplied charset glyph overrides the face glyph; a missing
character bitmap draws no foreground pixels. An icon missing from the face
uses its existing markup-registry fallback, which may be a color tile, a
character, or no glyph. The charset normalization step in `src/led/charsets.py`
separately checks supported characters, tries uppercase and the degree/heart
swap, then blank; it also removes unsupported spans and tiles. Consumers must
preserve the applicable renderer pipeline rather than infer replacement glyphs
from this asset response. Native rasterizers already use the same face data;
this endpoint does not supply a new fallback registry.

## Authentication and conditional requests

The endpoint uses the existing `/v1` authentication boundary. Mobile Bearer
credentials with the `control` scope, authenticated browser sessions, and a
configured API token can read it. TV credentials with the `tv_panels` scope
remain denied. Authentication-disabled installations retain the existing open
API behavior. See [native-client-authentication.md](native-client-authentication.md)
for session and deployment context.

Every successful `200` response carries:

```http
ETag: "<sha256-of-exact-response-bytes>"
Cache-Control: private, no-cache
```

The quoted SHA-256 ETag is a strong validator of the exact UTF-8 response bytes.
`private` permits storage in a client cache; `no-cache` requires revalidation
before reuse. Store the returned validator verbatim instead of constructing it
from `revision` or reserializing the JSON.

On a later GET, send that value in `If-None-Match`. An exact match, weak match
(`W/"..."`), matching member of a comma-separated list, or wildcard `*` returns
`304 Not Modified` with an empty body and the same ETag and cache policy. Values
across repeated `If-None-Match` headers are considered together. A stale or
nonmatching validator returns `200` with the full current document. Authentication
and scope checks run before conditional handling: a matching ETag never grants
access to an unauthenticated or disallowed caller.

## Client cache lifecycle

1. Isolate stored documents and validators by the hub's complete base URL,
   including deployment prefix, and the authenticated credential context. Use
   a local account/session identifier for isolation; do not put credential
   secrets in cache keys or logs. Invalidate that association on sign-out,
   revocation, or connection changes.
2. Fetch the document with the selected hub's credential. Use `If-None-Match`
   only when that same cache entry contains a complete, previously validated
   document. Avoid `*` for an empty cache: a `304` cannot populate it.
3. On `200`, validate `schema_version`, required fields, selected asset IDs,
   and bitmap dimensions before atomically storing the document with its ETag.
   An unsupported schema version or asset format must not be rendered as a
   known version. New content hashes are not themselves unsupported formats;
   source release metadata does not replace schema validation.
4. On `304`, retain the validated body and refresh its response metadata. If
   the body is missing or invalid, fetch again without a conditional header;
   do not decode the empty `304` body as JSON.
5. On authentication failure, stop using that credential's cached entry for
   authenticated requests. A network failure does not establish that the
   cached revision is current. Any offline rendering policy must remain an
   explicit client behavior, rather than treating this endpoint's cache
   headers as permission to skip revalidation.

## Recorded contract evidence

`tests/fixtures/render-assets-v1/` holds recorded response bodies and a
`SOURCE.json` manifest. `scripts/record_render_assets.py` records the actual
API boundary and binds the resulting bodies to source provenance, requests,
statuses, headers, and hashes. The records cover the complete asset response,
conditional caching, and authentication boundaries; an empty `304` body is
preserved as empty bytes. Credentials must not appear in recorded artifacts.

Contract checks compare asset values with the vendored source and validate
response shape, validators, cache policy, conditional-request behavior, and
authorized versus denied access. These records establish the server contract;
they do not establish native client wiring, physical-display parity, deployment,
or Docker execution. Vendored source integrity and rendering parity retain
their existing dedicated tests and golden fixtures.
