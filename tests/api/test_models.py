import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv

# 테스트 시작 전에 .env 파일 로드
load_dotenv()

# 환경 변수가 제대로 로드되었는지 확인 (디버깅 목적)
print(f"HF_API_TOKEN: {'*' * len(os.getenv('HF_API_TOKEN', ''))}")  # 토큰 값을 직접 출력하지 않고 길이만 표시

from app.main import app
from app.api import models

client = TestClient(app)

@pytest.fixture
def mock_requests():
    with patch('app.api.models.requests') as mock:
        yield mock

@pytest.fixture
def mock_hf_api():
    with patch('app.api.models.hf_api') as mock:
        yield mock

@pytest.fixture
def mock_hf_hub_download():
    with patch('app.api.models.hf_hub_download') as mock:
        yield mock

def test_api_models_trending(mock_requests):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'models': [
            {'id': 'model1', 'repoType': 'model'},
            {'id': 'model2', 'repoType': 'model'}
        ],
        'numTotalItems': 2
    }
    mock_requests.get.return_value = mock_response

    response = client.get("/api/v1/models?sort=trending")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2

def test_api_models_search(mock_requests):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {'id': 'model1'}, {'id': 'model2'}
    ]
    mock_requests.get.return_value = mock_response

    response = client.get("/api/v1/models?query=test&sort=downloads")
    assert response.status_code == 200
    data = response.json()
    assert len(data['models']) == 2
    assert data['total'] == 2

def test_api_model_files(mock_hf_api):
    mock_repo_info = MagicMock()
    mock_repo_info.siblings = [
        MagicMock(rfilename='file1.txt', size=1000, blob_id='blob1'),
        MagicMock(rfilename='file2.txt', size=2000, blob_id='blob2')
    ]
    mock_hf_api.repo_info.return_value = mock_repo_info

    response = client.get("/api/v1/models/test-model/files")
    assert response.status_code == 200
    data = response.json()
    assert len(data['files']) == 2
    assert data['files'][0]['name'] == 'file1.txt'
    assert data['files'][1]['name'] == 'file2.txt'

@patch('app.api.models.hf_hub_download')
def test_download_model(mock_hf_hub_download):
    # 임시 파일 생성
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_file.write(b"Test content")
        temp_file_path = temp_file.name

    mock_hf_hub_download.return_value = temp_file_path

    try:
        response = client.get("/api/v1/models/test-model/download?filename=test_file.bin")
        assert response.status_code == 200
        assert response.headers['content-type'] == 'application/octet-stream'
        assert response.headers['content-disposition'] == 'attachment; filename="test_file.bin"'
        assert response.content == b"Test content"
    finally:
        # 테스트 후 임시 파일 삭제
        os.unlink(temp_file_path)

@patch('app.api.models.get_model_info')
@patch('app.api.models.get_model_card')
@patch('app.api.models.markdown2.markdown')
def test_api_model_detail(mock_markdown, mock_get_model_card, mock_get_model_info):
    mock_get_model_info.return_value = MagicMock(
        id='test-model',
        downloads=1000,
        likes=100,
        lastModified='2023-01-01',
        pipeline_tag='text-classification',
        tags=['nlp', 'classification']
    )
    mock_get_model_card.return_value = ({'key': 'value'}, 'Model card text')
    mock_markdown.return_value = '<p>Model card HTML</p>'

    response = client.get("/api/v1/models/test-model")
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

def test_api_models_error(mock_requests):
    mock_requests.get.side_effect = Exception("Test error")

    response = client.get("/api/v1/models")
    assert response.status_code == 500
    assert "Test error" in response.json()['detail']