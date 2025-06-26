# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

[![Korean](https://img.shields.io/badge/🇰🇷-한국어%20버전-blue)](README.md) 
[![English](https://img.shields.io/badge/🇺🇸-English%20Version-green)](README_EN.md)

HUB Connect API는 다양한 AI 모델 마켓플레이스(HuggingFace, AI Hub)를 AI-PaaS 플랫폼에 연결하는 통합 API 서비스입니다.
직관적인 RESTful API와 S3 호환 저장소를 통해 AI 모델의 검색, 다운로드, 저장을 손쉽게 처리할 수 있습니다.

## 주요 기능

🔍 **통합 모델 검색**: HuggingFace 등 다중 마켓플레이스에서 AI 모델을 통합 검색하고 상세 정보를 조회할 수 있습니다.

📈 **트렌딩 모델**: 최신 트렌드를 반영한 인기 모델을 실시간으로 확인할 수 있습니다.

🏷️ **스마트 태그 시스템**: 효율적인 모델 분류와 검색을 위한 계층형 태그 시스템을 제공합니다.

☁️ **S3 호환 저장소**: AWS S3, Ceph 등 S3 호환 저장소를 통한 파일 업로드/다운로드/관리 기능을 제공합니다.

🔐 **JWT 기반 보안**: 강력한 JWT 토큰 기반 인증 시스템으로 안전한 API 액세스를 보장합니다.

⚡ **고성능 비동기 처리**: 모든 I/O 작업을 비동기로 처리하여 높은 성능을 제공합니다.

🛡️ **안정성 보장**: Rate Limiting, Circuit Breaker, Request Timeout 등으로 서비스 안정성을 보장합니다.

🚀 **빠른 통합**: RESTful API와 Docker 지원으로 기존 시스템에 쉽게 통합할 수 있습니다.

## 지원하는 AI 모델 마켓

| 마켓 이름       | 설명                  | 지원 기능                        | 상태   |
|-------------|---------------------|------------------------------|------|
| HuggingFace | 글로벌 AI 모델 및 데이터 마켓  | 모델 검색, 태그 검색, 모델 다운로드, 트렌딩 모델 | ✅ 완전 지원 |
| AI Hub      | 대한민국 AI 모델 및 데이터 마켓 | 모델 검색, 태그 검색, 모델 다운로드        | 🚧 개발 중 |

## 기술 스택

| 분야 | 기술 스택 |
|------|----------|
| **백엔드** | FastAPI, Python 3.10+, Uvicorn |
| **인증** | JWT (python-jose), bcrypt |
| **저장소** | AWS S3, Ceph S3-compatible |
| **캐싱** | aiocache (In-memory) |
| **테스트** | pytest, httpx |
| **배포** | Docker, Docker Compose |
| **모니터링** | 구조화된 로깅, Health Check |

## 빠른 시작

### 전제 조건

- Python 3.10+
- Docker & Docker Compose (선택사항, 권장)

### 방법 1: Docker로 실행 (권장)

1. 리포지토리 클론:
   ```bash
   git clone https://github.com/ai-paas/hub-connect.git
   cd hub-connect
   ```

2. 환경 설정:
   ```bash
   cp .env.sample .env
   # .env 파일 편집하여 필수 설정 추가:
   # - HF_API_TOKEN: HuggingFace API 토큰
   # - SECRET_KEY: JWT 시크릿 키
   # - 저장소 설정 (AWS S3 또는 Ceph)
   ```

3. Docker로 실행:
   ```bash
   docker-compose up -d
   ```

4. API 문서 확인:
   - Swagger UI: http://localhost:8001/docs
   - ReDoc: http://localhost:8001/redoc

### 방법 2: Python으로 직접 실행

1. 리포지토리 클론 및 환경 설정 (위와 동일)

2. 의존성 설치 및 실행:
   ```bash
   pip install -r requirements.txt
   python run.py
   ```

### 초기 로그인

기본 관리자 계정으로 로그인:
```bash
curl -X POST http://localhost:8001/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123"
```

## 인증 설정

HUB Connect API는 JWT 기반 인증을 사용합니다. 모든 API 엔드포인트는 인증이 필요합니다.

### 개발 환경 (기본값)

기본적으로 개발 환경용 설정이 적용되어 있습니다:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_PASSWORD_HASH=
```

### 로그인 방법

1. **토큰 획득**:
   ```bash
   curl -X 'POST' \
     'http://localhost:8001/api/v1/auth/login' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=admin&password=admin123'
   ```

2. **응답 예시**:
   ```json
   {
     "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
     "token_type": "bearer"
   }
   ```

3. **API 호출 시 토큰 사용**:
   ```bash
   curl -X 'GET' \
     'http://localhost:8001/api/v1/models?market=huggingface' \
     -H 'Authorization: Bearer your_access_token'
   ```

### 프로덕션 환경 설정

보안을 위해 프로덕션에서는 해시된 비밀번호를 사용하세요:

1. **비밀번호 해시 생성**:
   ```bash
   python scripts/generate_password_hash.py your_secure_password
   ```

2. **.env 파일 업데이트**:
   ```env
   ADMIN_USERNAME=admin
   # ADMIN_PASSWORD=admin123  # 제거 또는 주석 처리
   ADMIN_PASSWORD_HASH=생성된_해시값
   ```

3. **로그인**: 원래 비밀번호로 로그인하면 됩니다:
   ```bash
   curl -X 'POST' \
     'http://localhost:8001/api/v1/auth/login' \
     -H 'Content-Type: application/x-www-form-urlencoded' \
     -d 'username=admin&password=your_secure_password'
   ```

## API 엔드포인트

### 인증
- `POST /api/v1/auth/login` - JWT 토큰 획득

### 모델 관리
- `GET /api/v1/models` - 모델 검색/목록 조회
- `GET /api/v1/models/{id}` - 모델 상세 정보
- `GET /api/v1/models/{id}/files` - 모델 파일 목록
- `GET /api/v1/models/{id}/download` - 모델 파일 다운로드

### 태그 관리
- `GET /api/v1/tags` - 전체 태그 목록
- `GET /api/v1/tags/{group}` - 그룹별 태그 조회

### 저장소 관리
- `GET /api/v1/storage` - 저장소 목록
- `POST /api/v1/storage/{name}/upload` - 파일 업로드
- `GET /api/v1/storage/{name}/download/{key}` - 파일 다운로드
- `DELETE /api/v1/storage/{name}/{key}` - 파일 삭제

## 환경 변수 설정

필수 환경 변수:
```env
# API 토큰
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=your_jwt_secret_key

# 관리자 계정
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123  # 개발용
ADMIN_PASSWORD_HASH=     # 프로덕션용

# 저장소 설정 (AWS S3 예시)
STORAGE_TYPE=aws
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
AWS_S3_BUCKET=your-bucket-name
```

## 프로젝트 구조

```
hub-connect/
├── app/
│   ├── api/              # API 엔드포인트
│   │   ├── auth.py       # JWT 인증
│   │   ├── models.py     # 모델 검색/조회
│   │   ├── storage.py    # S3 저장소 관리
│   │   └── tags.py       # 태그 시스템
│   ├── core/             # 핵심 모듈
│   │   ├── auth.py       # 인증 미들웨어
│   │   ├── config.py     # 설정 관리
│   │   └── logging.py    # 로깅 시스템
│   ├── services/         # 비즈니스 로직
│   │   ├── markets/      # 마켓플레이스 통합
│   │   │   ├── common.py # 팩토리 패턴
│   │   │   ├── huggingface/ # HF 구현
│   │   │   └── aihub/    # AIHub 구현
│   │   ├── auth_service.py
│   │   ├── storage_service.py
│   │   ├── caching.py
│   │   └── upload_tracker.py
│   ├── utils/            # 유틸리티
│   │   ├── circuit_breaker.py
│   │   ├── error_handlers.py
│   │   └── helpers.py
│   ├── middleware/       # 미들웨어
│   │   └── rate_limit.py
│   └── main.py           # FastAPI 앱
├── tests/                # 테스트 코드
├── scripts/              # 유틸리티 스크립트
├── logs/                 # 로그 파일
├── data/                 # 데이터 디렉토리
├── Dockerfile            # Docker 빌드
├── docker-compose.yml    # Docker Compose
├── .env.sample           # 환경 변수 템플릿
└── requirements.txt      # Python 의존성
```

## API 문서

- **Swagger UI**: http://localhost:8001/docs - 대화형 API 문서
- **ReDoc**: http://localhost:8001/redoc - 깔끔한 API 문서

## 모니터링 및 로그

### 로그 파일 위치
- `logs/app.log` - 애플리케이션 로그
- `logs/api_calls.log` - API 호출 로그  
- `logs/error.log` - 에러 로그

### Docker 로그 확인
```bash
# 실시간 로그 확인
docker-compose logs -f hub-connect-api

# 최근 로그 확인
docker-compose logs --tail=100 hub-connect-api
```

### 성능 모니터링
- Rate Limiting: IP당 분당 200회 요청 제한
- Circuit Breaker: 외부 API 장애 시 자동 차단
- Request Timeout: 5분 요청 타임아웃
- Health Check: `/` 엔드포인트를 통한 서비스 상태 확인

## 기여하기

HUB Connect API의 발전에 기여해주세요! 다음과 같은 방법으로 참여할 수 있습니다: 

1. 이 저장소를 Fork하세요
2. 새로운 Feature 브랜치를 만드세요 (`git checkout -b feature/AmazingFeature`)
3. 변경사항을 Commit하세요 (`git commit -m 'Add some AmazingFeature'`)
4. 브랜치에 Push하세요 (`git push origin feature/AmazingFeature`)
5. Pull Request를 열어주세요

## 라이선스

이 프로젝트는 Apache License 2.0에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 연락처

프로젝트 링크: [https://github.com/ai-paas/hub-connect](https://github.com/ai-paas/hub-connect)

## 감사의 말

- 모든 기여자 분들

---

⭐️ 이 프로젝트가 도움이 되었다면 스타를 눌러주세요!
