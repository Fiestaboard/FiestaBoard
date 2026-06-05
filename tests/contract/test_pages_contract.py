"""Contract tests for the /pages API endpoints.

Validates that the Python backend returns responses that conform to the
schema the Next.js frontend expects to consume.

Issue: #502
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app
from src.pages.models import Page
from tests.contract.schemas import (
    CreatePageResponse,
    GetPageResponse,
    PagesListResponse,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_page():
    """A minimal valid template page."""
    return Page(
        id="test-page-contract-1",
        name="Contract Test",
        type="template",
        template=["LINE ONE", "", "", "", "", ""],
    )


# ---------------------------------------------------------------------------
# GET /pages
# ---------------------------------------------------------------------------


class TestListPagesContract:
    def test_returns_200(self, client):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = []
            mock_svc.return_value = svc

            resp = client.get("/pages")
        assert resp.status_code == 200

    def test_response_has_pages_and_total(self, client):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = []
            mock_svc.return_value = svc

            resp = client.get("/pages")

        data = resp.json()
        assert "pages" in data
        assert "total" in data

    def test_response_validates_against_schema(self, client):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = []
            mock_svc.return_value = svc

            resp = client.get("/pages")

        # Should not raise
        parsed = PagesListResponse(**resp.json())
        assert parsed.total == 0
        assert parsed.pages == []

    def test_pages_list_with_items_validates(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = [sample_page]
            mock_svc.return_value = svc

            resp = client.get("/pages")

        data = resp.json()
        parsed = PagesListResponse(**data)
        assert parsed.total == 1
        assert len(parsed.pages) == 1
        assert parsed.pages[0].name == "Contract Test"
        assert parsed.pages[0].type == "template"

    def test_page_id_is_string(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = [sample_page]
            mock_svc.return_value = svc

            resp = client.get("/pages")

        page = resp.json()["pages"][0]
        assert isinstance(page["id"], str)
        assert len(page["id"]) > 0

    def test_total_matches_pages_length(self, client, sample_page):
        page2 = Page(id="test-2", name="Page Two", type="template", template=["X"])
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.list_pages.return_value = [sample_page, page2]
            mock_svc.return_value = svc

            resp = client.get("/pages")

        data = resp.json()
        assert data["total"] == len(data["pages"])


# ---------------------------------------------------------------------------
# POST /pages
# ---------------------------------------------------------------------------


class TestCreatePageContract:
    def test_returns_200_on_valid_input(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.create_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.post(
                "/pages",
                json={"name": "Contract Test", "type": "template", "template": ["HELLO", "", "", "", "", ""]},
            )

        assert resp.status_code == 200

    def test_response_validates_against_schema(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.create_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.post(
                "/pages",
                json={"name": "Contract Test", "type": "template", "template": ["HELLO", "", "", "", "", ""]},
            )

        parsed = CreatePageResponse(**resp.json())
        assert parsed.status == "success"
        assert parsed.page.id == "test-page-contract-1"

    def test_response_status_is_success(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.create_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.post(
                "/pages",
                json={"name": "T", "type": "template", "template": ["X", "", "", "", "", ""]},
            )

        assert resp.json()["status"] == "success"

    def test_returns_400_for_invalid_page(self, client):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.create_page.side_effect = ValueError("Missing required field")
            mock_svc.return_value = svc

            resp = client.post(
                "/pages",
                json={"name": "Bad Page", "type": "template"},  # missing template
            )

        # Either 400 (business logic) or 422 (schema validation)
        assert resp.status_code in (400, 422)

    def test_created_page_has_required_fields(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.create_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.post(
                "/pages",
                json={"name": "T", "type": "template", "template": ["X", "", "", "", "", ""]},
            )

        page = resp.json()["page"]
        assert "id" in page
        assert "name" in page
        assert "type" in page


# ---------------------------------------------------------------------------
# GET /pages/{page_id}
# ---------------------------------------------------------------------------


class TestGetPageContract:
    def test_returns_200_for_existing_page(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.get_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.get("/pages/test-page-contract-1")

        assert resp.status_code == 200

    def test_response_validates_against_schema(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.get_page.return_value = sample_page
            mock_svc.return_value = svc

            resp = client.get("/pages/test-page-contract-1")

        # GET /pages/{id} returns the page directly (not nested under "page")
        parsed = GetPageResponse(**resp.json())
        assert parsed.id == "test-page-contract-1"

    def test_returns_404_for_missing_page(self, client):
        with patch("src.api_server.get_page_service") as mock_svc:
            svc = Mock()
            svc.get_page.return_value = None
            mock_svc.return_value = svc

            resp = client.get("/pages/does-not-exist")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /pages/{page_id}
# ---------------------------------------------------------------------------


class TestDeletePageContract:
    def test_returns_200_on_delete(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            from src.pages.service import DeleteResult

            svc = Mock()
            svc.delete_page.return_value = DeleteResult(deleted=True)
            mock_svc.return_value = svc

            resp = client.delete("/pages/test-page-contract-1")

        assert resp.status_code == 200

    def test_response_has_status_field(self, client, sample_page):
        with patch("src.api_server.get_page_service") as mock_svc:
            from src.pages.service import DeleteResult

            svc = Mock()
            svc.delete_page.return_value = DeleteResult(deleted=True)
            mock_svc.return_value = svc

            resp = client.delete("/pages/test-page-contract-1")

        data = resp.json()
        assert "status" in data
