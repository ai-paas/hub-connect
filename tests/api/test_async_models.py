import os
import tempfile
import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock, AsyncMock
from dotenv import load_dotenv

# Load .env file before tests
load_dotenv()

from app.main import app
from app.services.async_service_manager import service_manager

# Use async test client
@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def mock_async_httpx_client():
    """Mock httpx.AsyncClient for HTTP requests"""
    with patch('app.services.markets.huggingface.async_huggingface_models.httpx.AsyncClient') as mock:
        mock_client = AsyncMock()
        mock_response = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock.return_value = mock_client
        yield mock_client

@pytest.fixture
async def mock_async_hf_api():
    """Mock HuggingFace API for async calls"""
    with patch('app.services.markets.huggingface.async_huggingface_models.HfApi') as mock:
        mock_instance = MagicMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.fixture
async def mock_async_hf_hub_download():
    """Mock hf_hub_download for async file downloads"""
    with patch('app.services.markets.huggingface.async_huggingface_models.hf_hub_download') as mock:
        yield mock

@pytest.fixture
async def mock_async_storage_service():
    """Mock AsyncStorageService"""
    with patch('app.services.async_storage_service.AsyncStorageService') as mock:
        mock_instance = AsyncMock()
        mock.return_value = mock_instance
        yield mock_instance

@pytest.mark.asyncio
async def test_async_api_models_trending(async_client, mock_async_httpx_client):
    """Test trending models API with async client"""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        'models': [
            {'id': 'model1', 'repoType': 'model'},
            {'id': 'model2', 'repoType': 'model'}
        ],
        'numTotalItems': 2
    }
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response

    response = await async_client.get("/api/v1/models?sort=trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2

@pytest.mark.asyncio
async def test_async_api_models_search(async_client, mock_async_httpx_client):
    """Test search models API with async client"""
    mock_response = AsyncMock()
    mock_response.json.return_value = [
        {'id': 'model1'}, {'id': 'model2'}
    ]
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response

    response = await async_client.get("/api/v1/models?query=test&sort=downloads")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2

@pytest.mark.asyncio
async def test_async_api_models_with_parameter_filtering(async_client, mock_async_httpx_client):
    """Test models API with parameter filtering"""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
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
        'numTotalItems': 2
    }
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response

    response = await async_client.get("/api/v1/models?sort=trending&num_parameters_min=3B&num_parameters_max=256B")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2
    assert 'applied_filters' in data
    assert data['applied_filters']['num_parameters_min'] == '3B'
    assert data['applied_filters']['num_parameters_max'] == '256B'
    
    # Check parameter enhancement
    for model in data['models']:
        assert 'parameterDisplay' in model
        assert 'parameterRange' in model

@pytest.mark.asyncio
async def test_async_api_models_parameter_filtering_min_only(async_client, mock_async_httpx_client):
    """Test models API with minimum parameter filtering only"""
    mock_response = AsyncMock()
    mock_response.json.return_value = [
        {
            'id': 'model1', 
            'numParameters': 24_000_000_000,
            'parameterDisplay': '24B',
            'parameterRange': 'extra_large'
        }
    ]
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response

    response = await async_client.get("/api/v1/models?query=test&num_parameters_min=24B")
    assert response.status_code == 200
    data = response.json()
    assert 'applied_filters' in data
    assert data['applied_filters']['num_parameters_min'] == '24B'
    assert 'num_parameters_max' not in data['applied_filters']

@pytest.mark.asyncio
async def test_async_api_models_parameter_filtering_max_only(async_client, mock_async_httpx_client):
    """Test models API with maximum parameter filtering only"""
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        'models': [
            {
                'id': 'model1', 
                'repoType': 'model',
                'numParameters': 3_000_000_000,
                'parameterDisplay': '3B',
                'parameterRange': 'large'
            }
        ],
        'numTotalItems': 1
    }
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response

    response = await async_client.get("/api/v1/models?sort=trending&num_parameters_max=128B")
    assert response.status_code == 200
    data = response.json()
    assert 'applied_filters' in data
    assert data['applied_filters']['num_parameters_max'] == '128B'
    assert 'num_parameters_min' not in data['applied_filters']

@pytest.mark.asyncio
async def test_async_api_models_invalid_parameter_format(async_client):
    """Test models API with invalid parameter format"""
    response = await async_client.get("/api/v1/models?num_parameters_min=3M")
    assert response.status_code == 400
    data = response.json()
    assert 'INVALID_MIN_PARAMETER_FORMAT' in str(data['detail'])

@pytest.mark.asyncio
async def test_async_api_models_invalid_parameter_range(async_client):
    """Test models API with invalid parameter range"""
    response = await async_client.get("/api/v1/models?num_parameters_min=256B&num_parameters_max=3B")
    assert response.status_code == 400
    data = response.json()
    assert 'INVALID_PARAMETER_RANGE' in str(data['detail'])

@pytest.mark.asyncio
async def test_async_api_model_files(async_client, mock_async_hf_api):
    """Test model files API with async HuggingFace API"""
    mock_repo_info = MagicMock()
    mock_repo_info.siblings = [
        MagicMock(rfilename='file1.txt', size=1000, blob_id='blob1'),
        MagicMock(rfilename='file2.txt', size=2000, blob_id='blob2')
    ]
    
    # Mock the async API call
    with patch('app.services.markets.huggingface.async_huggingface_models.AsyncHuggingFaceService._async_hf_api_call') as mock_call:
        mock_call.return_value = mock_repo_info
        
        response = await async_client.get("/api/v1/models/test-model/files")
        assert response.status_code == 200
        data = response.json()
        assert len(data['files']) == 2
        assert data['files'][0]['name'] == 'file1.txt'
        assert data['files'][1]['name'] == 'file2.txt'

@pytest.mark.asyncio
async def test_async_download_model(async_client, mock_async_hf_hub_download):
    """Test model download with async implementation"""
    # Create temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file_path = temp_file.name

    # Mock async API call
    with patch('app.services.markets.huggingface.async_huggingface_models.AsyncHuggingFaceService._async_hf_api_call') as mock_call:
        mock_call.return_value = temp_file_path
        
        try:
            response = await async_client.get("/api/v1/models/test-model/download?filename=test_file.bin")
            assert response.status_code == 200
            assert response.headers['content-type'] == 'application/octet-stream'
            assert b"Test content" in response.content
        finally:
            # Clean up temporary file
            os.unlink(temp_file_path)

@pytest.mark.asyncio
async def test_async_api_model_detail(async_client):
    """Test model detail API with async implementation"""
    mock_model_info = MagicMock()
    mock_model_info.id = 'test-model'
    mock_model_info.downloads = 1000
    mock_model_info.likes = 100
    mock_model_info.lastModified = '2023-01-01'
    mock_model_info.pipeline_tag = 'text-classification'
    mock_model_info.tags = ['nlp', 'classification']
    
    mock_model_card = MagicMock()
    mock_model_card.data.to_dict.return_value = {'key': 'value'}
    mock_model_card.text = 'Model card text'
    
    with patch('app.services.markets.huggingface.async_huggingface_models.AsyncHuggingFaceService._async_hf_api_call') as mock_call:
        # Mock both API calls
        mock_call.side_effect = [mock_model_info, mock_model_card]
        
        with patch('app.services.markets.huggingface.async_huggingface_models.markdown2.markdown') as mock_markdown:
            mock_markdown.return_value = '<p>Model card HTML</p>'
            
            response = await async_client.get("/api/v1/models/test-model")
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
async def test_async_api_models_error(async_client, mock_async_httpx_client):
    """Test error handling with async client"""
    mock_async_httpx_client.get.side_effect = Exception("Test error")

    response = await async_client.get("/api/v1/models")
    assert response.status_code == 500
    assert "Test error" in response.json()['detail']

@pytest.mark.asyncio
async def test_async_storage_operations(async_client, mock_async_storage_service):
    """Test async storage operations"""
    # Mock storage service methods
    mock_async_storage_service.list_buckets.return_value = [
        {"name": "test-bucket", "creation_date": "2023-01-01T00:00:00Z"}
    ]
    mock_async_storage_service.get_bucket_details.return_value = {
        "name": "test-bucket",
        "creation_date": "2023-01-01T00:00:00Z",
        "object_count": 10,
        "size": 1024
    }
    
    with patch('app.services.async_service_manager.service_manager.get_storage_service') as mock_get_storage:
        mock_get_storage.return_value.__aenter__.return_value = mock_async_storage_service
        
        # Test list buckets
        response = await async_client.get("/api/v1/storage")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]['name'] == 'test-bucket'

@pytest.mark.asyncio 
async def test_async_service_manager_lifecycle():
    """Test async service manager initialization and cleanup"""
    async with service_manager:
        # Test that services are initialized
        assert service_manager._initialized
        assert service_manager.storage_service is not None
        assert service_manager.huggingface_service is not None
        assert service_manager.huggingface_tags_service is not None
        
        # Test context managers
        async with service_manager.get_storage_service() as storage:
            assert storage is not None
            
        async with service_manager.get_huggingface_service() as hf:
            assert hf is not None
            
        async with service_manager.get_huggingface_tags_service() as hf_tags:
            assert hf_tags is not None
    
    # After context exit, services should be cleaned up
    assert not service_manager._initialized

# Performance test
@pytest.mark.asyncio
async def test_async_concurrent_requests(async_client, mock_async_httpx_client):
    """Test concurrent requests performance"""
    import asyncio
    
    mock_response = AsyncMock()
    mock_response.json.return_value = {
        'models': [{'id': 'model1', 'repoType': 'model'}],
        'numTotalItems': 1
    }
    mock_response.raise_for_status.return_value = None
    mock_async_httpx_client.get.return_value = mock_response
    
    # Make 10 concurrent requests
    tasks = []
    for i in range(10):
        task = async_client.get(f"/api/v1/models?sort=trending&page={i}")
        tasks.append(task)
    
    # Execute all requests concurrently
    responses = await asyncio.gather(*tasks)
    
    # Verify all requests succeeded
    for response in responses:
        assert response.status_code == 200
        data = response.json()
        assert len(data['models']) == 1