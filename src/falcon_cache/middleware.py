from cache import APICache
from redis import Redis


class CacheMiddleware:
    @classmethod
    def process_response(cls, req, resp, resource, req_succeeded):
        if not req_succeeded:
            return

        redis: Redis = req.context["redis"]
        key = APICache.make_cache_key(req)

        if req.method in APICache.invalidate_methods:
            redis.delete(key)
