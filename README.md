# Scrapy-Antiban

This spider middleware aims to avoid banned by the target websites. When the ban condition is triggered, this middleware stop the engine for a certain period, then re-check until the ban lift.

Initially, the engine stopped for 60 seconds, then it will increase by 50% if still banned.

Usage,

```python
# in spider, re-yield same request with meta,
meta = {"pre_request_banned": True}

# in settings.py
SPIDER_MIDDLEWARES = {
    "scrapy_antiban.throttle.ThrottleMiddleware": 543,
}
```
