"""Shared labels for the Active Page select's collection targets."""

import logging

logger = logging.getLogger(__name__)


def collection_options(pages) -> list[tuple[str, str]]:
    """Return (label, collection id) pairs, preserving ordinary page names.

    A collection's prefix distinguishes it from a page with the same name.
    Include its stable id when even that label collides with another target.
    Discovery, commands and state use this same mapping.
    """
    from src.collections.service import get_collection_service

    try:
        collections = get_collection_service().list_collections()
        bases = [f"Collection: {collection.name}" for collection in collections]
        used = {page.name.lower() for page in pages}
        options = []
        for collection, base in zip(collections, bases, strict=True):
            label = base
            if label.lower() in used or sum(b.lower() == base.lower() for b in bases) > 1:
                label = f"{base} [{collection.id}]"
            while label.lower() in used:
                label = f"{label} [{collection.id}]"
            used.add(label.lower())
            options.append((label, collection.id))
        return options
    except Exception:
        logger.debug("Could not retrieve collections for MQTT", exc_info=True)
        return []


def content_name(ref_id: str, page_service) -> str | None:
    """The exact select option for a page or collection reference."""
    from src.collections.models import is_collection_id

    if is_collection_id(ref_id):
        return next((label for label, cid in collection_options(page_service.list_pages()) if cid == ref_id), None)
    page = page_service.get_page(ref_id)
    return page.name if page else None
