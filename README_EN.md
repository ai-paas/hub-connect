# HUB Connect API

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135.1-green.svg)

[한국어](README.md) | [English](README_EN.md)

HUB Connect API is a FastAPI service that combines Hugging Face and Kaggle model/dataset access with S3-compatible storage management behind a single API.

## What It Does

- Search Hugging Face / Kaggle models and fetch details, files, and downloads
- Fetch Hugging Face / Kaggle tags with background cache warmup/refresh
- Search Hugging Face / Kaggle datasets and download files or snapshots
- Manage buckets, folders, and objects on S3-compatible storage
- Authenticate admin users with JWT
- Enable resumable uploads with Tus when Redis is configured
- Expose `/health`, `/cache/status`, `/cache/refresh`, and `/docs`

## Current Support

| Target | Status | Notes |
|---|---|---|
| Hugging Face models | Supported | Main feature set is implemented |
| Hugging Face datasets | Supported | Search, info, file listing, downloads |
| Kaggle models | Supported | Handle format `owner/model/framework[/variation]`, credentials required |
| Kaggle datasets | Supported | Search, info, file listing, downloads |
| S3-compatible storage | Supported | AWS S3 and Ceph-style configuration |
| Redis + Tus uploads | Optional | Enabled only when Redis is configured |

## Tech Stack

- Python 3.12
- FastAPI 0.135.1, Uvicorn
- Pydantic v2, pydantic-settings
- httpx, aiohttp
- aiobotocore, aiofiles
- redis asyncio client
- tuspyserver
- pytest, pytest-asyncio, httpx
- Docker, Docker Compose

## Compatibility

- Local runtime: Python 3.12
- Docker image: based on `python:3.12-slim`
- `docker-compose.yml` uses `network_mode: host`, so it is better suited to Linux/WSL environments
- Redis is optional, but required for Tus resumable uploads and related large-upload features

## Quick Start

### 1. Prepare Environment Variables

```bash
cp .env.sample .env
```

Minimum values to review:

```env
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=change-this-to-at-least-32-characters

# Kaggle (optional; API tokens require Python 3.11+): market=kaggle returns 503 when unset
KAGGLE_API_TOKEN=
# Set only when using legacy authentication
KAGGLE_USERNAME=
KAGGLE_KEY=

ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_PASSWORD_HASH=

STORAGE_TYPE=aws
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
```

- For production, prefer `ADMIN_PASSWORD_HASH` over `ADMIN_PASSWORD`.
- For Ceph, set `STORAGE_TYPE=ceph` and the `CEPH_*` variables.
- For Redis/Tus, set `REDIS_HOST` and `REDIS_PORT`.

### 2. Run Locally

```bash
pip install -r requirements.txt
python run.py
```

Endpoints:

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- Health: `http://localhost:8001/health`

### 3. Run with Docker

```bash
docker-compose up -d
```

Notes:

- The current Compose file assumes host networking.
- On Docker Desktop for macOS/Windows, networking behavior may differ from Linux.

## Authentication

Login:

```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

Generate a password hash:

```bash
python scripts/generate_password_hash.py your_password
```

## Main API Areas

- `POST /api/v1/auth/login`
- `GET /api/v1/models`
- `GET /api/v1/models/{model_id}`
- `GET /api/v1/models/{model_id}/files`
- `GET /api/v1/models/{model_id}/download`
- `GET /api/v1/tags`
- `GET /api/v1/tags/{group}`
- `GET /api/v1/tags/{group}/all`
- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{repo_id}/info`
- `GET /api/v1/datasets/{repo_id}/files`
- `GET /api/v1/datasets/{repo_id}/download`
- `GET /api/v1/buckets`
- `POST /api/v1/buckets`
- `GET /api/v1/uploads`
- `GET /api/v1/tus/health`

For full request/response details, use `/docs` as the source of truth.

## Tests

```bash
pytest
pytest --cov=app tests/
```

## Project Layout

```text
app/
  api/        # FastAPI routers
  core/       # config, logging, auth
  middleware/ # shared middleware
  schemas/    # response schemas
  services/   # integrations and business logic
  utils/      # helpers
tests/        # pytest suite
scripts/      # utility scripts
```
