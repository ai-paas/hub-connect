# HUB Connect API

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.135.1-green.svg)

[한국어](README.md) | [English](README_EN.md)

HUB Connect API는 Hugging Face · Kaggle 모델/데이터셋 조회와 S3 호환 스토리지 관리를 하나의 FastAPI 서비스로 묶은 API 서버입니다.

## 핵심 기능

- Hugging Face / Kaggle 모델 검색, 상세 조회, 파일 목록, 파일 다운로드
- Hugging Face / Kaggle 태그 조회와 백그라운드 캐시 갱신
- Hugging Face / Kaggle 데이터셋 검색, 정보 조회, 파일 목록, 파일/스냅샷 다운로드
- S3 호환 스토리지 버킷/폴더/객체 관리
- JWT 기반 관리자 인증
- Redis 사용 시 Tus 기반 재개 가능한 업로드
- `/health`, `/cache/status`, `/cache/refresh`, `/docs` 제공

## 현재 지원 범위

| 대상 | 상태 | 비고 |
|---|---|---|
| Hugging Face models | 지원 | 주요 기능 구현됨 |
| Hugging Face datasets | 지원 | 검색, 정보, 파일 목록, 다운로드 |
| Kaggle models | 지원 | 핸들 형식 `owner/model/framework[/variation]`, 자격증명 필요 |
| Kaggle datasets | 지원 | 검색, 정보, 파일 목록, 다운로드 |
| S3-compatible storage | 지원 | AWS S3, Ceph 스타일 설정 지원 |
| Redis + Tus uploads | 선택 기능 | Redis 설정 시 활성화 |

## 기술 스택

- Python 3.12
- FastAPI 0.135.1, Uvicorn
- Pydantic v2, pydantic-settings
- httpx, aiohttp
- aiobotocore, aiofiles
- redis-py asyncio
- tuspyserver
- pytest, pytest-asyncio, httpx
- Docker, Docker Compose

## 호환성

- 로컬 실행: Python 3.12
- Docker 이미지: Python 3.12-slim 기반
- Docker Compose 설정은 `network_mode: host`를 사용하므로 Linux/WSL 환경에 더 적합합니다.
- Redis는 선택 사항이지만, 재개 업로드(Tus)와 일부 대용량 업로드 기능에는 필요합니다.

## 빠른 시작

### 1. 환경 변수 준비

```bash
cp .env.sample .env
```

최소 확인 항목:

```env
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=change-this-to-at-least-32-characters

# Kaggle 연동(선택): 미설정시 market=kaggle 호출은 503 응답
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

- 프로덕션에서는 `ADMIN_PASSWORD` 대신 `ADMIN_PASSWORD_HASH` 사용을 권장합니다.
- Ceph를 쓰는 경우 `STORAGE_TYPE=ceph`와 `CEPH_*` 값을 설정합니다.
- Redis를 쓰는 경우 `REDIS_HOST`, `REDIS_PORT`를 설정합니다.

### 2. 로컬 실행

```bash
pip install -r requirements.txt
python run.py
```

접속:

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`
- Health: `http://localhost:8001/health`

### 3. Docker 실행

```bash
docker-compose up -d
```

주의:

- 현재 `docker-compose.yml`은 host network 기준으로 작성되어 있습니다.
- macOS/Windows Docker Desktop에서는 네트워크 동작이 Linux와 다를 수 있습니다.

## 인증

로그인:

```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

해시 비밀번호 생성:

```bash
python scripts/generate_password_hash.py your_password
```

## 주요 API

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

상세 스키마와 요청 예시는 `/docs`를 기준으로 확인하는 편이 가장 정확합니다.

## 테스트

```bash
pytest
pytest --cov=app tests/
```

## 프로젝트 구조

```text
app/
  api/        # FastAPI 라우터
  core/       # 설정, 로깅, 인증
  middleware/ # 공통 미들웨어
  schemas/    # 응답 스키마
  services/   # 외부 연동 및 비즈니스 로직
  utils/      # 보조 유틸리티
tests/        # pytest 테스트
scripts/      # 운영/개발 스크립트
```
