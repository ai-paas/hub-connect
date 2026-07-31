import os
import asyncio
from pathlib import Path
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.testclient import TestClient
from huggingface_hub.utils import HfHubHTTPError

# Load .env file before starting tests
load_dotenv()

from app.main import app
from app.services.auth_service import create_access_token, verify_token
from app.services.markets import async_common
from app.services.markets.huggingface.async_huggingface_models import (
    AsyncHuggingFaceService,
)
from app.services.markets.kaggle.async_kaggle_models import AsyncKaggleService
from app.services.markets.kaggle.handle import parse_model_handle
from app.services.markets.kaggle import kaggle_client as kaggle_client_module
from app.services.markets.kaggle.mappers import to_model_item

client = TestClient(app)


@pytest.fixture
def mock_market_service():
    """Mock the async market service factory to return a mock service."""
    mock_service = AsyncMock()
    with patch('app.api.models.get_async_market_service', return_value=mock_service) as mock:
        yield mock_service


def test_api_models_trending(mock_market_service):
    mock_market_service.get_trending_models.return_value = {
        'models': [
            {'id': 'model1', 'repoType': 'model'},
            {'id': 'model2', 'repoType': 'model'}
        ],
        'total': 2
    }

    response = client.get("/api/v1/models/?market=huggingface&sort=trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2


def test_api_models_search(mock_market_service):
    mock_market_service.search_models.return_value = {
        'models': [
            {'id': 'model1'}, {'id': 'model2'}
        ],
        'total': 2
    }

    response = client.get("/api/v1/models/?market=huggingface&query=test&sort=downloads")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2


def test_api_model_files(mock_market_service):
    mock_market_service.get_model_files.return_value = {
        'files': [
            {'name': 'file1.txt', 'size': 1000},
            {'name': 'file2.txt', 'size': 2000}
        ]
    }

    response = client.get("/api/v1/models/test-model/files?market=huggingface")
    assert response.status_code == 200
    data = response.json()
    assert len(data['files']) == 2
    assert data['files'][0]['name'] == 'file1.txt'
    assert data['files'][1]['name'] == 'file2.txt'


def test_download_model(mock_market_service):
    from fastapi.responses import FileResponse

    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as temp_file:
        temp_file.write(b"Test content")
        temp_file_path = temp_file.name

    mock_market_service.download_model_file.return_value = FileResponse(
        path=temp_file_path,
        filename="test_file.bin",
        media_type="application/octet-stream"
    )

    try:
        response = client.get("/api/v1/models/test-model/download?filename=test_file.bin&market=huggingface")
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/octet-stream'
        assert response.content == b"Test content"
    finally:
        os.unlink(temp_file_path)


def test_api_model_detail(mock_market_service):
    mock_market_service.get_model_detail.return_value = {
        'id': 'test-model',
        'downloads': 1000,
        'likes': 100,
        'lastModified': '2023-01-01',
        'pipeline_tag': 'text-classification',
        'tags': ['nlp', 'classification'],
        'key': 'value',
        'card_html': '<p>Model card HTML</p>'
    }

    response = client.get("/api/v1/models/test-model?market=huggingface")
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 'test-model'
    assert data['downloads'] == 1000
    assert data['likes'] == 100
    assert data['lastModified'] == '2023-01-01'
    assert data['pipeline_tag'] == 'text-classification'
    assert data['tags'] == ['nlp', 'classification']
    assert data['key'] == 'value'
    assert data['card_html'] == '<p>Model card HTML</p>'


def test_api_models_error(mock_market_service):
    mock_market_service.get_trending_models.side_effect = Exception("Test error")

    response = client.get("/api/v1/models/?market=huggingface&sort=trending")
    assert response.status_code == 500


def test_api_models_rejects_unsupported_market():
    response = client.get("/api/v1/models/?market=unknown")

    assert response.status_code == 400


def test_kaggle_2_model_shape_preserves_json_contract():
    raw = SimpleNamespace(
        ref="google/bert",
        author="Google LLC",
        slug="bert",
        instances=[
            SimpleNamespace(
                framework=SimpleNamespace(name="MODEL_FRAMEWORK_PY_TORCH"),
                slug="answer-equivalence-bem",
            )
        ],
        vote_count=7,
        update_time="2026-06-25T00:00:00",
        tags=[SimpleNamespace(name="nlp")],
    )

    item = to_model_item(raw)

    assert item["id"] == "google/bert/pyTorch/answer-equivalence-bem"
    assert item["author"] == "google"
    assert item["likes"] == 7
    assert {"nlp", "pyTorch"} <= set(item["tags"])


@pytest.mark.asyncio
async def test_kaggle_2_model_detail_uses_string_instance_handle():
    api = SimpleNamespace(
        model_get=MagicMock(return_value={"description": "Base"}),
        model_instance_get=MagicMock(return_value={"description": "Instance"}),
    )
    kaggle_client_module.reset_kaggle_client_for_testing(api)
    try:
        detail = await AsyncKaggleService().get_model_detail(
            "google/bert/pyTorch/answer-equivalence-bem"
        )
    finally:
        kaggle_client_module.reset_kaggle_client_for_testing(None)

    api.model_instance_get.assert_called_once_with(
        "google/bert/pyTorch/answer-equivalence-bem"
    )
    assert detail["variation_resolved"] is True


def test_health_hides_storage_exception_details():
    with patch(
        "app.main.service_manager.get_health_status",
        new=AsyncMock(side_effect=RuntimeError("secret storage path")),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["services"]["storage"]["error"] == "Health check failed"
    assert "secret storage path" not in response.text


def test_access_token_round_trip_and_rejects_tampering():
    token = create_access_token({"sub": "admin"}, timedelta(minutes=1))

    assert verify_token(token) == {"username": "admin"}
    assert verify_token(token + "tampered") is None


class _JsonResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


@pytest.mark.asyncio
async def test_huggingface_model_pagination_honors_limit_across_upstream_pages():
    class FakeClient:
        def __init__(self):
            self.pages = []

        async def get(self, _url, params):
            page = params.get("p", 0)
            self.pages.append(page)
            start = page * 30
            models = [
                {"id": f"model-{index}", "repoType": "model"}
                for index in range(start, start + 30)
            ]
            return _JsonResponse({"models": models, "numTotalItems": 100})

        async def aclose(self):
            return None

    service = AsyncHuggingFaceService()
    fake_client = FakeClient()
    service._http_client = fake_client

    result = await service.search_models("", "downloads", page=2, limit=20)

    assert [item["id"] for item in result["models"]] == [
        f"model-{index}" for index in range(20, 40)
    ]
    assert result["total"] == 100
    assert fake_client.pages == [0, 1]


@pytest.mark.asyncio
async def test_kaggle_model_pagination_uses_next_page_token():
    page_tokens = []

    def list_models(request):
        page_tokens.append(request.page_token)
        if request.page_token:
            return SimpleNamespace(
                models=[{"ref": "owner/model-2/pyTorch/v1"}],
                next_page_token="",
                total_results=2,
            )
        return SimpleNamespace(
            models=[{"ref": "owner/model-1/pyTorch/v1"}],
            next_page_token="next-page",
            total_results=2,
        )

    class ClientContext:
        def __enter__(self):
            return SimpleNamespace(
                models=SimpleNamespace(
                    model_api_client=SimpleNamespace(list_models=list_models)
                )
            )

        def __exit__(self, *exc):
            return False

    kaggle_client_module.reset_kaggle_client_for_testing(
        SimpleNamespace(build_kaggle_client=lambda: ClientContext())
    )
    try:
        result = await AsyncKaggleService().search_models(
            query="",
            sort="downloads",
            page=2,
            limit=1,
        )
    finally:
        kaggle_client_module.reset_kaggle_client_for_testing(None)

    assert not page_tokens[0]
    assert page_tokens[1] == "next-page"
    assert result["models"][0]["id"] == "owner/model-2/pyTorch/v1"


def test_kaggle_sdk_internal_type_error_is_not_treated_as_legacy_signature():
    class Api:
        @staticmethod
        def model_instance_get(_handle):
            raise TypeError("internal SDK failure")

    handle = parse_model_handle("owner/model/pyTorch/variation")

    with pytest.raises(TypeError, match="internal SDK failure"):
        AsyncKaggleService._model_instance_get_from_api(Api(), handle)


@pytest.mark.asyncio
async def test_kaggle_direct_download_removes_temporary_directory(tmp_path):
    temp_dir = tmp_path / "kaggle-download"
    temp_dir.mkdir()
    service = AsyncKaggleService()

    def create_download(_handle, target_dir):
        Path(target_dir, "model.bin").write_bytes(b"model")

    service._download_model_files_sync = create_download
    with patch(
        "app.services.markets.kaggle.async_kaggle_models.tempfile.mkdtemp",
        return_value=str(temp_dir),
    ):
        response = await service.download_model_file(
            "owner/model/pyTorch/variation",
            "model.bin",
        )

    assert temp_dir.exists()
    await response.background()
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_market_service_is_reused_and_closed():
    async_common._async_market_instances.clear()
    first = await async_common.get_async_market_service("huggingface")
    second = await async_common.get_async_market_service("huggingface")
    close = AsyncMock()
    first._http_client = SimpleNamespace(aclose=close)

    await async_common.close_async_market_services()

    assert first is second
    close.assert_awaited_once()
    assert async_common._async_market_instances == {}


@pytest.mark.asyncio
async def test_huggingface_timeout_maps_to_gateway_timeout():
    service = AsyncHuggingFaceService()
    with patch(
        "app.services.markets.huggingface.async_huggingface_models.asyncio.wait_for",
        new=AsyncMock(side_effect=asyncio.TimeoutError),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await service._async_hf_api_call(lambda: None)

    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_huggingface_missing_model_is_not_returned_as_empty_success():
    response = httpx.Response(
        404,
        request=httpx.Request("GET", "https://huggingface.co/api/models/missing"),
    )
    missing = HfHubHTTPError("missing", response=response)
    service = AsyncHuggingFaceService()
    service._async_hf_api_call = AsyncMock(side_effect=[missing, missing])

    with pytest.raises(HTTPException) as exc_info:
        await service.get_model_detail("missing/model")

    assert exc_info.value.status_code == 404
