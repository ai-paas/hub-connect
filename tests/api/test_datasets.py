import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, AsyncMock

from app.main import app


@pytest.fixture
def mock_market_service():
    """Mock the async market service factory."""
    mock_service = AsyncMock()
    with patch('app.api.datasets.get_async_market_service', return_value=mock_service):
        yield mock_service


@pytest.mark.asyncio
async def test_search_datasets(mock_market_service):
    """Test dataset search endpoint"""
    mock_market_service.search_datasets.return_value = {
        "datasets": [
            {
                "id": "test/test-dataset",
                "author": "test",
                "downloads": 500,
                "gated": False,
                "lastModified": "2024-01-01T00:00:00Z",
                "likes": 100,
                "private": False,
                "repoType": "dataset"
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 10
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/datasets/?market=huggingface&sort=likes&page=1&limit=10")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_dataset_files(mock_market_service):
    """Test dataset file listing endpoint"""
    mock_market_service.get_dataset_files.return_value = [
        {
            "path": "data.csv",
            "type": "file",
            "size": 1000,
            "blob_id": None,
            "lfs": None
        }
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/datasets/fka/awesome-chatgpt-prompts/files?market=huggingface")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_dataset_info(mock_market_service):
    """Test dataset info endpoint"""
    mock_market_service.get_dataset_info.return_value = {
        "dataset_info": {},
        "pending": [],
        "failed": [],
        "partial": False
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/datasets/fka/awesome-chatgpt-prompts/info?market=huggingface")
    assert response.status_code == 200
