"""JSON file-based storage for carousels."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .models import Carousel

logger = logging.getLogger(__name__)


class CarouselStorage:
    """JSON file-based storage for carousels."""

    def __init__(self, storage_file: Optional[str] = None):
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "carousels.json"
        else:
            self.storage_file = Path(storage_file)

        self._carousels: Dict[str, Carousel] = {}
        self._load()

        logger.info(
            f"CarouselStorage initialized "
            f"(file: {self.storage_file}, carousels: {len(self._carousels)})"
        )

    def _load(self) -> None:
        if not self.storage_file.exists():
            self._carousels = {}
            return
        try:
            with open(self.storage_file, "r") as f:
                data = json.load(f)

            self._carousels = {}
            for item in data.get("carousels", []):
                try:
                    if "created_at" in item and isinstance(item["created_at"], str):
                        item["created_at"] = datetime.fromisoformat(item["created_at"])
                    if "updated_at" in item and isinstance(item["updated_at"], str):
                        item["updated_at"] = datetime.fromisoformat(item["updated_at"])
                    carousel = Carousel(**item)
                    self._carousels[carousel.id] = carousel
                except Exception as e:
                    logger.warning(f"Failed to load carousel: {e}")

            logger.info(f"Loaded {len(self._carousels)} carousels from storage")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load carousels file: {e}")
            self._carousels = {}

    def _save(self) -> None:
        try:
            data = {
                "carousels": [c.model_dump() for c in self._carousels.values()]
            }
            for item in data["carousels"]:
                if item.get("created_at"):
                    item["created_at"] = item["created_at"].isoformat()
                if item.get("updated_at"):
                    item["updated_at"] = item["updated_at"].isoformat()

            with open(self.storage_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.debug(f"Saved {len(self._carousels)} carousels to storage")
        except IOError as e:
            logger.error(f"Failed to save carousels file: {e}")
            raise

    def list_all(self) -> List[Carousel]:
        carousels = list(self._carousels.values())
        carousels.sort(key=lambda c: c.name.lower())
        return carousels

    def get(self, carousel_id: str) -> Optional[Carousel]:
        return self._carousels.get(carousel_id)

    def create(self, carousel: Carousel) -> Carousel:
        if carousel.id in self._carousels:
            raise ValueError(f"Carousel with ID {carousel.id} already exists")

        errors = carousel.validate_config()
        if errors:
            raise ValueError(f"Invalid carousel configuration: {errors}")

        self._carousels[carousel.id] = carousel
        self._save()
        logger.info(f"Created carousel: {carousel.id} ({carousel.name})")
        return carousel

    def update(self, carousel_id: str, updates: dict) -> Optional[Carousel]:
        if carousel_id not in self._carousels:
            return None

        carousel = self._carousels[carousel_id]
        carousel_dict = carousel.model_dump()
        for key, value in updates.items():
            if value is not None and key in carousel_dict:
                carousel_dict[key] = value

        carousel_dict["updated_at"] = datetime.utcnow()
        updated = Carousel(**carousel_dict)

        errors = updated.validate_config()
        if errors:
            raise ValueError(f"Invalid carousel configuration: {errors}")

        self._carousels[carousel_id] = updated
        self._save()
        logger.info(f"Updated carousel: {carousel_id}")
        return updated

    def delete(self, carousel_id: str) -> bool:
        if carousel_id not in self._carousels:
            return False
        del self._carousels[carousel_id]
        self._save()
        logger.info(f"Deleted carousel: {carousel_id}")
        return True

    def exists(self, carousel_id: str) -> bool:
        return carousel_id in self._carousels

    def count(self) -> int:
        return len(self._carousels)
