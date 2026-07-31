from fastapi import HTTPException


# Async market service registry - import dynamically to avoid dependency issues
ASYNC_MARKET_SERVICES = {
    "huggingface": "app.services.markets.huggingface.async_huggingface_models.AsyncHuggingFaceService",
    "kaggle": "app.services.markets.kaggle.async_kaggle_models.AsyncKaggleService",
}

_async_market_instances = {}

async def get_async_market_service(market: str):
    """
    Factory function to get async market service instance

    Args:
        market: Market name (huggingface, kaggle)

    Returns:
        Async market service instance

    Raises:
        HTTPException: If market is not supported
    """
    if market not in ASYNC_MARKET_SERVICES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported market: {market}. "
                f"Available markets: {list(ASYNC_MARKET_SERVICES.keys())}"
            ),
        )
    
    if market not in _async_market_instances:
        service_path = ASYNC_MARKET_SERVICES[market]
        module_name, class_name = service_path.rsplit(".", 1)

        # Dynamic import to avoid dependency issues
        module = __import__(module_name, fromlist=[class_name])
        service_class = getattr(module, class_name)
        _async_market_instances[market] = service_class()

    return _async_market_instances[market]


async def close_async_market_services() -> None:
    """Close reusable market clients during application shutdown."""
    for service in _async_market_instances.values():
        close = getattr(service, "close_http_client", None)
        if callable(close):
            await close()
    _async_market_instances.clear()

def get_available_async_markets() -> list:
    """Get list of available async markets"""
    return list(ASYNC_MARKET_SERVICES.keys())
