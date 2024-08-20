import logging
from logging import LogRecord
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from app.core.config import settings


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


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_filter.request_info = {
            "request_path": request.url.path,
            "request_method": request.method,
        }

        if logger.level <= logging.DEBUG:
            request_filter.request_info["request_params"] = str(dict(request.query_params))
            body = await request.body()
            body_str = body.decode() if body else ""
            request_filter.request_info["request_body"] = body_str[:1000] + "..." if len(body_str) > 1000 else body_str

        response = await call_next(request)
        return response


def get_logging_level(level_name: str) -> int:
    return getattr(logging, level_name.upper(), logging.INFO)


def setup_logging():
    log_level = get_logging_level(settings.LOG_LEVEL)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s - Path: %(request_path)s - Method: %(request_method)s",
        handlers=[
            logging.FileHandler("app.log"),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)
    request_filter = RequestInfoFilter()
    logger.addFilter(request_filter)
    return logger, request_filter


logger, request_filter = setup_logging()


# Function to log external API calls
def log_external_api_call(url: str, method: str, params: dict = None, data: dict = None):
    logger.info(f"External API Call - URL: {url}, Method: {method}, Params: {params}, Data: {data}")