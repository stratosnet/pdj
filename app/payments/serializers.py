import uuid
from typing import Tuple, Optional


class ProcessorIDSerializer:
    SEPARATOR = ":"

    @classmethod
    def serialize_subscription(cls) -> str:
        return f"sub{cls.SEPARATOR}{uuid.uuid4().hex}"

    @classmethod
    def deserialize(cls, custom_id: str) -> Tuple[str, Optional[str]]:
        parts = custom_id.split(cls.SEPARATOR)

        if len(parts) == 1:
            # Recurring subscription (simple UUID)
            return None, parts[0]

        if len(parts) == 2:
            # Non-recurring subscription with plan_id
            return parts[0], parts[1]

        raise ValueError(f"Invalid custom_id format: {custom_id}")
