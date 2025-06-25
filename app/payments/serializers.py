import uuid


class ProcessorIDSerializer:
    SEPARATOR = ":"

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
