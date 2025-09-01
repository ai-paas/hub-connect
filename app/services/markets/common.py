from fastapi import HTTPException

# Centrally manage market-specific service mappings
market_services = {
    "huggingface": "app.services.markets.huggingface.huggingface_models.HuggingFaceService",
    "aihub": "app.services.markets.aihub.aihub_models.AihubService",
    # Register here when other markets are added
}


def get_market_service(market: str):
    service = market_services.get(market)
    if not service:
        raise HTTPException(status_code=404, detail=f"Market {market} not supported")

    module_name, class_name = service.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    service_class = getattr(module, class_name)

    return service_class()
