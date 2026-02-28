"""Plugin test fixtures and configuration."""

import pytest
from unittest.mock import patch, MagicMock
import json
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_plugin_singletons():
    """Reset plugin singletons before each test."""
    yield


@pytest.fixture
def sample_manifest():
    """Load the plugin manifest for testing."""
    manifest_path = Path(__file__).parent.parent / "manifest.json"
    with open(manifest_path) as f:
        return json.load(f)


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "enabled": True,
        "max_launches": 4,
        "refresh_seconds": 300,
    }


@pytest.fixture
def mock_launches_response():
    """Mock Launch Library 2 API response."""
    return {
        "count": 3,
        "next": None,
        "previous": None,
        "results": [
            {
                "id": "abc-123",
                "name": "Falcon 9 Block 5 | Crew-12",
                "status": {
                    "id": 1,
                    "name": "Go for Launch",
                    "abbrev": "Go",
                    "description": "Current T-0 confirmed by launch provider."
                },
                "net": "2026-03-15T14:30:00Z",
                "window_start": "2026-03-15T14:30:00Z",
                "window_end": "2026-03-15T18:30:00Z",
                "pad": {
                    "id": 87,
                    "name": "Space Launch Complex 40",
                    "location": {
                        "name": "Cape Canaveral, FL, USA"
                    }
                },
                "launch_service_provider": {
                    "id": 121,
                    "name": "SpaceX",
                    "type": "Commercial"
                },
                "rocket": {
                    "id": 7899,
                    "configuration": {
                        "id": 164,
                        "name": "Falcon 9",
                        "family": "Falcon",
                        "full_name": "Falcon 9 Block 5",
                        "variant": "Block 5"
                    }
                },
                "mission": {
                    "id": 6500,
                    "name": "Crew-12",
                    "description": "Twelfth operational crew rotation mission.",
                    "type": "Human Spaceflight"
                }
            },
            {
                "id": "def-456",
                "name": "Atlas V N22 | USSF-87",
                "status": {
                    "id": 2,
                    "name": "To Be Determined",
                    "abbrev": "TBD",
                    "description": "Launch date is not yet confirmed."
                },
                "net": "2026-03-20T08:00:00Z",
                "window_start": "2026-03-20T08:00:00Z",
                "window_end": "2026-03-20T10:00:00Z",
                "pad": {
                    "id": 29,
                    "name": "Space Launch Complex 41",
                    "location": {
                        "name": "Cape Canaveral, FL, USA"
                    }
                },
                "launch_service_provider": {
                    "id": 124,
                    "name": "ULA",
                    "type": "Commercial"
                },
                "rocket": {
                    "id": 8000,
                    "configuration": {
                        "id": 166,
                        "name": "Atlas V",
                        "family": "Atlas",
                        "full_name": "Atlas V N22",
                        "variant": "N22"
                    }
                },
                "mission": {
                    "id": 6501,
                    "name": "USSF-87",
                    "description": "Military mission for US Space Force.",
                    "type": "Government"
                }
            },
            {
                "id": "ghi-789",
                "name": "Soyuz 2.1a | Progress MS-30",
                "status": {
                    "id": 1,
                    "name": "Go for Launch",
                    "abbrev": "Go",
                    "description": "Current T-0 confirmed."
                },
                "net": "2026-04-01T06:30:00Z",
                "window_start": "2026-04-01T06:30:00Z",
                "window_end": "2026-04-01T06:30:00Z",
                "pad": {
                    "id": 20,
                    "name": "Site 31/6",
                    "location": {
                        "name": "Baikonur Cosmodrome, Kazakhstan"
                    }
                },
                "launch_service_provider": {
                    "id": 63,
                    "name": "Roscosmos",
                    "type": "Government"
                },
                "rocket": {
                    "id": 8001,
                    "configuration": {
                        "id": 24,
                        "name": "Soyuz 2.1a",
                        "family": "Soyuz",
                        "full_name": "Soyuz 2.1a",
                        "variant": "2.1a"
                    }
                },
                "mission": {
                    "id": 6502,
                    "name": "Progress MS-30",
                    "description": "Resupply mission to the ISS.",
                    "type": "Resupply"
                }
            }
        ]
    }


@pytest.fixture
def mock_empty_response():
    """Mock Launch Library 2 API empty response."""
    return {
        "count": 0,
        "next": None,
        "previous": None,
        "results": []
    }


@pytest.fixture
def mock_launch_no_mission():
    """Mock launch with no mission data."""
    return {
        "count": 1,
        "results": [
            {
                "id": "xyz-000",
                "name": "Unknown Vehicle | Mystery Payload",
                "status": {
                    "id": 2,
                    "name": "To Be Determined",
                    "abbrev": "TBD"
                },
                "net": "2026-05-01T12:00:00Z",
                "window_start": "2026-05-01T12:00:00Z",
                "window_end": "2026-05-01T14:00:00Z",
                "pad": None,
                "launch_service_provider": None,
                "rocket": None,
                "mission": None
            }
        ]
    }
