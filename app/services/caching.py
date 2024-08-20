from aiocache import Cache
import hashlib
import json
from app.core.config import settings

cache = Cache(Cache.MEMORY)

async def cache_data(key, data, timeout=settings.CACHE_TIMEOUT):
    data_bytes = json.dumps(data).encode('utf-8')
    data_hash = hashlib.sha256(data_bytes).hexdigest()

    await cache.set(key, data, ttl=timeout)
    await cache.set(f"{key}_hash", data_hash, ttl=timeout)

async def get_cached_data(key):
    data = await cache.get(key)
    data_hash = await cache.get(f"{key}_hash")
    return data, data_hash
