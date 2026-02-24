"""JSON file-based storage for pages.

Provides simple persistence for page configurations that survives restarts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from .models import Page

logger = logging.getLogger(__name__)


class PageStorage:
    """JSON file-based storage for pages.
    
    Stores pages in a JSON file for simple persistence.
    Thread-safe for basic operations.
    """
    
    def __init__(self, storage_file: Optional[str] = None):
        """Initialize page storage.
        
        Args:
            storage_file: Path to JSON storage file. Defaults to data/pages.json
        """
        if storage_file is None:
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            self.storage_file = data_dir / "pages.json"
        else:
            self.storage_file = Path(storage_file)
        
        # In-memory cache
        self._pages: Dict[str, Page] = {}
        
        # Load existing pages
        self._load()
        
        logger.info(f"PageStorage initialized (file: {self.storage_file}, pages: {len(self._pages)})")
    
    def _load(self) -> None:
        """Load pages from storage file."""
        if not self.storage_file.exists():
            self._pages = {}
            return
        
        try:
            with open(self.storage_file, 'r') as f:
                data = json.load(f)
            
            self._pages = {}
            for page_data in data.get("pages", []):
                try:
                    # Handle datetime parsing
                    if "created_at" in page_data and isinstance(page_data["created_at"], str):
                        page_data["created_at"] = datetime.fromisoformat(page_data["created_at"])
                    if "updated_at" in page_data and isinstance(page_data["updated_at"], str):
                        page_data["updated_at"] = datetime.fromisoformat(page_data["updated_at"])
                    
                    page = Page(**page_data)
                    self._pages[page.id] = page
                except Exception as e:
                    logger.warning(f"Failed to load page: {e}")
            
            logger.info(f"Loaded {len(self._pages)} pages from storage")
            
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load pages file: {e}")
            self._pages = {}
    
    def _save(self) -> None:
        """Save pages to storage file."""
        try:
            data = {
                "pages": [page.model_dump() for page in self._pages.values()]
            }
            
            # Convert datetime objects to ISO strings for JSON serialization
            for page_data in data["pages"]:
                if page_data.get("created_at"):
                    page_data["created_at"] = page_data["created_at"].isoformat()
                if page_data.get("updated_at"):
                    page_data["updated_at"] = page_data["updated_at"].isoformat()
            
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Saved {len(self._pages)} pages to storage")
            
        except IOError as e:
            logger.error(f"Failed to save pages file: {e}")
            raise
    
    def list_all(self) -> List[Page]:
        """Get all stored pages.
        
        Returns:
            List of all pages, ordered alphabetically by name
        """
        pages = list(self._pages.values())
        pages.sort(key=lambda p: p.name.lower())
        return pages
    
    def get(self, page_id: str) -> Optional[Page]:
        """Get a page by ID.
        
        Args:
            page_id: The page ID
            
        Returns:
            Page if found, None otherwise
        """
        return self._pages.get(page_id)
    
    def create(self, page: Page) -> Page:
        """Create a new page.
        
        Args:
            page: The page to create
            
        Returns:
            The created page
            
        Raises:
            ValueError: If page with same ID already exists
        """
        if page.id in self._pages:
            raise ValueError(f"Page with ID {page.id} already exists")
        
        # Validate
        errors = page.validate_config()
        if errors:
            raise ValueError(f"Invalid page configuration: {errors}")
        
        self._pages[page.id] = page
        self._save()
        
        logger.info(f"Created page: {page.id} ({page.name})")
        return page
    
    def update(self, page_id: str, updates: dict) -> Optional[Page]:
        """Update an existing page.
        
        Args:
            page_id: The page ID
            updates: Dictionary of fields to update
            
        Returns:
            Updated page if found, None otherwise
        """
        if page_id not in self._pages:
            return None
        
        page = self._pages[page_id]
        
        # Apply updates
        page_dict = page.model_dump()
        for key, value in updates.items():
            if value is not None and key in page_dict:
                page_dict[key] = value
        
        # Update timestamp
        page_dict["updated_at"] = datetime.utcnow()
        
        # Recreate page with updates
        updated_page = Page(**page_dict)
        
        # Validate
        errors = updated_page.validate_config()
        if errors:
            raise ValueError(f"Invalid page configuration: {errors}")
        
        self._pages[page_id] = updated_page
        self._save()
        
        logger.info(f"Updated page: {page_id}")
        return updated_page
    
    def delete(self, page_id: str) -> bool:
        """Delete a page.
        
        Args:
            page_id: The page ID
            
        Returns:
            True if deleted, False if not found
        """
        if page_id not in self._pages:
            return False
        
        del self._pages[page_id]
        self._save()
        
        logger.info(f"Deleted page: {page_id}")
        return True
    
    def exists(self, page_id: str) -> bool:
        """Check if a page exists.
        
        Args:
            page_id: The page ID
            
        Returns:
            True if exists
        """
        return page_id in self._pages
    
    def count(self) -> int:
        """Get the number of stored pages."""
        return len(self._pages)




