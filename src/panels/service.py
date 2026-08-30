"""Service layer for FiestaPanel panels.

Storage-pure CRUD; virtual-board co-creation/deletion is orchestrated by
the API routes (matching how /settings/board/add orchestrates inline).
"""

import logging

from .models import Panel, PanelCreate, PanelUpdate
from .storage import PanelStorage

logger = logging.getLogger(__name__)


class PanelService:
    """CRUD over panel storage."""

    def __init__(self, storage: PanelStorage | None = None):
        self.storage = storage or PanelStorage()

    def list_panels(self) -> list[Panel]:
        return self.storage.list_all()

    def get_panel(self, panel_id: str) -> Panel | None:
        return self.storage.get(panel_id)

    def get_panel_by_ref(self, ref: str) -> Panel | None:
        """Resolve a viewer URL reference.

        "display" resolves the panel designated as the local display (the
        FiestaPi HDMI kiosk's stable URL); a short all-digit string is a
        short code; anything else is a panel id. Random slug ids are 12+
        chars of base64url, so the reserved words and codes cannot collide.
        """
        if ref == "display":
            return self.storage.get_display_panel()
        # isdecimal(), not isdigit(): isdigit() accepts superscripts and other
        # non-decimal digit characters that int() then raises on — and this
        # runs on the unauthenticated viewer path, where "²" must 404, not 500.
        if ref.isdecimal() and len(ref) <= 6:
            return self.storage.get_by_short_code(int(ref))
        return self.storage.get(ref)

    def create_panel(self, data: PanelCreate, board_id: str) -> Panel:
        """Create a panel bound to an (already created) virtual board."""
        panel = Panel(
            name=data.name,
            board_id=board_id,
            screen_diagonal_inches=data.screen_diagonal_inches,
            screen_aspect_w=data.screen_aspect_w,
            screen_aspect_h=data.screen_aspect_h,
        )
        return self.storage.create(panel)

    def update_panel(self, panel_id: str, data: PanelUpdate) -> Panel | None:
        """Apply only the fields the caller actually set (exclude_unset).

        Designating a panel as the local display clears the role from any
        other holder first — exactly one panel may serve /p/display.
        """
        updates = data.model_dump(exclude_unset=True)
        if updates.get("is_display"):
            # Confirm the target exists BEFORE demoting the current holder:
            # a 404-ing request (stale tab, deleted panel) must not blank the
            # /p/display kiosk by clearing the role and then failing.
            if self.storage.get(panel_id) is None:
                return None
            current = self.storage.get_display_panel()
            if current is not None and current.id != panel_id:
                self.storage.update(current.id, {"is_display": False})
        return self.storage.update(panel_id, updates)

    def delete_panel(self, panel_id: str) -> Panel | None:
        """Delete a panel, returning it (routes need board_id for cleanup)."""
        panel = self.storage.get(panel_id)
        if panel is None:
            return None
        self.storage.delete(panel_id)
        return panel


_panel_service: PanelService | None = None


def get_panel_service() -> PanelService:
    """Module-level singleton, mirroring get_page_service()."""
    global _panel_service
    if _panel_service is None:
        _panel_service = PanelService()
    return _panel_service
