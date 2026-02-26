"""Tests for pages module (models, storage, service, API)."""

import pytest
import tempfile
import os
from datetime import datetime
from unittest.mock import Mock, patch

from src.pages.models import Page, PageCreate, PageUpdate, RowConfig, PageType
from src.pages.storage import PageStorage
from src.pages.service import PageService, DeleteResult
from src.displays.service import DisplayResult


class TestPageModels:
    """Tests for Page and related models."""
    
    def test_page_single_valid(self):
        """Test valid single-type page."""
        page = Page(
            name="Weather Page",
            type="single",
            display_type="weather"
        )
        assert page.is_valid()
        assert page.type == "single"
        assert page.display_type == "weather"
    
    def test_page_single_missing_display_type(self):
        """Test single page without display_type is invalid."""
        page = Page(name="Bad Page", type="single")
        errors = page.validate_config()
        assert "display_type" in errors[0].lower()
    
    def test_page_composite_valid(self):
        """Test valid composite page."""
        page = Page(
            name="Composite Page",
            type="composite",
            rows=[
                RowConfig(source="weather", row_index=0, target_row=0),
                RowConfig(source="datetime", row_index=0, target_row=1),
            ]
        )
        assert page.is_valid()
    
    def test_page_composite_missing_rows(self):
        """Test composite page without rows is invalid."""
        page = Page(name="Bad Page", type="composite")
        errors = page.validate_config()
        assert "row" in errors[0].lower()
    
    def test_page_composite_duplicate_targets(self):
        """Test composite page with duplicate target rows is invalid."""
        page = Page(
            name="Bad Page",
            type="composite",
            rows=[
                RowConfig(source="weather", row_index=0, target_row=0),
                RowConfig(source="datetime", row_index=0, target_row=0),  # Duplicate!
            ]
        )
        errors = page.validate_config()
        assert "duplicate" in errors[0].lower()
    
    def test_page_template_valid(self):
        """Test valid template page."""
        page = Page(
            name="Template Page",
            type="template",
            template=["Line 1", "Line 2", "", "", "", ""]
        )
        assert page.is_valid()
    
    def test_page_template_missing_template(self):
        """Test template page without template is invalid."""
        page = Page(name="Bad Page", type="template")
        errors = page.validate_config()
        assert "template" in errors[0].lower()
    
    def test_page_generates_id(self):
        """Test that page auto-generates an ID."""
        page = Page(name="Test", type="single", display_type="weather")
        assert page.id is not None
        assert len(page.id) > 0
    
    def test_page_duration_defaults(self):
        """Test default duration is 300 seconds."""
        page = Page(name="Test", type="single", display_type="weather")
        assert page.duration_seconds == 300
    
    def test_row_config_valid(self):
        """Test valid row config."""
        config = RowConfig(source="weather", row_index=0, target_row=5)
        assert config.source == "weather"
        assert config.row_index == 0
        assert config.target_row == 5


class TestPageStorage:
    """Tests for PageStorage."""
    
    @pytest.fixture
    def temp_storage_file(self):
        """Create a temporary storage file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"pages": []}')
            yield f.name
        os.unlink(f.name)
    
    @pytest.fixture
    def storage(self, temp_storage_file):
        """Create a storage instance with temp file."""
        return PageStorage(storage_file=temp_storage_file)
    
    def test_create_page(self, storage):
        """Test creating a page."""
        page = Page(name="Test", type="single", display_type="weather")
        created = storage.create(page)
        
        assert created.id == page.id
        assert created.name == "Test"
        assert storage.count() == 1
    
    def test_create_duplicate_id_raises(self, storage):
        """Test creating page with duplicate ID raises."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)
        
        with pytest.raises(ValueError, match="already exists"):
            storage.create(page)
    
    def test_get_page(self, storage):
        """Test getting a page by ID."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)
        
        retrieved = storage.get(page.id)
        assert retrieved is not None
        assert retrieved.name == "Test"
    
    def test_get_nonexistent_returns_none(self, storage):
        """Test getting nonexistent page returns None."""
        result = storage.get("nonexistent")
        assert result is None
    
    def test_list_all(self, storage):
        """Test listing all pages."""
        page1 = Page(name="Page 1", type="single", display_type="weather")
        page2 = Page(name="Page 2", type="single", display_type="datetime")
        storage.create(page1)
        storage.create(page2)
        
        pages = storage.list_all()
        assert len(pages) == 2
    
    def test_list_all_alphabetical_order(self, storage):
        """Test that list_all returns pages sorted alphabetically by name."""
        page_z = Page(name="Zebra Page", type="single", display_type="weather")
        page_a = Page(name="Alpha Page", type="single", display_type="datetime")
        page_m = Page(name="Middle Page", type="template", template=["Hi", "", "", "", "", ""])
        storage.create(page_z)
        storage.create(page_a)
        storage.create(page_m)
        
        pages = storage.list_all()
        names = [p.name for p in pages]
        assert names == ["Alpha Page", "Middle Page", "Zebra Page"]
    
    def test_list_all_alphabetical_case_insensitive(self, storage):
        """Test that list_all sorts case-insensitively."""
        page_upper = Page(name="Bravo", type="single", display_type="weather")
        page_lower = Page(name="alpha", type="single", display_type="datetime")
        page_mixed = Page(name="Charlie", type="single", display_type="weather")
        storage.create(page_upper)
        storage.create(page_lower)
        storage.create(page_mixed)
        
        pages = storage.list_all()
        names = [p.name for p in pages]
        assert names == ["alpha", "Bravo", "Charlie"]
    
    def test_update_page(self, storage):
        """Test updating a page."""
        page = Page(name="Original", type="single", display_type="weather")
        storage.create(page)
        
        updated = storage.update(page.id, {"name": "Updated"})
        assert updated.name == "Updated"
        assert updated.updated_at is not None
    
    def test_update_nonexistent_returns_none(self, storage):
        """Test updating nonexistent page returns None."""
        result = storage.update("nonexistent", {"name": "Test"})
        assert result is None
    
    def test_delete_page(self, storage):
        """Test deleting a page."""
        page = Page(name="Test", type="single", display_type="weather")
        storage.create(page)
        
        result = storage.delete(page.id)
        assert result is True
        assert storage.get(page.id) is None
    
    def test_delete_nonexistent_returns_false(self, storage):
        """Test deleting nonexistent page returns False."""
        result = storage.delete("nonexistent")
        assert result is False
    
    def test_persistence(self, temp_storage_file):
        """Test that pages persist across storage instances."""
        # Create first storage and add page
        storage1 = PageStorage(storage_file=temp_storage_file)
        page = Page(name="Persistent", type="single", display_type="weather")
        storage1.create(page)
        
        # Create second storage and verify page exists
        storage2 = PageStorage(storage_file=temp_storage_file)
        retrieved = storage2.get(page.id)
        
        assert retrieved is not None
        assert retrieved.name == "Persistent"


class TestPageService:
    """Tests for PageService."""
    
    @pytest.fixture
    def temp_storage_file(self):
        """Create a temporary storage file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"pages": []}')
            yield f.name
        os.unlink(f.name)
    
    @pytest.fixture
    def service(self, temp_storage_file):
        """Create a page service with temp storage."""
        storage = PageStorage(storage_file=temp_storage_file)
        return PageService(storage=storage)
    
    def test_create_page(self, service):
        """Test creating a page via service."""
        data = PageCreate(name="Test", type="single", display_type="weather")
        page = service.create_page(data)
        
        assert page.name == "Test"
        assert page.type == "single"
    
    def test_list_pages(self, service):
        """Test listing pages via service."""
        service.create_page(PageCreate(name="Page 1", type="single", display_type="weather"))
        service.create_page(PageCreate(name="Page 2", type="single", display_type="datetime"))
        
        pages = service.list_pages()
        assert len(pages) == 2
    
    def test_update_page(self, service):
        """Test updating a page via service."""
        page = service.create_page(PageCreate(name="Original", type="single", display_type="weather"))
        
        updated = service.update_page(page.id, PageUpdate(name="Updated"))
        assert updated.name == "Updated"
    
    def test_delete_page(self, service):
        """Test deleting a page via service (when multiple pages exist)."""
        # Create two pages so we're not deleting the last one
        page1 = service.create_page(PageCreate(name="Page 1", type="single", display_type="weather"))
        page2 = service.create_page(PageCreate(name="Page 2", type="single", display_type="datetime"))
        
        result = service.delete_page(page1.id)
        assert result.deleted is True
        assert result.default_page_created is False
        assert result.new_page_id is None
        assert service.get_page(page1.id) is None
        # page2 should still exist
        assert service.get_page(page2.id) is not None
    
    def test_delete_last_page_creates_default(self, service):
        """Test deleting the last page creates a default welcome page."""
        # Create a single page
        page = service.create_page(PageCreate(name="Only Page", type="single", display_type="weather"))
        
        # Delete it - should create a default page
        result = service.delete_page(page.id)
        
        assert result.deleted is True
        assert result.default_page_created is True
        assert result.new_page_id is not None
        
        # Original page should be gone
        assert service.get_page(page.id) is None
        
        # Default page should exist
        default_page = service.get_page(result.new_page_id)
        assert default_page is not None
        assert default_page.name == "Welcome"
        assert default_page.type == "template"
        assert default_page.template is not None
        
        # There should be exactly 1 page
        pages = service.list_pages()
        assert len(pages) == 1
    
    def test_delete_nonexistent_page(self, service):
        """Test deleting a page that doesn't exist."""
        result = service.delete_page("nonexistent-id")
        assert result.deleted is False
        assert result.default_page_created is False
    
    @patch('src.pages.service.get_display_service')
    def test_render_single_page(self, mock_get_display, service):
        """Test rendering a single-source page."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F\nSan Francisco",
            raw={"temp": 72},
            available=True
        )
        mock_get_display.return_value = mock_display_service
        
        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        result = service.render_page(page)
        
        assert result.available is True
        assert "Sunny" in result.formatted
    
    @patch('src.pages.service.get_display_service')
    def test_render_composite_page(self, mock_get_display, service):
        """Test rendering a composite page."""
        mock_display_service = Mock()
        
        def mock_get_display_fn(display_type):
            if display_type == "weather":
                return DisplayResult(
                    display_type="weather",
                    formatted="Sunny Line 1\nSunny Line 2",
                    raw={},
                    available=True
                )
            elif display_type == "datetime":
                return DisplayResult(
                    display_type="datetime",
                    formatted="Monday Dec 25\n10:30 AM",
                    raw={},
                    available=True
                )
            return DisplayResult(display_type=display_type, formatted="", raw={}, available=False)
        
        mock_display_service.get_display.side_effect = mock_get_display_fn
        mock_get_display.return_value = mock_display_service
        
        page = service.create_page(PageCreate(
            name="Composite",
            type="composite",
            rows=[
                RowConfig(source="weather", row_index=0, target_row=0),
                RowConfig(source="datetime", row_index=0, target_row=2),
            ]
        ))
        result = service.render_page(page)
        
        assert result.available is True
        lines = result.formatted.split('\n')
        assert "Sunny" in lines[0]
        assert "Monday" in lines[2]
    
    def test_render_template_page(self, service):
        """Test rendering a template page."""
        page = service.create_page(PageCreate(
            name="Template",
            type="template",
            template=["Hello World", "Line 2", "", "", "", ""]
        ))
        result = service.render_page(page)
        
        assert result.available is True
        assert "Hello World" in result.formatted
    
    @patch('src.pages.service.get_display_service')
    def test_preview_page_uses_cache(self, mock_get_display, service):
        """Test that preview_page uses cache on subsequent calls."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F",
            raw={"temp": 72},
            available=True
        )
        mock_get_display.return_value = mock_display_service
        
        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        
        # First call should render
        result1 = service.preview_page(page.id)
        assert result1.available is True
        assert mock_display_service.get_display.call_count == 1
        
        # Second call should use cache (no additional render)
        result2 = service.preview_page(page.id)
        assert result2.available is True
        assert result2.formatted == result1.formatted
        assert mock_display_service.get_display.call_count == 1  # Still 1!
    
    @patch('src.pages.service.get_display_service')
    def test_preview_page_force_refresh(self, mock_get_display, service):
        """Test that force_refresh bypasses cache."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F",
            raw={"temp": 72},
            available=True
        )
        mock_get_display.return_value = mock_display_service
        
        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        
        # First call
        result1 = service.preview_page(page.id)
        assert result1.available is True
        assert mock_display_service.get_display.call_count == 1
        
        # Second call with force_refresh=True should render again
        result2 = service.preview_page(page.id, force_refresh=True)
        assert result2.available is True
        assert mock_display_service.get_display.call_count == 2  # Rendered again!
    
    @patch('src.pages.service.get_display_service')
    def test_update_page_invalidates_cache(self, mock_get_display, service):
        """Test that updating a page invalidates its cache."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F",
            raw={"temp": 72},
            available=True
        )
        mock_get_display.return_value = mock_display_service
        
        page = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        
        # First preview - should cache
        result1 = service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 1
        
        # Second preview - should use cache
        result2 = service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 1
        
        # Update the page
        service.update_page(page.id, PageUpdate(name="Updated Weather"))
        
        # Third preview - should re-render (cache was invalidated)
        result3 = service.preview_page(page.id)
        assert mock_display_service.get_display.call_count == 2
    
    def test_get_cache_stats(self, service):
        """Test getting cache statistics."""
        stats = service.get_cache_stats()
        
        assert "cache_size" in stats
        assert "cached_pages" in stats
        assert "ttl_seconds" in stats
        assert stats["cache_size"] == 0
        assert stats["cached_pages"] == []
    
    @patch('src.pages.service.get_display_service')
    def test_cache_stats_after_preview(self, mock_get_display, service):
        """Test cache statistics after previewing pages."""
        mock_display_service = Mock()
        mock_display_service.get_display.return_value = DisplayResult(
            display_type="weather",
            formatted="Sunny, 72F",
            raw={"temp": 72},
            available=True
        )
        mock_get_display.return_value = mock_display_service
        
        page1 = service.create_page(PageCreate(name="Weather", type="single", display_type="weather"))
        page2 = service.create_page(PageCreate(name="Datetime", type="single", display_type="datetime"))
        
        # Preview both pages
        service.preview_page(page1.id)
        service.preview_page(page2.id)
        
        stats = service.get_cache_stats()
        assert stats["cache_size"] == 2
        assert page1.id in stats["cached_pages"]
        assert page2.id in stats["cached_pages"]
    
    @patch('src.pages.service.get_template_engine')
    def test_preview_pages_batch_shares_context(self, mock_get_engine, service):
        """Test that batch preview builds template context only once."""
        mock_engine = Mock()
        mock_engine._build_context.return_value = {"weather": {"temp": 72}}
        mock_engine.render_lines.return_value = "Hello World\n\n\n\n\n"
        mock_get_engine.return_value = mock_engine
        
        # Create multiple template pages
        page1 = service.create_page(PageCreate(name="Page 1", type="template", template=["Hello", "", "", "", "", ""]))
        page2 = service.create_page(PageCreate(name="Page 2", type="template", template=["World", "", "", "", "", ""]))
        page3 = service.create_page(PageCreate(name="Page 3", type="template", template=["Test", "", "", "", "", ""]))
        
        # Batch preview all three
        results = service.preview_pages_batch([page1.id, page2.id, page3.id])
        
        assert len(results) == 3
        assert all(r is not None and r.available for r in results.values())
        
        # Context should be built only once, not three times
        assert mock_engine._build_context.call_count == 1
        # But render_lines should be called three times (once per page)
        assert mock_engine.render_lines.call_count == 3
    
    @patch('src.pages.service.get_template_engine')
    def test_preview_pages_batch_uses_cache(self, mock_get_engine, service):
        """Test that batch preview uses cache for already-cached pages."""
        mock_engine = Mock()
        mock_engine._build_context.return_value = {}
        mock_engine.render_lines.return_value = "Rendered\n\n\n\n\n"
        mock_get_engine.return_value = mock_engine
        
        page1 = service.create_page(PageCreate(name="Page 1", type="template", template=["Hello", "", "", "", "", ""]))
        page2 = service.create_page(PageCreate(name="Page 2", type="template", template=["World", "", "", "", "", ""]))
        
        # Preview page1 first to populate cache
        service.preview_pages_batch([page1.id])
        assert mock_engine.render_lines.call_count == 1
        
        # Batch preview both - page1 should use cache, only page2 renders
        mock_engine.render_lines.reset_mock()
        mock_engine._build_context.reset_mock()
        results = service.preview_pages_batch([page1.id, page2.id])
        
        assert len(results) == 2
        assert mock_engine.render_lines.call_count == 1  # Only page2 rendered
    
    def test_preview_pages_batch_nonexistent_page(self, service):
        """Test that batch preview handles nonexistent pages."""
        results = service.preview_pages_batch(["nonexistent-id"])
        assert results["nonexistent-id"] is None


class TestPagesAPIEndpoints:
    """Tests for pages API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        from src.api_server import app
        from fastapi.testclient import TestClient
        return TestClient(app)
    
    @pytest.fixture
    def mock_page_service(self):
        """Mock the page service."""
        with patch('src.api_server.get_page_service') as mock:
            mock_service = Mock()
            mock.return_value = mock_service
            yield mock_service
    
    def test_list_pages(self, client, mock_page_service):
        """Test GET /pages."""
        mock_page_service.list_pages.return_value = [
            Page(id="1", name="Page 1", type="single", display_type="weather"),
            Page(id="2", name="Page 2", type="single", display_type="datetime"),
        ]
        
        response = client.get("/pages")
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["pages"]) == 2
    
    def test_create_page(self, client, mock_page_service):
        """Test POST /pages."""
        mock_page_service.create_page.return_value = Page(
            id="new-id",
            name="New Page",
            type="single",
            display_type="weather"
        )
        
        response = client.post("/pages", json={
            "name": "New Page",
            "type": "single",
            "display_type": "weather"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["page"]["name"] == "New Page"
    
    def test_get_page(self, client, mock_page_service):
        """Test GET /pages/{id}."""
        mock_page_service.get_page.return_value = Page(
            id="test-id",
            name="Test Page",
            type="single",
            display_type="weather"
        )
        
        response = client.get("/pages/test-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Page"
    
    def test_get_page_not_found(self, client, mock_page_service):
        """Test GET /pages/{id} with nonexistent ID."""
        mock_page_service.get_page.return_value = None
        
        response = client.get("/pages/nonexistent")
        
        assert response.status_code == 404
    
    def test_update_page(self, client, mock_page_service):
        """Test PUT /pages/{id}."""
        mock_page_service.update_page.return_value = Page(
            id="test-id",
            name="Updated Page",
            type="single",
            display_type="weather"
        )
        
        response = client.put("/pages/test-id", json={"name": "Updated Page"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["page"]["name"] == "Updated Page"
    
    def test_delete_page(self, client, mock_page_service):
        """Test DELETE /pages/{id}."""
        mock_page_service.delete_page.return_value = DeleteResult(deleted=True)
        
        response = client.delete("/pages/test-id")
        
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data["message"]
        assert data["default_page_created"] is False
    
    def test_delete_last_page_creates_default(self, client, mock_page_service):
        """Test DELETE /pages/{id} when it's the last page."""
        mock_page_service.delete_page.return_value = DeleteResult(
            deleted=True,
            default_page_created=True,
            new_page_id="new-default-id"
        )
        
        response = client.delete("/pages/test-id")
        
        assert response.status_code == 200
        data = response.json()
        assert data["default_page_created"] is True
        assert data["new_page_id"] == "new-default-id"
        assert "welcome" in data["message"].lower()
    
    def test_delete_page_not_found(self, client, mock_page_service):
        """Test DELETE /pages/{id} with nonexistent ID."""
        mock_page_service.delete_page.return_value = DeleteResult(deleted=False)
        
        response = client.delete("/pages/nonexistent-id")
        
        assert response.status_code == 404
    
    def test_preview_page(self, client, mock_page_service):
        """Test POST /pages/{id}/preview."""
        mock_page_service.preview_page.return_value = DisplayResult(
            display_type="page:single",
            formatted="Preview Content\nLine 2",
            raw={"page_id": "test-id"},
            available=True
        )
        
        response = client.post("/pages/test-id/preview")
        
        assert response.status_code == 200
        data = response.json()
        assert data["page_id"] == "test-id"
        assert "Preview Content" in data["message"]

