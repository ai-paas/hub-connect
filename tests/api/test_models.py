import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from dotenv import load_dotenv

# Load .env file before starting tests
load_dotenv()

from app.main import app

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