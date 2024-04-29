from falcon_cache.cache import APICache


class CacheMiddleware:
    def __init__(self, cache: APICache):
        self._cache = cache

    def process_response(self, req, resp, resource, req_succeeded):
        if not req_succeeded:
            return

        key = self._cache.make_cache_key(req)

        if req.method in self._cache.invalidate_methods:
            self._cache.redis.delete(key)
