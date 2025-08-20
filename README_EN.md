# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

[![Korean](https://img.shields.io/badge/🇰🇷-한국어%20버전-blue)](README.md) 
[![English](https://img.shields.io/badge/🇺🇸-English%20Version-green)](README_EN.md)

HUB Connect API is a unified API service that connects various AI model marketplaces (HuggingFace, AI Hub) to AI-PaaS platforms. It provides intuitive RESTful APIs and S3-compatible storage for seamless AI model search, download, and storage operations.

## Overview

HUB Connect API is an enterprise-grade AI model management platform that provides unified management of AI models from multiple marketplaces and complete model lifecycle management through S3-compatible storage. Built on asynchronous architecture and microservices patterns, it ensures high performance and scalability.

## Key Features

### 🔍 **Unified Model Search & Management**
- **Multi-Marketplace Integration**: Unified search across various AI model marketplaces like HuggingFace and AI Hub
- **Comprehensive Metadata**: Complete model metadata including information, file lists, download URLs
- **Trending Models**: Real-time popular and trending model information
- **Advanced Filtering**: Model filtering by tags, categories, licenses, and other criteria

### 🏷️ **Smart Tag System**
- **Hierarchical Tag Structure**: Multi-level tag system for efficient model classification
- **Dynamic Tag Management**: Real-time tag updates and group-based tag management
- **Tag-Based Search**: Precise model search and filtering using tags

### ☁️ **Enterprise-Grade Storage Management**
- **S3-Compatible Storage**: Support for AWS S3, Ceph, and other S3-compatible storage systems
- **Bucket Management**: Bucket creation, deletion, detailed information retrieval (capacity, object count)
- **Folder Management**: Complete folder management including creation, deletion, renaming, copying
- **Large File Upload**: Multipart upload support for large files (>100MB)
- **Upload Progress Tracking**: Real-time upload progress tracking and cancellation functionality
- **Batch Operations**: Batch operation support for bulk object management (1000 objects per batch)

### 🔐 **Enterprise Security**
- **JWT-Based Authentication**: Robust JWT token-based authentication system
- **Dual Authentication Modes**: Development/production environment-specific authentication modes
- **Input Validation**: Complete input validation using Pydantic models
- **Security Headers**: Compliance with web security standards including CORS and security headers

### ⚡ **High-Performance Architecture**
- **Full Asynchronous Processing**: High performance through asynchronous processing of all I/O operations
- **Connection Pooling**: External API call optimization through HTTP connection pooling (max 50 connections)
- **Smart Caching**: Data integrity assurance through SHA256-based cache validation
- **Response Compression**: Network optimization through gzip compression
- **Async Tree Structure**: Asynchronous pagination for hierarchical storage structures

### 🛡️ **Reliability & Monitoring**
- **Rate Limiting**: IP-based request limiting (default 200 requests/minute)
- **Circuit Breaker**: Automatic protection mechanism against external API failures
- **Request Timeout**: Per-request timeout configuration (default 5 minutes)
- **Structured Logging**: JSON-formatted structured logs and request tracking
- **Health Check**: Service status monitoring and health check endpoints

### 🚀 **Operational Efficiency**
- **Docker Optimization**: Performance optimization through host network mode
- **Multi-Process Support**: High-performance multi-process execution support
- **Automatic Log Rotation**: Automatic log file rotation in 10MB units
- **Performance Benchmarks**: Built-in performance benchmark tools

## Supported AI Model Markets

| Market Name | Description | Supported Features | Status |
|-------------|-------------|-------------------|--------|
| HuggingFace | Global AI model and data marketplace | Model search, tag search, model download, trending models | ✅ Full Support |
| AI Hub | Korean AI model and data marketplace | Model search, tag search, model download | 🚧 In Development |

## Architecture & Technology Stack

### 🏗️ **Architecture Design**
- **Microservices Architecture**: Clear separation of concerns and modularization
- **Async-First Architecture**: Asynchronous processing throughout the application stack
- **Factory Pattern**: Factory pattern for market service instantiation
- **Repository Pattern**: Repository pattern for data access and storage operations
- **Middleware Pipeline**: Cross-cutting concerns handling for logging, rate limiting, authentication

### 💻 **Technology Stack**

| Category | Technologies | Description |
|----------|-------------|-------------|
| **Backend** | FastAPI, Python 3.10+, Uvicorn | High-performance asynchronous web framework |
| **Authentication** | JWT (python-jose), bcrypt | Token-based authentication and password hashing |
| **Storage** | AWS S3, Ceph S3-compatible, aiobotocore | Asynchronous S3 client |
| **Caching** | aiocache (In-memory) | Asynchronous in-memory caching |
| **HTTP Client** | httpx | Asynchronous HTTP client |
| **Data Validation** | Pydantic | Data validation and settings management |
| **Testing** | pytest, httpx | Testing framework |
| **Deployment** | Docker, Docker Compose | Containerization and orchestration |
| **Monitoring** | Structured logging, Health checks | JSON logging and health checks |

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (optional, recommended)

### Method 1: Docker Setup (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/ai-paas/hub-connect.git
   cd hub-connect
   ```

2. Environment configuration:
   ```bash
   cp .env.sample .env
   # Edit .env file with required settings:
   # - HF_API_TOKEN: HuggingFace API token
   # - SECRET_KEY: JWT secret key
   # - Storage settings (AWS S3 or Ceph)
   ```

3. Run with Docker:
   ```bash
   docker-compose up -d
   ```

4. Access API documentation:
   - Swagger UI: http://localhost:8001/docs
   - ReDoc: http://localhost:8001/redoc

### Method 2: Python Direct Execution

1. Clone repository and configure environment (same as above)

2. Install dependencies and run:
   ```bash
   pip install -r requirements.txt
   python run.py
   ```

### Initial Login

Login with default admin account:
```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

## Authentication Setup

HUB Connect API uses JWT-based authentication. All API endpoints require authentication.

### Development Environment (Default)

The development environment configuration is applied by default:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_PASSWORD_HASH=
```

### Login Method

1. **Obtain Token**:
   ```bash
   curl -X 'POST' \
     'http://localhost:8001/api/v1/auth/login' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=admin&password=admin123'
   ```

2. **Response Example**:
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "token_type": "bearer"
   }
   ```

3. **Use Token in API Calls**:
   ```bash
   curl -X 'GET' \
     'http://localhost:8001/api/v1/models?market=huggingface' \
     -H 'Authorization: Bearer your_access_token'
   ```

### Production Environment Setup

For security, use hashed passwords in production:

1. **Generate Password Hash**:
   ```bash
   python scripts/generate_password_hash.py your_secure_password
   ```

2. **Update .env File**:
   ```env
   ADMIN_USERNAME=admin
   # ADMIN_PASSWORD=admin123  # Remove or comment out
   ADMIN_PASSWORD_HASH=generated_hash_value
   ```

3. **Login**: Use the original password to login:
   ```bash
   curl -X 'POST' \
     'http://localhost:8001/api/v1/auth/login' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=admin&password=your_secure_password'
   ```

## API Endpoints

### Authentication
- `POST /api/v1/auth/login` - Obtain JWT token

### Model Management
- `GET /api/v1/models` - Search/list models with filtering
- `GET /api/v1/models/{id}` - Get model details
- `GET /api/v1/models/{id}/files` - List model files
- `GET /api/v1/models/{id}/download` - Download model files

### Tag Management
- `GET /api/v1/tags` - Get all tags
- `GET /api/v1/tags/{group}` - Get tags by group

### Storage Management

#### Bucket Management
- `GET /api/v1/buckets` - List all buckets
- `POST /api/v1/buckets` - Create a new bucket
- `GET /api/v1/buckets/{bucket_id}` - Get bucket details (including object count and total size)
- `DELETE /api/v1/buckets/{bucket_id}` - Delete a bucket and all its contents

#### Folder Management
- `GET /api/v1/buckets/{bucket_id}/objects` - List folder contents in a tree structure (use `prefix` and `depth` queries)
- `POST /api/v1/buckets/{bucket_id}/folders` - Create an empty folder
- `DELETE /api/v1/buckets/{bucket_id}/folders/{folder_path:path}` - Delete a folder and all its contents
- `PUT /api/v1/buckets/{bucket_id}/folders/{folder_path:path}` - Rename/move a folder
- `POST /api/v1/buckets/{bucket_id}/folders/{folder_path:path}/copy` - Copy a folder
- `GET /api/v1/buckets/{bucket_id}/folders/{folder_path:path}/stats` - Get folder statistics (total size, file count, folder count)

#### Object Management
- `POST /api/v1/buckets/{bucket_id}/objects` - Upload an object (supports large files with multipart upload)
- `GET /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - Download an object
- `PUT /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - Rename/move an object
- `POST /api/v1/buckets/{bucket_id}/objects/{object_key:path}/copy` - Copy an object
- `DELETE /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - Delete an object

#### Upload Progress Tracking
- `GET /api/v1/uploads` - List all ongoing/completed/failed uploads
- `GET /api/v1/uploads/{upload_id}` - Get detailed progress for a specific upload
- `DELETE /api/v1/uploads/{upload_id}` - Cancel an ongoing upload

## Environment Variables

### Required Environment Variables
```env
# API Tokens
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=your_jwt_secret_key

# Admin Account
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123  # Development
ADMIN_PASSWORD_HASH=     # Production

# Storage Configuration (Choose AWS S3 or Ceph)
STORAGE_TYPE=aws # or ceph
```

### AWS S3 Configuration
```env
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
AWS_S3_BUCKET=your-bucket-name
```

### Ceph S3-Compatible Configuration
```env
CEPH_S3_ENDPOINT=https://your-ceph-endpoint
CEPH_ACCESS_KEY=your_access_key
CEPH_SECRET_KEY=your_secret_key
CEPH_BUCKET=your-bucket-name
```

### Performance & Security Settings
```env
# Caching Configuration
CACHE_TIMEOUT=3600              # Cache timeout (seconds)
GROUPS=default,premium          # User groups
LIMITED_GROUPS=free            # Limited groups

# Rate Limiting (requests per minute)
RATE_LIMIT=200

# Logging Configuration
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# JWT Configuration
ACCESS_TOKEN_EXPIRE_MINUTES=30  # JWT token expiration time (minutes)

# CORS Configuration
ALLOWED_ORIGINS=["*"]           # Allowed origins
```

## Project Structure

```
hub-connect/
├── app/
│   ├── api/              # API endpoints
│   │   ├── auth.py       # JWT authentication
│   │   ├── models.py     # Model search/lookup
│   │   ├── storage.py    # S3 storage management
│   │   └── tags.py       # Tag system
│   ├── core/             # Core modules
│   │   ├── auth.py       # Auth middleware
│   │   ├── config.py     # Configuration
│   │   └── logging.py    # Logging system
│   ├── services/         # Business logic
│   │   ├── markets/      # Marketplace integration
│   │   │   ├── common.py # Factory pattern
│   │   │   ├── huggingface/ # HF implementation
│   │   │   └── aihub/    # AIHub implementation
│   │   ├── auth_service.py
│   │   ├── storage_service.py
│   │   ├── caching.py
│   │   └── upload_tracker.py
│   ├── utils/            # Utilities
│   │   ├── circuit_breaker.py
│   │   ├── error_handlers.py
│   │   └── helpers.py
│   ├── middleware/       # Middleware
│   │   └── rate_limit.py
│   └── main.py           # FastAPI app
├── tests/                # Test code
├── scripts/              # Utility scripts
├── logs/                 # Log files
├── data/                 # Data directory
├── Dockerfile            # Docker build
├── docker-compose.yml    # Docker Compose
├── .env.sample           # Environment template
└── requirements.txt      # Python dependencies
```

## API Documentation

- **Swagger UI**: http://localhost:8001/docs - Interactive API documentation
- **ReDoc**: http://localhost:8001/redoc - Clean API documentation

## Monitoring and Logs

### Log File Locations
- `logs/app.log` - Application logs
- `logs/api_calls.log` - API call logs
- `logs/error.log` - Error logs

### Docker Log Checking
```bash
# Real-time log monitoring
docker-compose logs -f hub-connect-api

# Recent logs
docker-compose logs --tail=100 hub-connect-api
```

### Performance Monitoring
- **Rate Limiting**: 200 requests per minute per IP (configurable)
- **Circuit Breaker**: Automatic protection and recovery against external API failures
- **Request Timeout**: 5-minute request timeout (supports long-running operations)
- **Connection Pooling**: Up to 50 connection pooling for external API optimization
- **Async Tree Building**: Improved response times through asynchronous storage tree structure building
- **Health Check**: Service status check via `/` endpoint

### Performance Benchmark Execution
```bash
# Run performance benchmarks
python benchmarks/performance_benchmark.py

# Run performance test scripts
python scripts/run_performance_test.py
```

## Testing

### Running All Tests
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/api/test_models.py

# Run async tests
pytest tests/api/test_async_models.py
```

### Test Environment
- Tests automatically load the `.env` file
- External API calls are handled with mocks
- Temporary file support for download testing

## Latest Improvements (January 2025)

### 🚀 **Major Feature Additions**
- **Complete S3 Bucket Management**: Bucket creation, deletion, detailed statistics retrieval
- **Advanced Folder Management**: Folder creation, deletion, renaming, copying functionality
- **Upload Cancellation**: Real-time cancellation and status tracking for ongoing uploads
- **Batch Object Management**: Optimized bulk object management for 1000 objects per batch

### ⚡ **Performance Optimizations**
- **Host Network Mode**: Significant performance improvements through Docker host networking
- **Async Storage Tree**: Improved response times through asynchronous hierarchical storage structure building
- **Request Timeout Middleware**: Enhanced timeout handling for long-running operations
- **Multi-Process Support**: High-performance multi-process execution environment

### 🛡️ **Security & Stability Enhancements**
- **Safe Logging**: Logging protection mechanisms for binary file uploads
- **Enhanced Error Handling**: Centralized error logging and handling system
- **Dual Authentication Mode**: Optimized authentication flow for development/production environments

## Contributing

Contribute to the development of HUB Connect API! You can participate by following these steps:

1. Fork this repository
2. Create a new feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a pull request

### Development Guidelines
- Write test code for all new features
- API endpoints must comply with OpenAPI schema
- Maintain async patterns and consider performance optimization
- Follow security best practices

## License

This project is licensed under the Apache License 2.0. For more details, see the [LICENSE](LICENSE) file.

## Contact

Project link: [https://github.com/ai-paas/hub-connect](https://github.com/ai-paas/hub-connect)

## Acknowledgments

- To all contributors
- HuggingFace community
- FastAPI and Python ecosystem

---

⭐️ If this project helped you, please give it a star!