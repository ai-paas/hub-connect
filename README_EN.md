# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

[![Korean](https://img.shields.io/badge/🇰🇷-한국어%20버전-blue)](README.md) 
[![English](https://img.shields.io/badge/🇺🇸-English%20Version-green)](README_EN.md)

HUB Connect API is a unified API service that connects various AI model marketplaces (HuggingFace, AI Hub) to AI-PaaS platforms. It provides intuitive RESTful APIs and S3-compatible storage for seamless AI model search, download, and storage operations.

## Key Features

🔍 **Unified Model Search**: Integrated search across multiple marketplaces like HuggingFace with detailed model information and metadata.

📈 **Trending Models**: Real-time access to popular and trending AI models across supported platforms.

🏷️ **Smart Tag System**: Hierarchical tag system for efficient model classification and filtering capabilities.

☁️ **S3-Compatible Storage**: Support for AWS S3, Ceph, and other S3-compatible storage systems for file upload/download/management.

🔐 **JWT Security**: Robust JWT token-based authentication system ensuring secure API access.

⚡ **High-Performance Async**: All I/O operations are asynchronous for optimal performance and scalability.

🛡️ **Reliability Features**: Rate limiting, circuit breaker, request timeout, and other stability mechanisms.

🚀 **Easy Integration**: RESTful API with Docker support for seamless integration into existing systems.

## Supported AI Model Markets

| Market Name | Description | Supported Features | Status |
|-------------|-------------|-------------------|--------|
| HuggingFace | Global AI model and data marketplace | Model search, tag search, model download, trending models | ✅ Full Support |
| AI Hub | Korean AI model and data marketplace | Model search, tag search, model download | 🚧 In Development |

## Technology Stack

| Category | Technologies |
|----------|-------------|
| **Backend** | FastAPI, Python 3.10+, Uvicorn |
| **Authentication** | JWT (python-jose), bcrypt |
| **Storage** | AWS S3, Ceph S3-compatible |
| **Caching** | aiocache (In-memory) |
| **Testing** | pytest, httpx |
| **Deployment** | Docker, Docker Compose |
| **Monitoring** | Structured logging, Health checks |

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
- `GET /api/v1/storage` - List storage services
- `POST /api/v1/storage/{name}/upload` - Upload files
- `GET /api/v1/storage/{name}/download/{key}` - Download files
- `DELETE /api/v1/storage/{name}/{key}` - Delete files

## Environment Variables

Required environment variables:
```env
# API Tokens
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=your_jwt_secret_key

# Admin Account
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123  # Development
ADMIN_PASSWORD_HASH=     # Production

# Storage Configuration (AWS S3 example)
STORAGE_TYPE=aws
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
AWS_S3_BUCKET=your-bucket-name
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
- Rate Limiting: 200 requests per minute per IP
- Circuit Breaker: Automatic protection against external API failures
- Request Timeout: 5-minute request timeout
- Health Check: Service status check via `/` endpoint

## Contributing

Contribute to the development of HUB Connect API! You can participate by following these steps:

1. Fork this repository
2. Create a new feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a pull request

## License

This project is licensed under the Apache License 2.0. For more details, see the [LICENSE](LICENSE) file.

## Contact

Project link: [https://github.com/ai-paas/hub-connect](https://github.com/ai-paas/hub-connect)

## Acknowledgments

- To all contributors