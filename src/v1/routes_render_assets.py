"""Versioned fonts and built-in character sets for native renderers (H14)."""

from typing import Annotated

from fastapi import Header, Response

from src.api_errors import errors

from .render_assets import RenderAssets, matches_if_none_match, render_asset_snapshot
from .router import router

_CACHE_CONTROL = "private, no-cache"
_CACHE_HEADERS = {
    "ETag": {"schema": {"type": "string"}, "description": "Quoted SHA-256 of the exact catalog response bytes."},
    "Cache-Control": {
        "schema": {"type": "string"},
        "description": "private, no-cache: store privately; revalidate before reuse.",
    },
}


@router.get(
    "/render-assets",
    response_model=RenderAssets,
    response_model_exclude_none=True,
    responses={
        **errors(401, 403, 503),
        200: {"headers": _CACHE_HEADERS},
        304: {"description": "The cached catalog is current; no response body.", "headers": _CACHE_HEADERS},
    },
    summary="Read the native renderer's fonts and character sets",
    description=(
        "One atomic snapshot of the hub's vendored built-in LED fonts and flattened character sets. "
        "The nested documents retain FiestaUI's field names and bitmap rows ('#' lit, '.' unlit). "
        "`schema_version` versions this envelope; `revision` identifies its font and charset content; "
        "`source` names the upstream release. Custom plugin character sets are not included. "
        "Cache the response privately and send its ETag in `If-None-Match` to revalidate: a matching "
        "validator (including weak tags, lists or '*') returns an empty 304 with the same cache headers. "
        "Authentication is checked before revalidation. Mobile control credentials, browser sessions and "
        "configured API tokens use the existing v1 access rules; TV credentials do not gain access."
    ),
)
def get_render_assets(
    if_none_match: Annotated[
        list[str] | None,
        Header(description="Cached ETag(s), comma-separated or repeated; weak tags and '*' are accepted."),
    ] = None,
) -> Response:
    body, etag = render_asset_snapshot()
    headers = {"ETag": etag, "Cache-Control": _CACHE_CONTROL}
    if matches_if_none_match(if_none_match, etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
