# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

[![Korean](https://img.shields.io/badge/🇰🇷-한국어%20버전-blue)](README.md) 
[![English](https://img.shields.io/badge/🇺🇸-English%20Version-green)](README_EN.md)

HUB Connect API는 다양한 AI 모델 마켓플레이스(HuggingFace, AI Hub)를 AI-PaaS 플랫폼에 연결하는 통합 API 서비스입니다.
직관적인 RESTful API와 S3 호환 저장소를 통해 AI 모델의 검색, 다운로드, 저장을 손쉽게 처리할 수 있습니다.

## 개요

HUB Connect API는 엔터프라이즈급 AI 모델 관리 플랫폼으로, 다중 마켓플레이스에서 AI 모델을 통합 관리하고 S3 호환 저장소를 통한 완전한 모델 라이프사이클 관리를 제공합니다. 비동기 아키텍처와 마이크로서비스 패턴을 기반으로 구축되어 높은 성능과 확장성을 보장합니다.

## 주요 기능

### 🔍 **통합 모델 검색 & 관리**
- **다중 마켓플레이스 통합**: HuggingFace, AI Hub 등 다양한 AI 모델 마켓플레이스를 통합 검색
- **상세 메타데이터**: 모델 정보, 파일 목록, 다운로드 URL 등 완전한 모델 메타데이터 제공
- **트렌딩 모델**: 실시간 인기 모델 및 트렌딩 정보 제공
- **고급 필터링**: 태그, 카테고리, 라이센스 등 다양한 조건으로 모델 필터링

### 🏷️ **스마트 태그 시스템**
- **계층형 태그 구조**: 효율적인 모델 분류를 위한 다단계 태그 시스템
- **동적 태그 관리**: 실시간 태그 업데이트 및 그룹별 태그 관리
- **태그 기반 검색**: 태그를 활용한 정확한 모델 검색 및 필터링

### ☁️ **엔터프라이즈급 저장소 관리**
- **S3 호환 저장소**: AWS S3, Ceph 등 다양한 S3 호환 저장소 지원
- **버킷 관리**: 버킷 생성, 삭제, 상세 정보 조회 (용량, 객체 수 등)
- **폴더 관리**: 폴더 생성, 삭제, 이름 변경, 복사 등 완전한 폴더 관리
- **대용량 파일 업로드**: 멀티파트 업로드를 통한 대용량 파일 처리 (>100MB)
- **업로드 진행 상태**: 실시간 업로드 진행 상태 추적 및 취소 기능
- **배치 작업**: 대량 객체 관리를 위한 배치 작업 지원 (1000개 단위)

### 🔐 **엔터프라이즈 보안**
- **JWT 기반 인증**: 강력한 JWT 토큰 기반 인증 시스템
- **이중 인증 모드**: 개발/프로덕션 환경별 인증 모드 지원
- **입력 검증**: Pydantic 모델 기반 완전한 입력 검증
- **보안 헤더**: CORS, 보안 헤더 등 웹 보안 표준 준수

### ⚡ **고성능 아키텍처**
- **완전 비동기 처리**: 모든 I/O 작업의 비동기 처리로 높은 성능 보장
- **연결 풀링**: HTTP 연결 풀링으로 외부 API 호출 최적화 (최대 50개 연결)
- **스마트 캐싱**: SHA256 기반 캐시 검증으로 데이터 무결성 보장
- **응답 압축**: gzip 압축을 통한 네트워크 최적화
- **비동기 트리 구조**: 계층형 저장소 구조의 비동기 페이지네이션

### 🛡️ **안정성 & 모니터링**
- **Rate Limiting**: IP 기반 요청 제한 (분당 200회 기본값)
- **Circuit Breaker**: 외부 API 장애 시 자동 보호 메커니즘
- **Request Timeout**: 요청별 타임아웃 설정 (5분 기본값)
- **구조화된 로깅**: JSON 형식의 구조화된 로그 및 요청 추적
- **Health Check**: 서비스 상태 모니터링 및 헬스체크 엔드포인트

### 🚀 **운영 효율성**
- **Docker 최적화**: 호스트 네트워크 모드를 통한 성능 최적화
- **다중 프로세스 지원**: 고성능 다중 프로세스 실행 지원
- **자동 로그 로테이션**: 10MB 단위 로그 파일 자동 로테이션
- **성능 벤치마크**: 내장된 성능 벤치마크 도구

## 지원하는 AI 모델 마켓

| 마켓 이름       | 설명                  | 지원 기능                        | 상태   |
|-------------|---------------------|------------------------------|------|
| HuggingFace | 글로벌 AI 모델 및 데이터 마켓  | 모델 검색, 태그 검색, 모델 다운로드, 트렌딩 모델 | ✅ 완전 지원 |
| AI Hub      | 대한민국 AI 모델 및 데이터 마켓 | 모델 검색, 태그 검색, 모델 다운로드        | 🚧 개발 중 |

## 아키텍처 & 기술 스택

### 🏗️ **아키텍처 설계**
- **마이크로서비스 아키텍처**: 명확한 관심사 분리와 모듈화
- **비동기 우선 아키텍처**: 전체 애플리케이션 스택에서 비동기 처리
- **팩토리 패턴**: 마켓 서비스 인스턴스화를 위한 팩토리 패턴
- **리포지토리 패턴**: 데이터 액세스 및 저장소 작업을 위한 리포지토리 패턴
- **미들웨어 파이프라인**: 로깅, 속도 제한, 인증 등 횡단 관심사 처리

### 💻 **기술 스택**

| 분야 | 기술 스택 | 설명 |
|------|----------|------|
| **백엔드** | FastAPI, Python 3.10+, Uvicorn | 고성능 비동기 웹 프레임워크 |
| **인증** | JWT (python-jose), bcrypt | 토큰 기반 인증 및 암호 해싱 |
| **저장소** | AWS S3, Ceph S3-compatible, aiobotocore | 비동기 S3 클라이언트 |
| **캐싱** | aiocache (In-memory) | 비동기 인메모리 캐싱 |
| **HTTP 클라이언트** | httpx | 비동기 HTTP 클라이언트 |
| **데이터 검증** | Pydantic | 데이터 검증 및 설정 관리 |
| **테스트** | pytest, httpx | 테스트 프레임워크 |
| **배포** | Docker, Docker Compose | 컨테이너화 및 오케스트레이션 |
| **모니터링** | 구조화된 로깅, Health Check | JSON 로깅 및 헬스체크 |

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

#### 버킷 관리
- `GET /api/v1/buckets` - 모든 버킷 목록 조회
- `POST /api/v1/buckets` - 새 버킷 생성
- `GET /api/v1/buckets/{bucket_id}` - 버킷 상세 정보 조회 (객체 수, 총 용량 포함)
- `DELETE /api/v1/buckets/{bucket_id}` - 버킷 및 모든 내용 삭제

#### 폴더 관리
- `GET /api/v1/buckets/{bucket_id}/objects` - 폴더 내용을 트리 구조로 조회 (`prefix`와 `depth` 쿼리 사용)
- `POST /api/v1/buckets/{bucket_id}/folders` - 빈 폴더 생성
- `DELETE /api/v1/buckets/{bucket_id}/folders/{folder_path:path}` - 폴더 및 모든 내용 삭제
- `PUT /api/v1/buckets/{bucket_id}/folders/{folder_path:path}` - 폴더 이름 변경/이동
- `POST /api/v1/buckets/{bucket_id}/folders/{folder_path:path}/copy` - 폴더 복사
- `GET /api/v1/buckets/{bucket_id}/folders/{folder_path:path}/stats` - 폴더 통계 (총 크기, 파일 수, 폴더 수)

#### 객체 관리
- `POST /api/v1/buckets/{bucket_id}/objects` - 객체 업로드 (멀티파트 업로드로 대용량 파일 지원)
- `GET /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - 객체 다운로드
- `PUT /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - 객체 이름 변경/이동
- `POST /api/v1/buckets/{bucket_id}/objects/{object_key:path}/copy` - 객체 복사
- `DELETE /api/v1/buckets/{bucket_id}/objects/{object_key:path}` - 객체 삭제

#### 업로드 진행 상태 추적
- `GET /api/v1/uploads` - 모든 진행 중/완료/실패 업로드 목록 조회
- `GET /api/v1/uploads/{upload_id}` - 특정 업로드의 상세 진행 상태 조회
- `DELETE /api/v1/uploads/{upload_id}` - 진행 중인 업로드 취소

## 환경 변수 설정

### 필수 환경 변수
```env
# API 토큰
HF_API_TOKEN=your_huggingface_token
SECRET_KEY=your_jwt_secret_key

# 관리자 계정
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123  # 개발용
ADMIN_PASSWORD_HASH=     # 프로덕션용

# 저장소 설정 (AWS S3 또는 Ceph 선택)
STORAGE_TYPE=aws # 또는 ceph
```

### AWS S3 설정
```env
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
AWS_S3_BUCKET=your-bucket-name
```

### Ceph S3 호환 설정
```env
CEPH_S3_ENDPOINT=https://your-ceph-endpoint
CEPH_ACCESS_KEY=your_access_key
CEPH_SECRET_KEY=your_secret_key
CEPH_BUCKET=your-bucket-name
```

### 성능 및 보안 설정
```env
# 캐싱 설정
CACHE_TIMEOUT=3600              # 캐시 타임아웃 (초)
GROUPS=default,premium          # 사용자 그룹
LIMITED_GROUPS=free            # 제한된 그룹

# 속도 제한 (분당 요청 수)
RATE_LIMIT=200

# 로깅 설정
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# JWT 설정
ACCESS_TOKEN_EXPIRE_MINUTES=30  # JWT 토큰 만료 시간 (분)

# CORS 설정
ALLOWED_ORIGINS=["*"]           # 허용된 오리진
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
- **Rate Limiting**: IP당 분당 200회 요청 제한 (설정 가능)
- **Circuit Breaker**: 외부 API 장애 시 자동 차단 및 복구
- **Request Timeout**: 5분 요청 타임아웃 (장시간 작업 지원)
- **Connection Pooling**: 최대 50개 연결 풀링으로 외부 API 최적화
- **Async Tree Building**: 비동기 저장소 트리 구조 구축으로 응답 속도 향상
- **Health Check**: `/` 엔드포인트를 통한 서비스 상태 확인

### 성능 벤치마크 실행
```bash
# 성능 벤치마크 실행
python benchmarks/performance_benchmark.py

# 성능 테스트 스크립트 실행
python scripts/run_performance_test.py
```

## 테스트 실행

### 전체 테스트 실행
```bash
# 모든 테스트 실행
pytest

# 커버리지와 함께 테스트 실행
pytest --cov=app tests/

# 특정 테스트 파일 실행
pytest tests/api/test_models.py

# 비동기 테스트 실행
pytest tests/api/test_async_models.py
```

### 테스트 환경
- 테스트는 자동으로 `.env` 파일을 로드합니다
- 외부 API 호출은 Mock으로 처리됩니다
- 임시 파일을 사용한 다운로드 테스트 지원

## 최신 개선사항 (2025년 1월)

### 🚀 **주요 기능 추가**
- **완전한 S3 버킷 관리**: 버킷 생성, 삭제, 상세 통계 조회
- **고급 폴더 관리**: 폴더 생성, 삭제, 이름 변경, 복사 기능
- **업로드 취소 기능**: 진행 중인 업로드 실시간 취소 및 상태 추적
- **배치 객체 관리**: 1000개 단위의 대량 객체 관리 최적화

### ⚡ **성능 최적화**
- **호스트 네트워크 모드**: Docker 호스트 네트워킹으로 성능 대폭 향상
- **비동기 저장소 트리**: 계층형 저장소 구조의 비동기 구축으로 응답 속도 향상
- **요청 타임아웃 미들웨어**: 장시간 작업을 위한 향상된 타임아웃 처리
- **다중 프로세스 지원**: 고성능 다중 프로세스 실행 환경

### 🛡️ **보안 및 안정성 강화**
- **안전한 로깅**: 바이너리 파일 업로드 시 로깅 보호 메커니즘
- **향상된 에러 처리**: 중앙화된 에러 로깅 및 처리 시스템
- **이중 인증 모드**: 개발/프로덕션 환경별 최적화된 인증 플로우

## 기여하기

HUB Connect API의 발전에 기여해주세요! 다음과 같은 방법으로 참여할 수 있습니다: 

1. 이 저장소를 Fork하세요
2. 새로운 Feature 브랜치를 만드세요 (`git checkout -b feature/AmazingFeature`)
3. 변경사항을 Commit하세요 (`git commit -m 'Add some AmazingFeature'`)
4. 브랜치에 Push하세요 (`git push origin feature/AmazingFeature`)
5. Pull Request를 열어주세요

### 개발 가이드라인
- 모든 새로운 기능에 대해 테스트 코드 작성
- API 엔드포인트는 OpenAPI 스키마 준수
- 비동기 패턴 유지 및 성능 최적화 고려
- 보안 모범 사례 준수

## 라이선스

이 프로젝트는 Apache License 2.0에 따라 라이선스가 부여됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 연락처

프로젝트 링크: [https://github.com/ai-paas/hub-connect](https://github.com/ai-paas/hub-connect)

## 감사의 말

- 모든 기여자 분들
- HuggingFace 커뮤니티
- FastAPI 및 Python 생태계

---

⭐️ 이 프로젝트가 도움이 되었다면 스타를 눌러주세요!
