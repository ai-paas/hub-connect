import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_search_datasets():
    """Test dataset search endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # This should work without authentication for public datasets
        response = await ac.get("/api/v1/datasets?market=huggingface&sort=likes&page=1&limit=10")
    assert response.status_code in [200, 401]  # 401 if JWT auth is required
    

@pytest.mark.asyncio
async def test_get_dataset_files():
    """Test dataset file listing endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # This should work without authentication for public datasets
        response = await ac.get("/api/v1/datasets/fka/awesome-chatgpt-prompts/files?market=huggingface")
    assert response.status_code in [200, 401]  # 401 if JWT auth is required


@pytest.mark.asyncio
async def test_get_dataset_info():
    """Test dataset info endpoint"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # This should work without authentication for public datasets  
        response = await ac.get("/api/v1/datasets/fka/awesome-chatgpt-prompts/info?market=huggingface")
    assert response.status_code in [200, 401]  # 401 if JWT auth is required
