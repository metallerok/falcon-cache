import msgpack
import io
import falcon
import datetime as dt
import logging
from typing import List, Callable
from redis import Redis
from redis_helper.main import RedisHelper

logger = logging.getLogger(__name__)


class APICache:
    enabled = True

    invalidate_methods = ["POST", "PATCH", "PUT", "DELETE", "PROPPATCH"]
    cache_methods = ["GET", "PROPFIND", "REPORT"]
    CACHE_HEADER = 'X-WSGILook-Cache'

    API_CACHE_HIT_COUNTER_KEY = "API_CACHE:HIT_COUNTER"
    API_CACHE_MISS_COUNTER_KEY = "API_CACHE:MISS_COUNTER"

    def __init__(self, redis: Redis):
        self.redis = redis
        self._cache_key_maker = self._make_cache_key

    @staticmethod
    def _make_cache_key(req: falcon.Request):
        user_id = req.context.get("current_user_id")
        return (f"API_CACHE:{req.forwarded_host}:ORIGIN:{req.get_header('origin')}"
                f":USER:{user_id}:{req.relative_uri}:{req.params}")

    def make_cache_key(self, req: falcon.Request) -> str:
        return self._cache_key_maker(req)

    def set_cache_key_maker(self, func: Callable[[falcon.Request], str]):
        self._cache_key_maker = func

    @staticmethod
    def _serialize_response(resp: falcon.Response):
        stream = None
        if resp.stream:
            stream = resp.stream.read()
            resp.stream = io.BytesIO(stream)

        if hasattr(resp, "text"):
            text = resp.text
        else:  # resp.body is deprecated
            text = resp.body

        value = msgpack.packb(
            [resp.status, resp.content_type, text, stream, resp.headers],
            use_bin_type=True
        )

        return value

    @staticmethod
    def _deserialize_response(resp: falcon.Response, data):
        resp.status, resp.content_type, text, stream, headers = msgpack.unpackb(data, raw=False)

        if hasattr(resp, "text"):
            setattr(resp, "text", text)
        else:
            setattr(resp, "body", text)

        resp.stream = io.BytesIO(stream) if stream else None
        resp.set_headers(headers)
        resp.complete = True

    def cached(
            self,
            timeout: int,
            tags_templates: List[str] = None,
            stream_length_restriction: int = 512,
    ):
        if tags_templates is None:
            tags_templates = []

        def decorator(func, *args):
            def wrapper(cls, req, resp, *args, **kwargs):
                if not self.enabled:
                    func(cls, req, resp, *args, **kwargs)
                    return

                redis_helper: RedisHelper = RedisHelper(self.redis)
                key = self.make_cache_key(req)

                logger.debug(f"APICache used for key: {key}")

                if req.method in APICache.invalidate_methods:
                    self.redis.delete(key)

                if req.method in APICache.cache_methods:
                    data = self.redis.get(key)

                    if data:
                        APICache._deserialize_response(resp, data)
                        resp.set_header(APICache.CACHE_HEADER, 'Hit')
                        self._increase_hit_counter(self.redis, key)
                        return
                    else:
                        resp.set_header(APICache.CACHE_HEADER, 'Miss')
                        self._increase_miss_counter(self.redis, key)

                func(cls, req, resp, *args, **kwargs)

                if req.method in APICache.cache_methods:
                    if resp.stream and round(resp.stream.content_length / 1024) > stream_length_restriction:
                        return

                    try:
                        value = APICache._serialize_response(resp)

                        tags = []
                        format_keys = {
                            **req.context,
                            **req.params
                        }

                        for tag in tags_templates:
                            tags.append(tag.format(**format_keys))

                        redis_helper.set_with_tags(key, value, ex=dt.timedelta(seconds=timeout), tags=tags)
                    except Exception as e:
                        logger.error(e)

            return wrapper

        return decorator

    def invalidate_by_tag(self, tag: str):
        redis_helper = RedisHelper(self.redis)
        redis_helper.delete_by_tag(tag)

    @staticmethod
    def _increase_hit_counter(redis: Redis, key: str):
        try:
            if not redis.exists(APICache.API_CACHE_HIT_COUNTER_KEY):
                redis.set(APICache.API_CACHE_HIT_COUNTER_KEY, 0, ex=dt.timedelta(days=1))

            if not redis.exists(f"{key}:HIT"):
                redis.set(f"{key}:HIT", 0, ex=dt.timedelta(days=1))

            redis.incr(f"{key}:HIT")
            redis.incr(APICache.API_CACHE_HIT_COUNTER_KEY)
        except Exception as e:
            logger.error(e)

    @staticmethod
    def _increase_miss_counter(redis: Redis, key: str):
        try:
            if not redis.exists(APICache.API_CACHE_MISS_COUNTER_KEY):
                redis.set(APICache.API_CACHE_MISS_COUNTER_KEY, 0, ex=dt.timedelta(days=1))

            if not redis.exists(f"{key}:MISS"):
                redis.set(f"{key}:MISS", 0, ex=dt.timedelta(days=1))

            redis.incr(f"{key}:MISS")
            redis.incr(APICache.API_CACHE_MISS_COUNTER_KEY)
        except Exception as e:
            logger.error(e)
