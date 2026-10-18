"""Refuse destructive content deletion while saved consumers still reference it."""


class ContentInUseError(ValueError):
    """A saved reference must be removed before deleting content."""


def check_content_references(ref_id: str, *, replace_active: bool = False) -> None:
    """Check all boards, including disabled schedules and silence settings."""
    from src.collections.service import get_collection_service
    from src.config_manager import get_config_manager
    from src.schedules.service import get_schedule_service
    from src.settings.service import get_settings_service

    settings = get_settings_service()
    boards = settings.get_board_settings().boards
    references = []
    if not replace_active:
        for board_id in [None, *(b["id"] for b in boards)]:
            if settings.get_active_page_id(board_id) == ref_id:
                references.append(f"active selection for board {board_id or 'primary'}")
    schedules = get_schedule_service().storage
    for entry in schedules.list_all(board_id="*"):
        if entry.page_id == ref_id:
            references.append(f"schedule {entry.id} (board {entry.board_id})")
    for board_id in [None, *(b["id"] for b in boards)]:
        if schedules.get_default_page_id(board_id) == ref_id:
            references.append(f"schedule default for board {board_id or 'primary'}")
    for collection in get_collection_service().list_collections():
        variable = collection.variable
        if ref_id in collection.page_ids or (
            variable and (variable.default_page_id == ref_id or any(rule.page_id == ref_id for rule in variable.rules))
        ):
            references.append(f"collection {collection.id} ({collection.name})")
    silence = get_config_manager().get_feature("silence_schedule")
    for board_id, config in [("default", silence), *(silence.get("by_board") or {}).items()]:
        if config.get("page_id") == ref_id:
            references.append(f"silence settings for board {board_id}")
    override = settings.peek_temporary_override()
    if override and ref_id in (override.page_id, override.revert_page_id):
        references.append("temporary override (page or revert page)")
    if references:
        raise ContentInUseError(
            f"Cannot delete {ref_id}; remove or change these references first: " + "; ".join(references)
        )
