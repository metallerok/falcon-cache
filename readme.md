# Init

```python
import redis
import falcon
import redis
from falcon_cache.middleware import CacheMiddleware
from falcon_cache.cache import APICache


redis_conn = redis.Redis(...)
api_cache = APICache(redis=redis_conn)

app = falcon.API(middleware=[
    CacheMiddleware(cache=api_cache),
])
```

# Usage
```python
class WebResourceController:
    @classmethod
    @api_cache.cached(timeout=300)
    def on_get(cls, req, resp):
        pass
```

## Creation cache with tags
```python
class TaskWebController:
    @classmethod
    @api_cache.cached(timeout=300, tags_templates=["task_id:{task_id}"])  # task_id must be in req.params
    def on_get(cls, req, resp):
        task_id = req.params.get("task_id")
```
Now you can invalidate cache by tag
```python
api_cache.invalidate_by_tag(tag="task_id:1")
```

## Make your own cache key creation method
```python
def make_cache_key(req: falcon.Request) -> str:
    user_id = req.context.get("current_user_id")
    return (f"API_CACHE:{req.forwarded_host}:ORIGIN:{req.get_header('origin')}:ACCEPT:{req.get_header('accept')}"
            f":USER:{user_id}:{req.relative_uri}:{req.params}")

app_globals.api_cache = APICache(redis=redis_conn)
app_globals.api_cache.set_cache_key_maker(make_cache_key)
```

# Disable cache for tests
```python
api_cache = APICache(redis=redis_conn)
api_cache.enabled = False
```