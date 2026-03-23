import os
import tempfile
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock
from dotenv import load_dotenv

# Load .env file before tests
load_dotenv()

from app.main import app


# Use async test client
@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_market_service():
    """Mock the async market service factory."""
    mock_service = AsyncMock()
    with patch('app.api.models.get_async_market_service', return_value=mock_service):
        yield mock_service


@pytest.mark.asyncio
async def test_async_api_models_trending(async_client, mock_market_service):
    """Test trending models API with async client"""
    mock_market_service.get_trending_models.return_value = {
        'models': [
            {'id': 'model1', 'repoType': 'model'},
            {'id': 'model2', 'repoType': 'model'}
        ],
        'total': 2
    }

    response = await async_client.get("/api/v1/models/?market=huggingface&sort=trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2


@pytest.mark.asyncio
async def test_async_api_models_search(async_client, mock_market_service):
    """Test search models API with async client"""
    mock_market_service.search_models.return_value = {
        'models': [
            {'id': 'model1'}, {'id': 'model2'}
        ],
        'total': 2
    }

    response = await async_client.get("/api/v1/models/?market=huggingface&query=test&sort=downloads")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2


@pytest.mark.asyncio
async def test_async_api_models_with_parameter_filtering(async_client, mock_market_service):
    """Test models API with parameter filtering"""
    mock_market_service.get_trending_models.return_value = {
        'models': [
            {
                'id': 'model1',
                'repoType': 'model',
                'numParameters': 7_000_000_000,
                'parameterDisplay': '7B',
                'parameterRange': 'large'
            },
            {
                'id': 'model2',
                'repoType': 'model',
                'numParameters': 13_000_000_000,
                'parameterDisplay': '13B',
                'parameterRange': 'large'
            }
        ],
        'total': 2,
        'applied_filters': {
            'num_parameters_min': '3B',
            'num_parameters_max': '256B'
        }
    }

    response = await async_client.get("/api/v1/models/?market=huggingface&sort=trending&num_parameters_min=3B&num_parameters_max=256B")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2


@pytest.mark.asyncio
async def test_async_api_models_parameter_filtering_min_only(async_client, mock_market_service):
    """Test models API with minimum parameter filtering only"""
    mock_market_service.search_models.return_value = {
        'models': [
            {
                'id': 'model1',
                'numParameters': 24_000_000_000,
                'parameterDisplay': '24B',
                'parameterRange': 'extra_large'
            }
        ],
        'total': 1,
        'applied_filters': {
            'num_parameters_min': '24B'
        }
    }

    response = await async_client.get("/api/v1/models/?market=huggingface&query=test&num_parameters_min=24B")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 1


@pytest.mark.asyncio
async def test_async_api_models_parameter_filtering_max_only(async_client, mock_market_service):
    """Test models API with maximum parameter filtering only"""
    mock_market_service.get_trending_models.return_value = {
        'models': [
            {
                'id': 'model1',
                'repoType': 'model',
                'numParameters': 3_000_000_000,
                'parameterDisplay': '3B',
                'parameterRange': 'large'
            }
        ],
        'total': 1,
        'applied_filters': {
            'num_parameters_max': '128B'
        }
    }

    response = await async_client.get("/api/v1/models/?market=huggingface&sort=trending&num_parameters_max=128B")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 1


@pytest.mark.asyncio
async def test_async_api_models_invalid_parameter_format(async_client):
    """Test models API with invalid parameter format"""
    response = await async_client.get("/api/v1/models/?market=huggingface&num_parameters_min=3M")
    assert response.status_code == 400
    data = response.json()
    assert 'INVALID_MIN_PARAMETER_FORMAT' in str(data['detail'])


@pytest.mark.asyncio
async def test_async_api_models_invalid_parameter_range(async_client):
    """Test models API with invalid parameter range"""
    response = await async_client.get("/api/v1/models/?market=huggingface&num_parameters_min=256B&num_parameters_max=3B")
    assert response.status_code == 400
    data = response.json()
    assert 'INVALID_PARAMETER_RANGE' in str(data['detail'])


@pytest.mark.asyncio
async def test_async_api_model_files(async_client, mock_market_service):
    """Test model files API with async client"""
    mock_market_service.get_model_files.return_value = {
        'files': [
            {'name': 'file1.txt', 'size': 1000},
            {'name': 'file2.txt', 'size': 2000}
        ]
    }

    response = await async_client.get("/api/v1/models/test-model/files?market=huggingface")
    assert response.status_code == 200
    data = response.json()
    assert len(data['files']) == 2
    assert data['files'][0]['name'] == 'file1.txt'
    assert data['files'][1]['name'] == 'file2.txt'


@pytest.mark.asyncio
async def test_async_download_model(async_client, mock_market_service):
    """Test model download with async implementation"""
    from starlette.responses import FileResponse

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
        response = await async_client.get("/api/v1/models/test-model/download?filename=test_file.bin&market=huggingface")
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/octet-stream'
        assert b"Test content" in response.content
    finally:
        os.unlink(temp_file_path)


@pytest.mark.asyncio
async def test_async_api_model_detail(async_client, mock_market_service):
    """Test model detail API with async implementation"""
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

    response = await async_client.get("/api/v1/models/test-model?market=huggingface")
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


@pytest.mark.asyncio
async def test_async_api_models_error(async_client, mock_market_service):
    """Test error handling with async client"""
    mock_market_service.get_trending_models.side_effect = Exception("Test error")

    response = await async_client.get("/api/v1/models/?market=huggingface&sort=trending")
    assert response.status_code == 500


# Performance test
@pytest.mark.asyncio
async def test_async_concurrent_requests(async_client, mock_market_service):
    """Test concurrent requests performance"""
    import asyncio

    mock_market_service.get_trending_models.return_value = {
        'models': [{'id': 'model1', 'repoType': 'model'}],
        'total': 1
    }

    # Make 10 concurrent requests
    tasks = []
    for i in range(1, 11):
        task = async_client.get(f"/api/v1/models/?market=huggingface&sort=trending&page={i}")
        tasks.append(task)

    # Execute all requests concurrently
    responses = await asyncio.gather(*tasks)

    # Verify all requests succeeded
    for response in responses:
        assert response.status_code == 200
        data = response.json()
        assert len(data['models']) == 1
