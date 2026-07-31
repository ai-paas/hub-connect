from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.markets.huggingface.async_huggingface_models import (
    AsyncHuggingFaceService,
)
from app.services.markets.kaggle.async_kaggle_models import AsyncKaggleService
from app.services.markets.kaggle import kaggle_client as kaggle_client_module
from app.services.markets.kaggle.mappers import to_dataset_item


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
                "repoType": "dataset",
                "isBenchmark": True,
                "isTraces": False,
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
    item = response.json()["datasets"][0]
    # New upstream fields must survive the response_model filter.
    assert item["isBenchmark"] is True
    assert item["isTraces"] is False


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


@pytest.mark.asyncio
async def test_kaggle_2_dataset_detail_uses_low_level_api():
    captured = {}

    def _get_dataset(request):
        captured["request"] = request
        return SimpleNamespace(
            subtitle="Short",
            description="Long",
            license_name="CC0",
            total_bytes=123,
            last_updated="2026-06-25",
            tags=[],
        )

    class ClientContext:
        def __enter__(self):
            return SimpleNamespace(
                datasets=SimpleNamespace(
                    dataset_api_client=SimpleNamespace(get_dataset=_get_dataset)
                )
            )

        def __exit__(self, *exc):
            return False

    kaggle_client_module.reset_kaggle_client_for_testing(
        SimpleNamespace(build_kaggle_client=lambda: ClientContext())
    )
    try:
        result = await AsyncKaggleService().get_dataset_info("heptapod/titanic")
    finally:
        kaggle_client_module.reset_kaggle_client_for_testing(None)

    assert captured["request"].owner_slug == "heptapod"
    assert captured["request"].dataset_slug == "titanic"
    assert result["cardData"]["license"] == "CC0"


class _JsonResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_huggingface_dataset_pagination_uses_exact_upstream_total():
    class FakeClient:
        def __init__(self):
            self.pages = []

        async def get(self, _url, params, timeout):
            page = params.get("p", 0)
            self.pages.append(page)
            start = page * 30
            datasets = [{"id": f"dataset-{index}"} for index in range(start, start + 30)]
            return _JsonResponse({"datasets": datasets, "numTotalItems": 95})

        async def aclose(self):
            return None

    service = AsyncHuggingFaceService()
    fake_client = FakeClient()
    service._http_client = fake_client

    result = await service.search_datasets(page=4, page_size=10)

    assert [item["id"] for item in result["datasets"]] == [
        f"dataset-{index}" for index in range(30, 40)
    ]
    assert result["total"] == 95
    assert result["has_more"] is True
    assert fake_client.pages == [1]


@pytest.mark.asyncio
async def test_dataset_search_rejects_invalid_pagination():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/v1/datasets/?market=huggingface&page=0&limit=0"
        )

    assert response.status_code == 422


def test_kaggle_dataset_id_uses_ref_slug_instead_of_display_name():
    item = to_dataset_item(
        {
            "ref": "google/example-dataset",
            "ownerName": "Google LLC",
        }
    )

    assert item["id"] == "google/example-dataset"
    assert item["author"] == "google"


def test_kaggle_dataset_pagination_respects_api_page_size():
    dataset_list = MagicMock(
        return_value=[{"ref": f"owner/dataset-{index}"} for index in range(20)]
    )
    kaggle_client_module.reset_kaggle_client_for_testing(
        SimpleNamespace(dataset_list=dataset_list)
    )
    try:
        items = AsyncKaggleService()._datasets_list_sync(
            search="",
            sort_by="votes",
            page=2,
            page_size=10,
        )
    finally:
        kaggle_client_module.reset_kaggle_client_for_testing(None)

    assert [item["ref"] for item in items] == [
        f"owner/dataset-{index}" for index in range(10, 20)
    ]
    assert dataset_list.call_args.kwargs["page"] == 1
