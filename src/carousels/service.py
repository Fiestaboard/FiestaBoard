"""Carousel service for CRUD operations and rotation logic."""

import logging
import math
import time
from typing import List, Optional
from datetime import datetime

from .models import Carousel, CarouselCreate, CarouselUpdate, is_carousel_id
from .storage import CarouselStorage

logger = logging.getLogger(__name__)


class CarouselService:
    """Service for carousel operations.

    Handles CRUD and provides helpers for resolving which page should
    currently be displayed for a given carousel.
    """

    def __init__(self, storage: Optional[CarouselStorage] = None):
        self.storage = storage or CarouselStorage()
        logger.info("CarouselService initialized")

    def list_carousels(self) -> List[Carousel]:
        return self.storage.list_all()

    def get_carousel(self, carousel_id: str) -> Optional[Carousel]:
        return self.storage.get(carousel_id)

    def create_carousel(self, data: CarouselCreate) -> Carousel:
        carousel = Carousel(
            name=data.name,
            page_ids=data.page_ids,
            interval_seconds=data.interval_seconds,
            created_at=datetime.utcnow(),
        )
        return self.storage.create(carousel)

    def update_carousel(self, carousel_id: str, data: CarouselUpdate) -> Optional[Carousel]:
        updates = data.model_dump(exclude_unset=True)
        return self.storage.update(carousel_id, updates)

    def delete_carousel(self, carousel_id: str) -> bool:
        return self.storage.delete(carousel_id)

    def resolve_page_id(self, ref_id: str, now_unix: Optional[float] = None) -> Optional[str]:
        """If *ref_id* is a carousel, return the page that should be shown now.

        If *ref_id* is a plain page ID, return it unchanged.
        Returns None if the carousel is not found or has no pages.
        """
        if not is_carousel_id(ref_id):
            return ref_id

        carousel = self.storage.get(ref_id)
        if not carousel or not carousel.page_ids:
            return None

        ts = now_unix if now_unix is not None else time.time()
        return carousel.current_page_id(ts)

    def seconds_until_next_page(self, ref_id: str, now_unix: Optional[float] = None) -> Optional[int]:
        """Return seconds until the carousel advances to the next page.

        Returns None if *ref_id* is not a carousel or not found.
        """
        if not is_carousel_id(ref_id):
            return None

        carousel = self.storage.get(ref_id)
        if not carousel or not carousel.page_ids or len(carousel.page_ids) < 2:
            return None

        ts = now_unix if now_unix is not None else time.time()
        elapsed = ts % carousel.interval_seconds
        return max(1, math.ceil(carousel.interval_seconds - elapsed))


_carousel_service: Optional[CarouselService] = None


def get_carousel_service() -> CarouselService:
    global _carousel_service
    if _carousel_service is None:
        _carousel_service = CarouselService()
    return _carousel_service
