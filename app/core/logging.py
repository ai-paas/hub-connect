import logging
from logging import LogRecord
from logging.handlers import RotatingFileHandler
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from app.core.config import settings
import os


class RequestInfoFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.request_info = {}

    def filter(self, record: LogRecord) -> bool:
        for key, value in self.request_info.items():
            setattr(record, key, value)
        # Set default values for common fields if they're not present
        record.request_path = getattr(record, 'request_path', 'N/A')
        record.request_method = getattr(record, 'request_method', 'N/A')
        return True


class SafeFormatter(logging.Formatter):
    """요청 컨텍스트가 있을 때와 없을 때 모두 안전하게 처리하는 포맷터"""
    
    def format(self, record):
        # request_path와 request_method가 있으면 포함, 없으면 제외
        if hasattr(record, 'request_path') and record.request_path != 'N/A':
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s - Path: %(request_path)s - Method: %(request_method)s"
        else:
            self._style._fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        return super().format(record)


class LoggingMiddleware(BaseHTTPMiddleware):
    """안전한 로깅 미들웨어 - 바이너리 파일 업로드 지원"""
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_filter.request_info = {
            "request_path": request.url.path,
            "request_method": request.method,
        }

        # DEBUG 레벨일 때만 요청 세부사항 로깅 - 현재는 비활성화
        # 로그 레벨 확인: logger.level = {logger.level}, DEBUG = {logging.DEBUG}
        if False and logger.level <= logging.DEBUG:
            request_filter.request_info["request_params"] = str(dict(request.query_params))
            
            # 파일 업로드의 경우 body 로깅을 완전히 스킵
            content_type = request.headers.get("content-type", "")
            if content_type and content_type.startswith("multipart/form-data"):
                request_filter.request_info["request_body"] = "<multipart form data - not logged>"
            else:
                try:
                    body = await request.body()
                    if body:
                        # 안전한 디코딩
                        body_str = body.decode('utf-8', errors='ignore')
                        body_str = body_str[:1000] + "..." if len(body_str) > 1000 else body_str
                    else:
                        body_str = ""
                    request_filter.request_info["request_body"] = body_str
                except Exception:
                    # 모든 예외를 조용히 처리
                    request_filter.request_info["request_body"] = "<logging skipped>"

        response = await call_next(request)
        
        # API 요청 로그 기록 (인증된 사용자 정보 포함)
        user = getattr(request.state, 'user', None)
        username = user.get('username') if user else None
        log_api_request(request.method, request.url.path, response.status_code, username)
        
        # 요청 처리 후 컨텍스트 정리
        request_filter.request_info = {}
        
        return response


def get_logging_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def setup_logging():
    log_level = get_logging_level(settings.LOG_LEVEL)

    # logs 디렉토리 생성 시도
    try:
        os.makedirs("logs", exist_ok=True)
        # 디렉토리 쓰기 권한 확인
        if not os.access("logs", os.W_OK):
            raise PermissionError("Cannot write to logs directory")
        use_file_logging = True
    except (PermissionError, OSError) as e:
        # 로그 디렉토리 생성 실패 시 경고 (fallback으로 콘솔 로깅만 사용)
        import sys
        sys.stderr.write(f"Warning: Cannot create or write to logs directory ({e}). Using console logging only.\n")
        use_file_logging = False

    # request_filter 인스턴스 생성
    request_filter = RequestInfoFilter()
    
    # 기본 포맷터
    formatter = SafeFormatter()
    
    # API 호출 전용 포맷터
    api_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    
    file_handlers = []
    
    if use_file_logging:
        try:
            # 파일 핸들러들 (로테이션 적용)
            # 1. 일반 애플리케이션 로그
            app_handler = RotatingFileHandler(
                "logs/app.log", 
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            app_handler.setFormatter(formatter)
            app_handler.setLevel(log_level)
            
            # 2. API 호출 로그
            api_handler = RotatingFileHandler(
                "logs/api_calls.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            api_handler.setFormatter(api_formatter)
            api_handler.setLevel(logging.INFO)
            
            # 3. 에러 로그
            error_handler = RotatingFileHandler(
                "logs/error.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            error_handler.setFormatter(formatter)
            error_handler.setLevel(logging.ERROR)
            
            file_handlers = [app_handler, api_handler, error_handler]
            
        except (PermissionError, OSError) as e:
            import sys
            sys.stderr.write(f"Warning: Cannot create log files ({e}). Using console logging only.\n")
            file_handlers = []
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()  # 기존 핸들러 제거
    
    # 파일 핸들러 추가 (사용 가능한 경우에만)
    if file_handlers:
        root_logger.addHandler(file_handlers[0])  # app_handler
        root_logger.addHandler(file_handlers[2])  # error_handler
    
    root_logger.addHandler(console_handler)
    
    # API 호출 전용 로거 설정 (파일 핸들러가 있는 경우에만)
    if file_handlers:
        api_logger = logging.getLogger("api_calls")
        api_logger.setLevel(logging.INFO)
        api_logger.handlers.clear()
        api_logger.addHandler(file_handlers[1])  # api_handler
        api_logger.propagate = False  # 루트 로거로 전파 방지
    
    # request_filter를 루트 로거에 적용
    root_logger.addFilter(request_filter)
    
    logger = logging.getLogger(__name__)
    if not file_handlers:
        logger.warning("File logging disabled due to permission issues. Using console logging only.")
    
    return logger, request_filter


logger, request_filter = setup_logging()


# Function to log external API calls
def log_external_api_call(url: str, method: str, params: dict = None, data: dict = None):
    api_logger = logging.getLogger("api_calls")
    api_logger.info(f"External API Call - URL: {url}, Method: {method}, Params: {params}, Data: {data}")

# Function to log API requests
def log_api_request(method: str, path: str, status_code: int, user: str = None):
    api_logger = logging.getLogger("api_calls")
    user_info = f" - User: {user}" if user else ""
    api_logger.info(f"API Request - {method} {path} - Status: {status_code}{user_info}")
