import asyncio
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from app.services.caching import cache_data, get_cached_data
from app.services.markets.async_common import get_async_market_service
from app.core.config import settings
from app.core.logging import logger


class BackgroundCacheService:
    """Background service for preloading and refreshing cache data."""
    
    def __init__(self):
        self.is_running = False
        self.refresh_interval = 3600  # 1 hour default
        self.cache_warmup_markets = ["huggingface", "aihub"]  # Markets to preload
        self.background_task: Optional[asyncio.Task] = None
        self.last_refresh: Dict[str, datetime] = {}
        
    async def start(self, refresh_interval_seconds: int = 3600):
        """Start the background cache service."""
        if self.is_running:
            logger.warning("Background cache service is already running")
            return
            
        self.refresh_interval = refresh_interval_seconds
        self.is_running = True
        
        logger.info(f"Starting background cache service with {refresh_interval_seconds}s refresh interval")
        
        # Initial cache warmup
        await self.warmup_cache()
        
        # Start background refresh task
        self.background_task = asyncio.create_task(self._background_refresh_loop())
        logger.info("Background cache service started successfully")
        
    async def stop(self):
        """Stop the background cache service."""
        if not self.is_running:
            return
            
        self.is_running = False
        
        if self.background_task and not self.background_task.done():
            self.background_task.cancel()
            try:
                await self.background_task
            except asyncio.CancelledError:
                logger.info("Background cache task cancelled")
                
        logger.info("Background cache service stopped")
        
    async def warmup_cache(self):
        """Preload cache with tag data for all supported markets."""
        logger.info("Starting cache warmup...")
        warmup_start = datetime.now()
        
        warmup_tasks = []
        for market in self.cache_warmup_markets:
            task = asyncio.create_task(self._preload_market_tags(market))
            warmup_tasks.append(task)
            
        # Run all warmup tasks concurrently
        results = await asyncio.gather(*warmup_tasks, return_exceptions=True)
        
        success_count = 0
        for i, result in enumerate(results):
            market = self.cache_warmup_markets[i]
            if isinstance(result, Exception):
                logger.error(f"Failed to warmup cache for market {market}: {result}")
            else:
                success_count += 1
                logger.debug(f"Successfully warmed up cache for market {market}")
                
        warmup_duration = (datetime.now() - warmup_start).total_seconds()
        logger.info(
            f"Cache warmup completed in {warmup_duration:.2f}s - "
            f"Success: {success_count}/{len(self.cache_warmup_markets)} markets"
        )
        
    async def _preload_market_tags(self, market: str):
        """Preload tag data for a specific market."""
        try:
            cache_key = f"{market}_tag_cache"
            
            # Check if cache already exists and is fresh
            cached_data, _ = await get_cached_data(cache_key)
            last_refresh = self.last_refresh.get(market)
            
            if cached_data and last_refresh:
                time_since_refresh = datetime.now() - last_refresh
                if time_since_refresh.total_seconds() < self.refresh_interval:
                    logger.debug(f"Cache for {market} is still fresh, skipping preload")
                    return cached_data
            
            # Fetch fresh data
            logger.debug(f"Preloading tag cache for market: {market}")
            market_service = await get_async_market_service(market)
            
            if not market_service:
                logger.warning(f"Market service not available for: {market}")
                return None
                
            # Fetch tags data
            tags_data = await market_service.get_tags()
            
            if not tags_data:
                logger.warning(f"No tag data received for market: {market}")
                return None
                
            # Cache the data with extended TTL for background refresh
            extended_ttl = self.refresh_interval + 300  # Extra 5 minutes buffer
            await cache_data(cache_key, tags_data, timeout=extended_ttl)
            
            # Also preload individual group caches
            for group in settings.GROUPS:
                if group in tags_data:
                    group_cache_key = f"{market}_{group}_data"
                    await cache_data(group_cache_key, tags_data[group], timeout=extended_ttl)
            
            self.last_refresh[market] = datetime.now()
            
            # Log cache statistics
            total_tags = sum(len(group_data) if isinstance(group_data, list) else len(group_data) 
                           for group_data in tags_data.values())
            logger.info(f"Preloaded {total_tags} tags for market {market} across {len(tags_data)} groups")
            
            return tags_data
            
        except Exception as e:
            logger.error(f"Error preloading cache for market {market}: {e}")
            raise
            
    async def _background_refresh_loop(self):
        """Background loop for periodic cache refresh."""
        logger.info(f"Background cache refresh loop started (interval: {self.refresh_interval}s)")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.refresh_interval)
                
                if not self.is_running:
                    break
                    
                logger.info("Starting periodic cache refresh...")
                await self.warmup_cache()
                
            except asyncio.CancelledError:
                logger.info("Background refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in background refresh loop: {e}")
                # Wait a bit before retrying to avoid rapid error loops
                await asyncio.sleep(60)
                
    async def force_refresh(self, market: Optional[str] = None):
        """Force immediate cache refresh for specific market or all markets."""
        if market:
            logger.info(f"Force refreshing cache for market: {market}")
            await self._preload_market_tags(market)
        else:
            logger.info("Force refreshing cache for all markets")
            await self.warmup_cache()
            
    def get_cache_status(self) -> Dict[str, any]:
        """Get current cache service status."""
        return {
            "is_running": self.is_running,
            "refresh_interval": self.refresh_interval,
            "supported_markets": self.cache_warmup_markets,
            "last_refresh": {
                market: refresh_time.isoformat() 
                for market, refresh_time in self.last_refresh.items()
            },
            "next_refresh": (
                datetime.now() + timedelta(seconds=self.refresh_interval)
            ).isoformat() if self.is_running else None
        }


# Global service instance
background_cache_service = BackgroundCacheService()