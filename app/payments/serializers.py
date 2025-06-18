import uuid
from typing import Callable

from django.conf import settings
from django.core.cache import cache


class ProcessorIDSerializer:
    SEPARATOR = ":"

    @staticmethod
    def get_cache_key(ctype: str, plan_id: str, processor_id: str, user_id: str) -> str:
        return f"{ctype}:plan:{plan_id}:processor:{processor_id}:user:{processor_id}"

    @staticmethod
    def get_or_create_url(cache_key: str, create_url_func: Callable):
        lock_key = f"lock:{cache_key}"
        with cache.lock(lock_key):
            url = cache.get(cache_key)
            if not url:
                url = create_url_func()
                if url:
                    cache.set(
                        cache_key, url, timeout=settings.CACHE_PROCESSOR_URL_TIMEOUT
                    )
            return url

    @staticmethod
    def purge_cache_key(ctype: str, plan_id: str, processor_id: str, user_id: str):
        cache_key = ProcessorIDSerializer.get_cache_key(
            ctype, plan_id, processor_id, user_id
        )
        cache.delete(cache_key)

    @classmethod
    def serialize_subscription(cls) -> str:
        return f"sub{cls.SEPARATOR}{uuid.uuid4().hex}"

    @classmethod
    def serialize_plan_upgrade(cls) -> str:
        return f"planup{cls.SEPARATOR}{uuid.uuid4().hex}"

    @classmethod
    def deserialize(cls, custom_id: str) -> tuple[str | None, str]:
        parts = custom_id.split(cls.SEPARATOR)

        if len(parts) == 1:
            # Recurring subscription (simple UUID)
            return None, str(uuid.UUID(parts[0])) if parts[0] else ""

        if len(parts) == 2:
            # Non-recurring subscription with plan_id
            return parts[0], str(uuid.UUID(parts[1])) if parts[1] else ""

        raise ValueError(f"Invalid custom_id format: {custom_id}")
