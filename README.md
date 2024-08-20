# HUB Connect API

![GitHub license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)
![Python version](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.112.1%2B-green.svg)

HUB Connect API는 3rd party 모델을 AI-PaaS에 연결하기 위한 API 서비스입니다.
직관적인 인터페이스와 풍부한 기능을 통해 AI 개발에 필요한 모델과 데이터를 손쉽게 이용할 수 있습니다.

## 주요 기능

🔍 **모델 검색 및 조회**: HuggingFace 모델을 쉽게 검색하고 상세 정보를 조회할 수 있습니다.

📈 **트렌딩 모델**: 최신 트렌드를 반영한 인기 모델을 확인할 수 있습니다.

🏷️ **태그 관리**: 효율적인 모델 분류와 검색을 위한 태그 시스템을 제공합니다.

📁 **파일 관리**: 모델 관련 파일을 손쉽게 관리할 수 있습니다.

🚀 **빠른 통합**: RESTful API를 통해 기존 시스템에 쉽게 통합할 수 있습니다.

## 지원하는 AI 모델 마켓

| 마켓 이름       | 설명                  | 지원 기능                 | 상태   |
|-------------|---------------------|-----------------------|------|
| HuggingFace | 글로벌 AI 모델 및 데이터 마켓  | 모델 검색, 태그 검색, 모델 다운로드 | 지원 중 |
| AI API Data | 대한민국 AI 모델 및 데이터 마켓 | | 지원 예정 |

## 빠른 시작

### 전제 조건

- Python 3.10+

### 설치 및 실행

1. 리포지토리 클론:
   ```bash
   git clone https://github.com/ai-paas/hub-connect.git
   cd hub-connect
   ```

2. 환경 설정:
   ```bash
   cp .env.sample .env
   # .env 파일을 열어 필요한 설정을 변경하세요
   ## huggingface_token: Hugging Face API 토큰
   ```

3. 라이브러리 설치 및 실행:
   ```bash
   pip install -r requirements.txt
   python run.py
   ```

4. 브라우저에서 `http://localhost:8001/docs`를 열어 Swagger UI에서 API 문서를 확인하세요.

## 프로젝트 구조

```
hub-connect/
├── app/
│   ├── api/
│   │   ├── models.py
│   │   └── tags.py
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── services/
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
│   │   └── helpers.py
│   └── main.py
├── tests/
├── .env.sample
├── .gitignore
├── README.md
├── requirements.txt
└── run.py
```

## API 문서

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

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