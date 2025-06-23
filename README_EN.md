# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

[![Korean](https://img.shields.io/badge/🇰🇷-한국어%20버전-blue)](README.md) 
[![English](https://img.shields.io/badge/🇺🇸-English%20Version-green)](README_EN.md)

The HUB Connect API is an API service designed to connect third-party models to AI-PaaS. It provides an intuitive interface and rich features for easy use of models and data necessary for AI development.

## Main Features

🔍 **Model Search and Lookup**: Easily search and view detailed information about HuggingFace models.

📈 **Trending Models**: Check out popular models that reflect the latest trends.

🏷️ **Tag Management**: Provides a tag system for efficient model classification and search.

📁 **File Management**: Manage files related to models easily.

🚀 **Fast Integration**: Easily integrate into existing systems through RESTful API.

## Supported AI Model Markets

| Market Name | Description | Supported Features | Status |
| --- | --- | --- | --- |
| HuggingFace | Global AI model and data market | Model search, tag search, model download | Supported |
| AI API Data | Korean AI model and data market |     | Coming Soon |

## Quick Start

### Prerequisites

- Python 3.10+

### Installation and Execution

1. Clone the repository:
  
  ```bash
  git clone https://github.com/ai-paas/hub-connect.git
  cd hub-connect
  ```
  
2. Set up the environment:
  
  ```bash
  cp .env.sample .env
  # Open the .env file and modify the necessary settings
  ## HF_API_TOKEN: Hugging Face API token
  ```
  
3. Install dependencies and run:
  
  ```bash
  pip install -r requirements.txt
  python run.py
  ```
  
4. Open your browser and check the API documentation on Swagger UI at `http://localhost:8001/docs`.

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

## Project Structure

```
hub-connect/
├── app/
│   ├── api/
│   │   ├── auth.py          # JWT Authentication API
│   │   ├── models.py        # Model Search/Lookup API
│   │   ├── storage.py       # File Storage API
│   │   └── tags.py          # Tag Management API
│   ├── core/
│   │   ├── auth.py          # Authentication Middleware
│   │   ├── config.py        # Configuration Management
│   │   └── logging.py       # Logging System
│   ├── services/
│   │   ├── auth_service.py  # Authentication Service
│   │   ├── storage_service.py # Storage Service
│   │   ├── markets/
│   │   │   ├── aihub/
│   │   │   │   ├── aihub_models.py
│   │   │   │   └── aihub_tags.py
│   │   │   ├── huggingface/
│   │   │   │   ├── huggingface_models.py
│   │   │   │   └── huggingface_tags.py
│   │   │   └── common.py
│   │   └── caching.py
│   ├── utils/
│   │   ├── error_handlers.py # Error Handling Utilities
│   │   └── helpers.py
│   └── main.py
├── scripts/
│   └── generate_password_hash.py # Password Hash Generator
├── tests/
├── .env.sample
├── .gitignore
├── CLAUDE.md           # Developer Guide
├── README.md
├── README_EN.md
├── requirements.txt
└── run.py
```

## API Documentation

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

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