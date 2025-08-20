from typing import Union

# Async market service registry - import dynamically to avoid dependency issues
ASYNC_MARKET_SERVICES = {
    "huggingface": "app.services.markets.huggingface.async_huggingface_models.AsyncHuggingFaceService",
    "aihub": "app.services.markets.aihub.aihub_models.AihubService",  # Now has async methods
}

async def get_async_market_service(market: str):
    """
    Factory function to get async market service instance
    
    Args:
        market: Market name (huggingface, aihub)
        
    Returns:
        Async market service instance
        
    Raises:
        ValueError: If market is not supported
    """
    if market not in ASYNC_MARKET_SERVICES:
        raise ValueError(f"Unsupported market: {market}. Available markets: {list(ASYNC_MARKET_SERVICES.keys())}")
    
    service_path = ASYNC_MARKET_SERVICES[market]
    module_name, class_name = service_path.rsplit(".", 1)
    
    # Dynamic import to avoid dependency issues
    module = __import__(module_name, fromlist=[class_name])
    service_class = getattr(module, class_name)
    
    return service_class()

def get_available_async_markets() -> list:
    """Get list of available async markets"""
    return list(ASYNC_MARKET_SERVICES.keys())